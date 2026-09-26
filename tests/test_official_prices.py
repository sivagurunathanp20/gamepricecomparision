"""Offline tests: the stores' HTTP APIs are mocked with their real response shapes.
Run:  python -m unittest tests.test_official_prices -v
"""
import os, shutil, tempfile, unittest
from unittest.mock import patch, MagicMock

_tmp = tempfile.mkdtemp()
_db = os.path.join(_tmp, "t.db")
_src = os.path.join(os.path.dirname(__file__), "..", "game_deals.db")
if os.path.exists(_src):
    shutil.copy(_src, _db)            # exercise the legacy-DB migration
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"

from app import create_app
from extensions import db
from models import Game, GamePlatform, Edition
import official_prices as op


def fake_response(payload, status=200):
    r = MagicMock(); r.status_code = status; r.json.return_value = payload; r.close = lambda: None
    return r


APP = {"1245620": {"success": True, "data": {
    "type": "game", "name": "ELDEN RING", "is_free": False,
    "price_overview": {"currency": "INR", "initial": 399900, "final": 199950, "discount_percent": 50},
    "package_groups": [{"subs": [{"packageid": 111, "option_text": "x"}, {"packageid": 222, "option_text": "y"}]}]}}}
PKG = {"111": {"111": {"success": True, "data": {"name": "ELDEN RING", "price": {"currency": "INR", "initial": 399900, "final": 199950, "discount_percent": 50}}}},
       "222": {"222": {"success": True, "data": {"name": "ELDEN RING Deluxe Edition", "price": {"currency": "INR", "initial": 499900, "final": 499900, "discount_percent": 0}}}}}


def steam_request(method, url, params=None, **kw):
    if "appdetails" in url:
        return fake_response(APP)
    if "packagedetails" in url:
        return fake_response(PKG[params["packageids"]])
    raise AssertionError(url)


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.ctx = cls.app.app_context(); cls.ctx.push()
        cls.app.config["PROBE_PURCHASE_URLS"] = False
        op.time.sleep = lambda *_: None

    def make_game(self, app_id=1245620, title="ELDEN RING"):
        g = Game.query.filter_by(steam_app_id=app_id).first()
        if not g:
            g = Game(title=title, slug=title.lower().replace(" ", "-"), steam_app_id=app_id)
            db.session.add(g); db.session.commit()
        return g

    def test_legacy_prices_are_cleared(self):
        self.assertEqual(GamePlatform.query.filter(GamePlatform.current_price.isnot(None),
                                                   GamePlatform.verify_status != "verified").count(), 0)

    def test_steam_editions_and_urls(self):
        g = self.make_game()
        with patch.object(op.requests, "request", side_effect=steam_request):
            self.assertEqual(op.verify_game(g), {"Steam": "verified"})
        offers = {e.name: e for _, e in g.verified_offers}
        self.assertEqual(offers["Standard Edition"].current_price, 1999.5)
        self.assertEqual(offers["Standard Edition"].original_price, 3999)
        self.assertEqual(offers["Standard Edition"].discount_percent, 50)
        self.assertEqual(offers["ELDEN RING Deluxe Edition"].purchase_url, "https://store.steampowered.com/sub/222")
        self.assertEqual(g.best_offer[1].name, "Standard Edition")

    def test_currency_mismatch_fails_closed(self):
        g = self.make_game()
        bad = {"1245620": {"success": True, "data": dict(APP["1245620"]["data"], package_groups=[],
               price_overview={"currency": "USD", "initial": 5999, "final": 5999, "discount_percent": 0})}}
        with patch.object(op.requests, "request", side_effect=lambda m, u, **k: fake_response(bad)):
            self.assertEqual(op.verify_game(g), {"Steam": "failed"})
        self.assertIsNone(g.best_offer)
        self.assertIsNone(g.best_price)

    def test_network_error_keeps_data_then_expires(self):
        g = self.make_game()
        with patch.object(op.requests, "request", side_effect=steam_request):
            op.verify_game(g)
        with patch.object(op.requests, "request", side_effect=op.requests.ConnectionError("down")):
            self.assertEqual(op.verify_game(g), {"Steam": "retry"})
        self.assertIsNotNone(g.best_offer)                       # still fresh
        from datetime import datetime, timedelta
        for l in g.platform_listings:
            l.last_verified_at = datetime.utcnow() - timedelta(hours=13)
        db.session.commit()
        self.assertIsNone(g.best_offer)                          # too old -> hidden
        op.expire_stale_prices()
        self.assertIsNone(g.platform_listings[0].current_price)

    def test_reconcile_mismatch_is_not_shown(self):
        g = self.make_game(999, "Other Game")
        data = {"999": {"success": True, "data": {"type": "game", "name": "Other Game",
                "price_overview": {"currency": "INR", "initial": 100000, "final": 100000, "discount_percent": 0},
                "package_groups": [{"subs": [{"packageid": 333}]}]}}}
        pkg = {"333": {"success": True, "data": {"name": "Other Game", "price": {"currency": "INR", "initial": 90000, "final": 90000, "discount_percent": 0}}}}
        req = lambda m, u, params=None, **k: fake_response(data if "appdetails" in u else {"333": pkg["333"]})
        with patch.object(op.requests, "request", side_effect=req):
            self.assertEqual(op.verify_game(g), {"Steam": "retry"})
        self.assertIsNone(g.best_offer)

    def test_xbox_and_epic_parsers(self):
        xbox = {"Products": [{"ProductId": "9P9XBTMQQ2XZ", "LocalizedProperties": [{"ProductTitle": "ELDEN RING"}],
                "DisplaySkuAvailabilities": [{"Availabilities": [{"Actions": ["Purchase"],
                "OrderManagementData": {"Price": {"CurrencyCode": "INR", "ListPrice": 2999.0, "MSRP": 3999.0}}}]}]}]}
        with patch.object(op.requests, "request", return_value=fake_response(xbox)):
            r = op.fetch_xbox("9P9XBTMQQ2XZ", "IN", "en-IN", "INR")
        e = r.editions[0]
        self.assertEqual((e.current, e.original, e.discount), (2999.0, 3999.0, 25))
        self.assertTrue(op.validate_official_url("Xbox Store", e.url))
        epic = {"data": {"Catalog": {"searchStore": {"elements": [
            {"title": "Game", "id": "o1", "offerType": "BASE_GAME", "productSlug": "game/home",
             "price": {"totalPrice": {"discountPrice": 99900, "originalPrice": 199900, "currencyCode": "INR", "currencyInfo": {"decimals": 2}}}},
            {"title": "Game DLC", "id": "o2", "offerType": "ADD_ON", "productSlug": "game-dlc", "price": {"totalPrice": {}}}]}}}}
        with patch.object(op.requests, "request", return_value=fake_response(epic)):
            r = op.fetch_epic("ns", "IN", "INR")
        self.assertEqual([(e.name, e.current, e.url) for e in r.editions],
                         [("Game", 999.0, "https://store.epicgames.com/en-US/p/game")])

    def test_url_validation(self):
        v = op.validate_official_url
        self.assertTrue(v("Steam", "https://store.steampowered.com/app/1245620/ELDEN_RING/"))
        self.assertFalse(v("Steam", "https://store.steampowered.com/search/?term=elden"))
        self.assertFalse(v("Steam", "https://store.steampowered.com/"))
        self.assertFalse(v("GOG", "https://www.cheapshark.com/redirect?dealID=abc"))
        self.assertTrue(v("Xbox Store", "https://www.xbox.com/en-IN/games/store/elden-ring/9P9XBTMQQ2XZ"))
        self.assertFalse(v("Epic Games Store", "https://store.epicgames.com/en-US/browse?q=elden"))

    def test_pages_render(self):
        g = self.make_game()
        with patch.object(op.requests, "request", side_effect=steam_request):
            op.verify_game(g)
        c = self.app.test_client()
        html = c.get("/compare?sort=discount").get_data(as_text=True)
        self.assertIn("Buy Now on Steam", html); self.assertIn("₹1,999.50", html)
        html = c.get(f"/game/{g.slug}").get_data(as_text=True)
        self.assertIn("ELDEN RING Deluxe Edition", html); self.assertIn("store.steampowered.com/sub/222", html)
        for path in ["/", "/compare?sort=price_low&platform=Steam", "/deals/", "/deals/free-games", "/api/search?q=elden"]:
            self.assertEqual(c.get(path).status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
