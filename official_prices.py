"""
official_prices.py
=================================================================
Reads prices and purchase links ONLY from each game's own store.

Rules this module enforces (fail-closed):
  * A price is stored only when the store's own API returned it for the
    store's own product id (Steam app id, Xbox product id, Epic namespace).
    Titles are never searched, so another game's price can't be picked up.
  * Aggregators (CheapShark / ITAD) are NOT used for displayed prices.
  * Prices must be in the currency of the configured STORE_COUNTRY,
    otherwise they are rejected (keeps sorting/comparison honest).
  * Every Buy URL is built from ids the store returned and must match the
    strict product-page pattern for that store (no search/home pages).
  * Anything that cannot be verified is stored as NULL and shown in the UI
    as "Unable to verify price". A price older than PRICE_MAX_AGE_MINUTES
    is hidden too.

Supported price sources
  Steam            appdetails + packagedetails  (editions = Steam packages)
  Xbox Store       displaycatalog product API   (one product id per edition)
  Epic Games Store storefront GraphQL           (all offers in a namespace)
  GOG              api.gog.com product endpoint (one product id, GOG has no editions/subs)
  PlayStation / Nintendo / Ubisoft Connect: no public price API -> link-only,
  price "unable to verify" (only the purchase link is checked, never a price).
=================================================================
"""
import hashlib
import html
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher

import requests
from flask import current_app

logger = logging.getLogger("official_prices")

UA = {"User-Agent": "GameVault/2.0 (student project; official price verifier)"}
TIMEOUT = 10

STEAM, XBOX, EPIC, GOG = "Steam", "Xbox Store", "Epic Games Store", "GOG"
PLAYSTATION, NINTENDO, UBISOFT = "PlayStation Store", "Nintendo eShop", "Ubisoft Connect"
PRICE_VERIFIED_STORES = (STEAM, XBOX, EPIC, GOG)
LINK_ONLY_STORES = (PLAYSTATION, NINTENDO, UBISOFT)

COUNTRY_CURRENCY = {
    "IN": "INR", "US": "USD", "GB": "GBP", "DE": "EUR", "FR": "EUR", "ES": "EUR",
    "IT": "EUR", "AU": "AUD", "CA": "CAD", "SG": "SGD", "AE": "AED", "BR": "BRL", "JP": "JPY",
}

# Strict "exact product page" patterns. Search pages, homepages and
# aggregator redirects can never match.
OFFICIAL_URL_PATTERNS = {
    STEAM: re.compile(r"^https://store\.steampowered\.com/(app|sub|bundle)/\d+(/[^/?#]*)?/?$"),
    EPIC: re.compile(r"^https://store\.epicgames\.com/[a-z]{2}(?:-[A-Za-z]{2,4})?/p/[a-z0-9][a-z0-9-]*/?$"),
    XBOX: re.compile(r"^https://www\.xbox\.com/[a-z]{2}-[A-Za-z]{2}/games/store/[^/?#]+/[0-9A-Za-z]{12}/?$"),
    PLAYSTATION: re.compile(r"^https://store\.playstation\.com/[a-z]{2}-[a-z]{2}/(product|concept)/[A-Za-z0-9._-]+/?$"),
    NINTENDO: re.compile(r"^https://www\.nintendo\.com/(?:us|[a-z]{2}-[a-z]{2})/store/products/[a-z0-9-]+/?$"),
    GOG: re.compile(r"^https://www\.gog\.com/(?:[a-z]{2}/)?game/[a-z0-9_]+/?$"),
    UBISOFT: re.compile(r"^https://store\.ubi\.com/[a-z]{2}-[a-z]{2}/(game|p)/[a-z0-9-]+/?$", re.IGNORECASE),
}


def validate_official_url(store, url):
    """True only for a direct product page on the store's own domain."""
    pattern = OFFICIAL_URL_PATTERNS.get(store)
    return bool(pattern and url and pattern.match(url.strip()))


# ------------------------------------------------------------------
# Result types
# ------------------------------------------------------------------
class TransientError(Exception):
    """Network problem / rate limit / inconsistent read: keep old data, retry later."""


class RateLimited(TransientError):
    pass


class DefiniteFailure(Exception):
    """The store answered and the price is NOT verifiable (not found, wrong
    currency, no price published...). Old prices are cleared immediately."""


class SteamNotFound(DefiniteFailure):
    """Steam's storefront returned success:false for this app id. This is
    ambiguous by itself: Steam returns exactly this when an app genuinely
    has no store page in the region, AND when Steam is soft rate-limiting
    the caller (a known quirk - it does this instead of a real HTTP 429).
    verify_listing() disambiguates with a sanity probe before trusting it."""


@dataclass
class EditionOffer:
    key: str
    name: str
    current: float
    original: float
    currency: str
    discount: int
    url: str
    sort_order: int = 0


@dataclass
class StoreResult:
    title: str
    editions: list = field(default_factory=list)


def _cfg(key, default):
    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        return default


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "game"


def identity_ok(official_title, game_title, aliases=()):
    """Guards manually-registered ids (Xbox/Epic): the official title must
    resemble the game we think we are pricing."""
    o = _norm(official_title)
    for cand in [game_title, *aliases]:
        c = _norm(cand)
        if not c or not o:
            continue
        if c in o or o in c or SequenceMatcher(None, o, c).ratio() >= 0.6:
            return True
    return False


def _get_json(url, params=None, method="GET", json_body=None):
    try:
        resp = requests.request(method, url, params=params, json=json_body,
                                headers=UA, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise TransientError(f"network error: {exc}")
    if resp.status_code == 429:
        raise RateLimited("rate limited by store")
    if resp.status_code >= 500:
        raise TransientError(f"store returned HTTP {resp.status_code}")
    if resp.status_code == 404:
        raise DefiniteFailure("product not found on the official store")
    if resp.status_code >= 400:
        raise TransientError(f"store returned HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        raise TransientError("store returned non-JSON response")


def _check_currency(currency, expected):
    if expected and currency != expected:
        raise DefiniteFailure(
            f"store returned {currency} but region {_cfg('STORE_COUNTRY', 'IN')} requires {expected}"
        )


# ------------------------------------------------------------------
# Steam
# ------------------------------------------------------------------
def _strip_html(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


# Free-to-play apps that unquestionably have a store page in every Steam
# region. If Steam claims THESE apps don't exist either, the problem is
# Steam's soft rate limit, not real per-game removal.
STEAM_SANITY_APPIDS = (730, 570, 440)  # Counter-Strike 2, Dota 2, Team Fortress 2
# Steam's soft rate limit is flaky, not all-or-nothing: a single probe can
# succeed by chance even while real requests are being throttled, so one
# shot is not enough to trust. Take a majority vote across several attempts
# using different apps to reduce the chance of a lucky false-positive.
# We probe STEAM_SANITY_ATTEMPTS times total, cycling through the app ids.
STEAM_SANITY_ATTEMPTS = 5
STEAM_SANITY_RETRY_DELAY = 1.0
STEAM_SANITY_TTL_HEALTHY = timedelta(seconds=30)
# Once we've confirmed Steam is actually struggling, stay cautious longer
# so a lucky probe a few seconds later doesn't immediately re-trust it and
# let another wave of real prices get wrongly wiped.
STEAM_SANITY_TTL_UNHEALTHY = timedelta(seconds=180)
_steam_sanity_cache = {"ok": True, "checked_at": None, "country": None}


def _steam_probe_once(app_id, country):
    try:
        payload = _get_json("https://store.steampowered.com/api/appdetails",
                            params={"appids": app_id, "cc": country.lower(), "l": "english"})
    except TransientError:
        return False
    entry = (payload or {}).get(str(app_id))
    return bool(entry and entry.get("success"))


def _steam_is_healthy(country):
    """Cheaply check whether Steam is actually answering right now, so a
    'not found' for some other app id can be trusted. Cached briefly so a
    string of failures during a real block doesn't hammer Steam further."""
    now = datetime.utcnow()
    cached_at = _steam_sanity_cache["checked_at"]
    ttl = STEAM_SANITY_TTL_HEALTHY if _steam_sanity_cache["ok"] else STEAM_SANITY_TTL_UNHEALTHY
    if cached_at and _steam_sanity_cache["country"] == country and now - cached_at < ttl:
        return _steam_sanity_cache["ok"]
    votes = []
    # Cycle through all sanity app IDs for STEAM_SANITY_ATTEMPTS probes total.
    # Using modulo ensures we spread across multiple apps rather than repeating
    # the same one, reducing the chance that a single lucky response skews the
    # majority vote during a partial soft rate-limit.
    for i in range(STEAM_SANITY_ATTEMPTS):
        app_id = STEAM_SANITY_APPIDS[i % len(STEAM_SANITY_APPIDS)]
        if i:
            time.sleep(STEAM_SANITY_RETRY_DELAY)
        votes.append(_steam_probe_once(app_id, country))
    # Require a SUPERMAJORITY (>= 2/3) to declare Steam healthy, so a single
    # lucky probe during a rate-limit session doesn't cause a false positive.
    ok = sum(votes) >= max(2, round(len(votes) * 2 / 3))
    _steam_sanity_cache.update(ok=ok, checked_at=now, country=country)
    return ok


def fetch_steam(app_id, country, expected_currency):
    cc = country.lower()
    payload = _get_json("https://store.steampowered.com/api/appdetails",
                        params={"appids": app_id, "cc": cc, "l": "english"})
    entry = (payload or {}).get(str(app_id))
    if not entry or not entry.get("success"):
        raise SteamNotFound(f"Steam has no store page for app {app_id} in region {country}")
    data = entry["data"]
    if data.get("type") != "game":
        raise DefiniteFailure(f"Steam app {app_id} is not a game (type={data.get('type')})")

    title = (data.get("name") or "").strip()
    app_url = f"https://store.steampowered.com/app/{app_id}"

    if data.get("is_free"):
        return StoreResult(title, [EditionOffer(
            key=f"app{app_id}", name="Free to Play", current=0.0, original=0.0,
            currency=expected_currency or "USD", discount=0, url=app_url)])

    overview = data.get("price_overview")
    subs = [s for g in data.get("package_groups", []) for s in g.get("subs", [])]
    if not subs and not overview:
        raise DefiniteFailure("Steam publishes no price for this app (unreleased or not purchasable)")

    editions = []
    if not subs:  # single purchase option straight from the app
        _check_currency(overview["currency"], expected_currency)
        editions.append(EditionOffer(
            key=f"app{app_id}", name="Standard Edition",
            current=overview["final"] / 100, original=overview["initial"] / 100,
            currency=overview["currency"], discount=int(overview.get("discount_percent", 0)),
            url=app_url))
    else:
        for order, sub in enumerate(subs):
            pid = str(sub["packageid"])
            pkg = _get_json("https://store.steampowered.com/api/packagedetails",
                            params={"packageids": pid, "cc": cc, "l": "english"})
            pentry = (pkg or {}).get(pid) or {}
            pdata = pentry.get("data") or {}
            price = pdata.get("price")
            if not pentry.get("success") or not price:
                continue  # no official price for this package -> not listed
            _check_currency(price["currency"], expected_currency)
            name = (pdata.get("name") or "").strip()
            if not name or name.lower().startswith("sub "):
                name = re.sub(r"\s+-\s+[^-]*\d[^-]*$", "", _strip_html(sub.get("option_text", "")))
            if _norm(name) == _norm(title) or not name:
                name = "Standard Edition"
            editions.append(EditionOffer(
                key=f"sub{pid}", name=name,
                current=price["final"] / 100, original=price["initial"] / 100,
                currency=price["currency"], discount=int(price.get("discount_percent", 0)),
                url=app_url if len(subs) == 1 else f"https://store.steampowered.com/sub/{pid}",
                sort_order=order))
            time.sleep(0.25)  # be polite to Steam's rate limit

    if not editions:
        raise DefiniteFailure("no Steam package returned an official price")

    # Reconcile with the app page's own headline price: if none of the
    # packages matches it, the read was inconsistent (e.g. price changed
    # mid-request) -> retry later instead of showing a doubtful number.
    if overview and not any(abs(e.current - overview["final"] / 100) < 0.005 for e in editions):
        raise TransientError("package prices did not reconcile with the app price; will retry")

    editions.sort(key=lambda e: (e.current, e.sort_order))
    return StoreResult(title, editions)


# ------------------------------------------------------------------
# Xbox (Microsoft display catalog). store_product_id = "ID1,ID2,..." -
# one 12-character product id per edition.
# ------------------------------------------------------------------
def fetch_xbox(product_ids, country, locale, expected_currency):
    ids = [p.strip() for p in product_ids.split(",") if p.strip()]
    payload = _get_json("https://displaycatalog.mp.microsoft.com/v7.0/products",
                        params={"bigIds": ",".join(ids), "market": country,
                                "languages": locale, "MS-CV": "DGU1mcuYo0WMMp+F.1"})
    products = {p.get("ProductId", "").upper(): p for p in (payload or {}).get("Products", [])}
    editions, title = [], ""
    for order, pid in enumerate(ids):
        prod = products.get(pid.upper())
        if not prod:
            raise DefiniteFailure(f"Xbox product {pid} not found in market {country}")
        name = ((prod.get("LocalizedProperties") or [{}])[0].get("ProductTitle") or "").strip()
        title = title or name
        chosen = None
        for sku in prod.get("DisplaySkuAvailabilities", []):
            for av in sku.get("Availabilities", []):
                if "Purchase" in (av.get("Actions") or []) and \
                        (av.get("OrderManagementData") or {}).get("Price"):
                    chosen = av["OrderManagementData"]["Price"]
                    break
            if chosen:
                break
        if not chosen:
            raise DefiniteFailure(f"Xbox product {pid} has no purchasable price in market {country}")
        _check_currency(chosen["CurrencyCode"], expected_currency)
        cur, msrp = float(chosen["ListPrice"]), float(chosen.get("MSRP") or chosen["ListPrice"])
        msrp = max(msrp, cur)
        editions.append(EditionOffer(
            key=pid.upper(), name=name or "Standard Edition", current=cur, original=msrp,
            currency=chosen["CurrencyCode"],
            discount=round((1 - cur / msrp) * 100) if msrp > cur else 0,
            url=f"https://www.xbox.com/{locale}/games/store/{_slug(name)}/{pid.upper()}",
            sort_order=order))
    return StoreResult(title, editions)


# ------------------------------------------------------------------
# Epic (storefront GraphQL). store_product_id = catalog namespace; every
# base-game/edition offer in that namespace becomes an edition.
# ------------------------------------------------------------------
_EPIC_QUERY = """
query search($namespace:String!,$country:String!,$locale:String){
  Catalog{ searchStore(namespace:$namespace,country:$country,locale:$locale,count:40){
    elements{ title id offerType productSlug urlSlug
      price(country:$country){ totalPrice{ discountPrice originalPrice currencyCode currencyInfo{ decimals } } } } } }
}"""


def fetch_epic(namespace, country, expected_currency):
    payload = _get_json("https://store.epicgames.com/graphql", method="POST",
                        json_body={"query": _EPIC_QUERY,
                                   "variables": {"namespace": namespace, "country": country, "locale": "en-US"}})
    try:
        elements = payload["data"]["Catalog"]["searchStore"]["elements"]
    except (KeyError, TypeError):
        raise TransientError("unexpected Epic response shape")
    editions, title = [], ""
    for order, el in enumerate(elements):
        if el.get("offerType") not in ("BASE_GAME", "EDITION", "BUNDLE"):
            continue
        slug = (el.get("productSlug") or el.get("urlSlug") or "").strip("/")
        slug = re.sub(r"/home$", "", slug)
        url = f"https://store.epicgames.com/en-US/p/{slug}"
        total = (((el.get("price") or {}).get("totalPrice")) or {})
        if not slug or not validate_official_url(EPIC, url) or "discountPrice" not in total:
            continue
        dec = 10 ** int((total.get("currencyInfo") or {}).get("decimals", 2))
        _check_currency(total["currencyCode"], expected_currency)
        cur, orig = total["discountPrice"] / dec, total["originalPrice"] / dec
        title = title or el.get("title", "")
        editions.append(EditionOffer(
            key=el["id"], name=el.get("title") or "Standard Edition", current=cur, original=max(orig, cur),
            currency=total["currencyCode"],
            discount=round((1 - cur / orig) * 100) if orig > cur else 0, url=url, sort_order=order))
    if not editions:
        raise DefiniteFailure("Epic returned no purchasable offer for this namespace")
    return StoreResult(title, editions)


# ------------------------------------------------------------------
# GOG (api.gog.com). store_product_id = numeric GOG catalog id.
# GOG sells one edition per catalog id (no packages/subs like Steam).
# ------------------------------------------------------------------
def fetch_gog(product_id, country, expected_currency):
    currency = expected_currency or "USD"
    payload = _get_json(f"https://api.gog.com/products/{product_id}",
                        params={"expand": "price", "currency": currency, "country": country})
    if not payload or "title" not in payload:
        raise DefiniteFailure(f"GOG has no product {product_id}")
    title = (payload.get("title") or "").strip()
    price = payload.get("price") or (payload.get("_embedded") or {}).get("price")
    if not price:
        raise DefiniteFailure(f"GOG publishes no price for product {product_id} (unreleased, "
                              f"region-unavailable, or free)")
    got_currency = price.get("currency") or currency
    _check_currency(got_currency, expected_currency)
    try:
        current = float(price["finalAmount"])
        original = float(price.get("baseAmount") or price["finalAmount"])
    except (KeyError, TypeError, ValueError):
        raise TransientError("unexpected GOG price response shape")
    # Prefer GOG's own slug if the API returns one; only fall back to
    # deriving it from the title (which can occasionally mismatch GOG's
    # real URL, e.g. for titles with punctuation GOG strips differently).
    slug = (payload.get("slug") or "").strip("/")
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or f"product-{product_id}"
    url = f"https://www.gog.com/game/{slug}"
    discount = round((1 - current / original) * 100) if original > current else 0
    return StoreResult(title, [EditionOffer(
        key=f"gog{product_id}", name="Standard Edition", current=current, original=max(original, current),
        currency=got_currency, discount=discount, url=url)])


# ------------------------------------------------------------------
# Purchase-link probe
# ------------------------------------------------------------------
def probe_url(url):
    """True = page exists, False = definitely gone (404/410), None = unknown."""
    if not _cfg("PROBE_PURCHASE_URLS", True):
        return True
    try:
        resp = requests.get(url, headers=UA, timeout=TIMEOUT, allow_redirects=True, stream=True)
        resp.close()
    except requests.RequestException:
        return None
    if resp.status_code in (404, 410):
        return False
    return True if resp.status_code < 400 else None


# ------------------------------------------------------------------
# Applying a result to the database
# ------------------------------------------------------------------
def _get_platform(name):
    from extensions import db
    from models import Platform
    from store_apis import PLATFORM_BRAND_COLORS
    p = Platform.query.filter_by(name=name).first()
    if not p:
        p = Platform(name=name, brand_color=PLATFORM_BRAND_COLORS.get(name, "#00f5ff"))
        db.session.add(p)
        db.session.flush()
    return p


def _clear_prices(listing, status, error):
    listing.verify_status = status
    listing.verify_error = (error or "")[:255]
    listing.current_price = listing.original_price = None
    listing.discount_percent = 0
    for ed in listing.editions:
        ed.current_price = ed.original_price = None
        ed.discount_percent = 0


def _sync_deal(game, listing):
    from extensions import db
    from models import Deal
    existing = Deal.query.filter_by(game_id=game.id, platform_id=listing.platform_id,
                                    deal_type="discount").first()
    if listing.discount_percent and listing.discount_percent > 0:
        if existing:
            existing.discount_percent = listing.discount_percent
        else:
            db.session.add(Deal(game_id=game.id, platform_id=listing.platform_id,
                                deal_type="discount", discount_percent=listing.discount_percent))
    elif existing:
        db.session.delete(existing)


def _apply_success(game, listing, result):
    from extensions import db
    from models import Edition, PriceHistory
    now = datetime.utcnow()
    seen = set()
    for offer in result.editions:
        if not validate_official_url(listing.platform.name, offer.url):
            logger.warning("rejecting non-official URL %s", offer.url)
            continue
        ed = next((e for e in listing.editions if e.edition_key == offer.key), None)
        if not ed:
            ed = Edition(listing_id=listing.id, edition_key=offer.key, name=offer.name)
            db.session.add(ed)
            listing.editions.append(ed)
        url_changed = ed.purchase_url != offer.url
        ed.name, ed.sort_order = offer.name, offer.sort_order
        ed.current_price, ed.original_price = offer.current, offer.original
        ed.currency, ed.discount_percent = offer.currency, offer.discount
        ed.purchase_url, ed.is_available = offer.url, True
        ed.last_verified_at = now
        if url_changed or not ed.url_verified_at or now - ed.url_verified_at > timedelta(hours=24):
            alive = probe_url(offer.url)
            if alive is False:
                ed.is_available, ed.url_verified_at = False, None
                ed.current_price = ed.original_price = None
            elif alive is True:
                ed.url_verified_at = now
            elif url_changed:          # unknown result on a brand-new URL
                ed.url_verified_at = None
        seen.add(offer.key)
    for ed in listing.editions:        # editions the store no longer sells
        if ed.edition_key not in seen:
            ed.is_available, ed.current_price, ed.original_price = False, None, None

    live = [e for e in listing.editions if e.current_price is not None and e.is_available and e.link_is_verified]
    if not live:
        _clear_prices(listing, "failed", "no edition with a verifiable price and purchase link")
        return
    cheapest = min(live, key=lambda e: e.current_price)
    listing.current_price, listing.original_price = cheapest.current_price, cheapest.original_price
    listing.discount_percent, listing.price_currency = cheapest.discount_percent, cheapest.currency
    listing.store_url = cheapest.purchase_url
    listing.in_stock, listing.source = True, listing.platform.name.lower().split()[0]
    listing.last_verified_at, listing.verify_status, listing.verify_error = now, "verified", ""

    last = (PriceHistory.query.filter_by(game_id=game.id, platform_id=listing.platform_id, verified=True)
            .order_by(PriceHistory.recorded_at.desc()).first())
    if not last or last.price != listing.current_price or now - last.recorded_at > timedelta(hours=24):
        db.session.add(PriceHistory(game_id=game.id, platform_id=listing.platform_id,
                                    price=listing.current_price, verified=True))
    _sync_deal(game, listing)


def verify_listing(listing):
    """Re-verify ONE store listing against its official store.
    Returns 'verified' | 'unverified' | 'failed' | 'retry'. Never raises
    except RateLimited (so batch runs can stop)."""
    from extensions import db
    game, store = listing.game, listing.platform.name
    country = _cfg("STORE_COUNTRY", "IN")
    locale = _cfg("STORE_LOCALE", "en-IN")
    expected = COUNTRY_CURRENCY.get(country)
    try:
        if store == STEAM and listing.store_product_id:
            result = fetch_steam(int(listing.store_product_id), country, expected)
        elif store == XBOX and listing.store_product_id:
            result = fetch_xbox(listing.store_product_id, country, locale, expected)
            if not identity_ok(result.title, game.title, game.alias_list):
                raise DefiniteFailure(f"official title '{result.title}' does not match '{game.title}'")
        elif store == EPIC and listing.store_product_id:
            result = fetch_epic(listing.store_product_id, country, expected)
            if not identity_ok(result.title, game.title, game.alias_list):
                raise DefiniteFailure(f"official title '{result.title}' does not match '{game.title}'")
        elif store == GOG and listing.store_product_id:
            result = fetch_gog(listing.store_product_id, country, expected)
            if not identity_ok(result.title, game.title, game.alias_list):
                raise DefiniteFailure(f"official title '{result.title}' does not match '{game.title}'")
        else:
            # PlayStation / Nintendo / anything without a price API: only the
            # link is checked; the price is honestly "unable to verify".
            now = datetime.utcnow()
            for ed in listing.editions:
                if not validate_official_url(store, ed.purchase_url):
                    ed.url_verified_at = None
                    continue
                alive = probe_url(ed.purchase_url)
                ed.url_verified_at = now if alive is True else (None if alive is False else ed.url_verified_at)
                ed.current_price = ed.original_price = None
            _clear_prices(listing, "unverified",
                          "No public official price API for this store - price cannot be verified")
            db.session.commit()
            return "unverified"
    except RateLimited:
        db.session.rollback()
        raise
    except SteamNotFound as exc:
        if _steam_is_healthy(country):
            # Steam is answering fine for other apps.
            # However: if this listing was previously verified (i.e. it had a
            # confirmed price in the past), a single 'not found' response is
            # still suspicious — Steam occasionally returns false negatives for
            # individual app IDs without the sanity apps being affected.
            # Treat such cases as transient so the price is preserved for the
            # next re-verify cycle rather than being wiped immediately.
            if listing.verify_status == "verified" and listing.current_price is not None:
                listing.verify_error = (
                    f"{exc} (was previously verified; treating as transient — will retry)"
                )[:255]
                db.session.commit()
                return "retry"
            # First-time check (never verified before), or already cleared:
            # trust Steam's 'not found' response.
            _clear_prices(listing, "failed", str(exc))
            db.session.commit()
            return "failed"
        # Steam's own sanity-check apps also came back "not found" — Steam
        # itself is misbehaving (soft rate limit), so don't trust this
        # result. Keep the old price and stop the batch, same as a real 429.
        listing.verify_error = f"{exc} (Steam sanity probe also failed - likely soft rate-limited, not a real removal)"
        db.session.commit()
        raise RateLimited("Steam's storefront API appears to be soft rate-limiting this session")
    except TransientError as exc:
        listing.verify_error = str(exc)[:255]   # keep old data; expiry handles staleness
        db.session.commit()
        return "retry"
    except DefiniteFailure as exc:
        _clear_prices(listing, "failed", str(exc))
        db.session.commit()
        return "failed"
    _apply_success(game, listing, result)
    db.session.commit()
    return listing.verify_status


def ensure_steam_listing(game):
    from extensions import db
    from models import GamePlatform
    if not game.steam_app_id:
        return None
    platform = _get_platform(STEAM)
    listing = GamePlatform.query.filter_by(game_id=game.id, platform_id=platform.id).first()
    if not listing:
        listing = GamePlatform(game_id=game.id, platform_id=platform.id)
        db.session.add(listing)
    listing.store_product_id = str(game.steam_app_id)
    db.session.flush()
    return listing


def verify_game(game):
    """Verify every store listing of one game. Returns {store: status}."""
    from extensions import db
    ensure_steam_listing(game)
    out = {}
    for listing in list(game.platform_listings):
        if listing.store_product_id or listing.editions:
            out[listing.platform.name] = verify_listing(listing)
        else:
            # Legacy/seeded row with no official product id: nothing can back
            # its price, so it must never be shown.
            _clear_prices(listing, "unverified", "no official product id registered")
    game.last_synced_at = datetime.utcnow()
    db.session.commit()
    return out


def verify_all(sleep=1.5, progress=None):
    """Verify every game. Stops early (and says so) if a store rate-limits."""
    from models import Game
    counts = {"verified": 0, "failed": 0, "unverified": 0, "retry": 0, "rate_limited": False}
    for game in Game.query.all():
        try:
            for status in verify_game(game).values():
                counts[status] = counts.get(status, 0) + 1
        except RateLimited:
            counts["rate_limited"] = True
            break
        if progress:
            progress(game)
        time.sleep(sleep)
    return counts


def expire_stale_prices():
    """Hide prices whose last verification is older than PRICE_MAX_AGE_MINUTES."""
    from extensions import db
    from models import GamePlatform
    cutoff = datetime.utcnow() - timedelta(minutes=_cfg("PRICE_MAX_AGE_MINUTES", 720))
    stale = GamePlatform.query.filter(
        GamePlatform.verify_status == "verified",
        (GamePlatform.last_verified_at.is_(None)) | (GamePlatform.last_verified_at < cutoff)).all()
    for listing in stale:
        _clear_prices(listing, "stale", "price not re-verified recently")
    if stale:
        db.session.commit()
    return len(stale)


def register_official_product(game, store, product_id=None, url=None, edition_name=None):
    """Attach an official store identity to a game.
    Steam: automatic (steam_app_id). Xbox: product_id(s). Epic: namespace.
    GOG: numeric product id (price verified). PlayStation/Nintendo/Ubisoft
    Connect: url= exact product page (link-only, price stays unverifiable)."""
    from extensions import db
    from models import GamePlatform, Edition
    platform = _get_platform(store)
    listing = GamePlatform.query.filter_by(game_id=game.id, platform_id=platform.id).first()
    if not listing:
        listing = GamePlatform(game_id=game.id, platform_id=platform.id)
        db.session.add(listing)
        db.session.flush()
    if store in PRICE_VERIFIED_STORES:
        if not product_id:
            raise ValueError(f"{store} needs a product id")
        listing.store_product_id = product_id.strip()
    else:
        if not validate_official_url(store, url):
            raise ValueError("URL is not an exact official product page for " + store)
        key = hashlib.sha1(url.encode()).hexdigest()[:16]
        if not any(e.edition_key == key for e in listing.editions):
            listing.editions.append(Edition(edition_key=key, name=edition_name or "Standard Edition",
                                            purchase_url=url))
    listing.verify_status = "unverified"
    db.session.commit()
    return listing
