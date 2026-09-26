"""
Populates the database with REAL Steam game data — real titles, real cover
images, real descriptions, and real USD prices — pulled live from Steam's
public storefront API (no API key required).

Epic Games Store / GOG / Xbox / PlayStation don't offer a free public price
API, so those platform rows are still synthetic (a randomized variation on
the real Steam price) just so the comparison table has multiple platforms
to show. Steam's row for every game is 100% real, live data.

Requires internet access on the machine you run this on.

Usage:
    python seed_real_steam.py
    (re-run any time to refresh prices/discounts with the latest live data)
"""
import random
import time
from datetime import datetime, timedelta

import requests

from app import create_app
from extensions import db
from store_apis import PLATFORM_BRAND_COLORS, build_store_url
from models import (
    User, Category, Platform, Game, GamePlatform, Deal, PriceHistory, Review, GameAlias
)

# A curated list of well-known, real Steam App IDs across different genres.
# (Find more IDs from any store.steampowered.com/app/<id> URL. A few of the
# newer ones below are best-effort — if an ID is stale/wrong, the fetch
# just fails gracefully and that one entry is skipped, per the "one store
# failing never blocks the others" requirement.)
STEAM_APP_IDS = [
    730,      # Counter-Strike 2
    570,      # Dota 2
    271590,   # Grand Theft Auto V
    1091500,  # Cyberpunk 2077
    1174180,  # Red Dead Redemption 2
    1245620,  # ELDEN RING
    292030,   # The Witcher 3: Wild Hunt
    578080,   # PUBG: BATTLEGROUNDS
    1938090,  # Call of Duty (launcher/base app)
    1085660,  # Destiny 2
    431960,   # Wallpaper Engine
    252490,   # Rust
    1517290,  # Battlefield 2042
    1240440,  # Halo Infinite
    2050650,  # Resident Evil 4
    413150,   # Stardew Valley
    632360,   # Risk of Rain 2
    1145360,  # Hades
    1097150,  # Fall Guys
    2208920,  # Assassin's Creed Valhalla
    1222680,  # Need for Speed Heat
    2669320,  # EA SPORTS FC 25
    550,      # Left 4 Dead 2
    440,      # Team Fortress 2
    1237970,  # Titanfall 2
    236390,   # War Thunder
    # --- newly added (2nd batch) ---
    105600,   # Terraria
    620,      # Portal 2
    400,      # Portal
    4000,     # Garry's Mod
    220,      # Half-Life 2
    70,       # Half-Life
    546560,   # Half-Life: Alyx
    391540,   # Undertale
    588650,   # Dead Cells
    1794680,  # Vampire Survivors
    275850,   # No Man's Sky
    990080,   # Hogwarts Legacy
    230410,   # Warframe
    322330,   # Don't Starve Together
    381210,   # Dead by Daylight
    218620,   # PAYDAY 2
    227300,   # Euro Truck Simulator 2
    289070,   # Sid Meier's Civilization VI
    359550,   # Tom Clancy's Rainbow Six Siege
    812140,   # Assassin's Creed Odyssey
    1158310,  # Crusader Kings III
    1817070,  # Marvel's Spider-Man Remastered
    1966720,  # Lethal Company
    # --- free-to-play batch ---
    1172470,  # Apex Legends
    252950,   # Rocket League
    291550,   # Brawlhalla
    238960,   # Path of Exile
    386360,   # SMITE
    444090,   # Paladins
    753420,   # Dauntless
    552990,   # World of Warships
    2357570,  # Overwatch 2
    1203220,  # NARAKA: BLADEPOINT
    1611910,  # Enlisted
]
STEAM_APP_IDS = list(dict.fromkeys(STEAM_APP_IDS))  # de-dupe while keeping order

# Alias map: Steam App ID -> list of short names / abbreviations / nicknames
# players actually search with. This is what makes "GTAV", "CS2", "PUBG",
# "RDR2", "COD", "FC25", "NFS", "AC", "Elden", "Witcher" instantly resolve
# to the right game, on top of the fuzzy-match fallback in search.py.
GAME_ALIASES = {
    730: ["CS2", "CS 2", "CSGO", "CS:GO", "Counter Strike"],
    570: ["Dota", "Dota2", "Dota 2"],
    271590: ["GTA", "GTAV", "GTA V", "GTA 5", "GTA5"],
    1091500: ["Cyberpunk", "CP2077", "CP77"],
    1174180: ["RDR2", "RDR 2", "Red Dead 2"],
    1245620: ["Elden", "Elden Ring", "ER"],
    292030: ["Witcher", "Witcher 3", "TW3"],
    578080: ["PUBG", "PUBG:BATTLEGROUNDS", "Battlegrounds"],
    1938090: ["COD", "Call of Duty"],
    1085660: ["Destiny", "D2"],
    252490: ["Rust"],
    1517290: ["BF2042", "Battlefield", "Battlefield 2042"],
    1240440: ["Halo", "Halo Infinite"],
    2050650: ["RE4", "Resident Evil 4", "RE 4"],
    413150: ["Stardew", "SDV"],
    1145360: ["Hades"],
    1097150: ["Fall Guys", "FG"],
    2208920: ["AC", "ACV", "Assassins Creed", "Assassin's Creed"],
    1222680: ["NFS", "Need for Speed", "NFS Heat"],
    2669320: ["FIFA", "FC25", "FC 25", "EAFC"],
    550: ["L4D2", "Left 4 Dead"],
    440: ["TF2", "Team Fortress"],
    1237970: ["Titanfall", "Titanfall2"],
    4000: ["GMod", "Garrys Mod", "Garry's Mod"],
    220: ["HL2", "Half Life 2"],
    70: ["HL", "Half Life"],
    546560: ["HLA", "Half-Life Alyx", "Alyx"],
    230410: ["Warframe"],
    359550: ["R6", "R6S", "Siege", "Rainbow Six"],
    812140: ["AC Odyssey", "ACO", "Assassins Creed Odyssey"],
    1158310: ["CK3", "Crusader Kings 3"],
    1817070: ["Spiderman", "Spider-Man", "Spider Man Remastered"],
    990080: ["Hogwarts", "Hogwarts Legacy"],
    1172470: ["Apex", "Apex Legends"],
    252950: ["RL", "Rocket League"],
    238960: ["POE", "Path of Exile"],
    2357570: ["OW2", "Overwatch", "Overwatch 2"],
    1203220: ["Naraka", "Naraka Bladepoint"],
}

STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
OTHER_PLATFORMS = ["Epic Games Store", "GOG", "Ubisoft Connect", "Xbox Store", "PlayStation Store"]


def fetch_steam_game(app_id, regions=("us", "gb", "in", "de")):
    """Calls Steam's public appdetails endpoint. Tries several regional
    storefronts in order — some games (this was the actual root cause of
    GTA V showing $0 in earlier versions of this seeder) simply don't have
    a price_overview for the US storefront specifically but do for others.
    Returns the game's metadata dict, or None if every region failed
    outright. If metadata was found but NO region had a price, the caller
    is responsible for treating that as "Unavailable", never $0."""
    last_good_data = None
    for cc in regions:
        try:
            resp = requests.get(
                STEAM_APPDETAILS_URL,
                params={"appids": app_id, "cc": cc, "l": "en"},
                timeout=10,
            )
            resp.raise_for_status()
            payload = resp.json()
            entry = payload.get(str(app_id))
            if not entry or not entry.get("success"):
                continue
            data = entry["data"]
            last_good_data = last_good_data or data
            if data.get("is_free") or data.get("price_overview"):
                return data  # got real pricing (or confirmed genuinely free) — done
        except Exception as exc:
            print(f"  ! Failed to fetch app {app_id} (cc={cc}): {exc}")
            continue

    if last_good_data:
        print(f"  ! App {app_id}: metadata found but no region returned a price — will mark Unavailable")
    return last_good_data


def parse_release_date(date_str):
    for fmt in ("%d %b, %Y", "%b %d, %Y", "%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def run_seed():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        # --- Users ---
        admin = User(username="admin", email="admin@gamevault.com", is_admin=True)
        admin.set_password("Admin@123")
        demo = User(username="demo_player", email="demo@gamevault.com", is_admin=False)
        demo.set_password("Demo@123")
        db.session.add_all([admin, demo])

        # --- Platforms ---
        all_platform_names = ["Steam"] + OTHER_PLATFORMS
        platform_objs = {}
        for name in all_platform_names:
            p = Platform(name=name, brand_color=PLATFORM_BRAND_COLORS.get(name, "#00f5ff"))
            db.session.add(p)
            platform_objs[name] = p

        db.session.commit()
        category_objs = {}

        added = 0
        seen_ids = set()
        for app_id in STEAM_APP_IDS:
            if app_id in seen_ids:
                continue
            seen_ids.add(app_id)

            print(f"Fetching Steam app {app_id}...")
            data = fetch_steam_game(app_id)
            time.sleep(1.2)  # be polite to Steam's API — avoid rate limiting

            if not data or data.get("type") != "game":
                print(f"  - skipped (no data or not a game)")
                continue

            title = data.get("name", f"App {app_id}")
            slug = title.lower().replace(" ", "-").replace(":", "").replace("'", "")

            genre_name = "Action"
            genres = data.get("genres")
            if genres:
                genre_name = genres[0]["description"]
            if genre_name not in category_objs:
                cat = Category.query.filter_by(name=genre_name).first()
                if not cat:
                    cat = Category(name=genre_name, slug=genre_name.lower().replace(" ", "-"))
                    db.session.add(cat)
                    db.session.commit()
                category_objs[genre_name] = cat

            is_free = bool(data.get("is_free"))
            price_overview = data.get("price_overview")

            if is_free:
                base_price = 0.0
                current_price = 0.0
                discount = 0
                price_available = True
            elif price_overview:
                base_price = price_overview["initial"] / 100
                current_price = price_overview["final"] / 100
                discount = price_overview.get("discount_percent", 0)
                price_available = True
            else:
                # Root-cause fix: NEVER fabricate a $0 price for a paid
                # game just because Steam didn't return one. Store None —
                # the UI shows this as "Unavailable", not ₹0.
                base_price = None
                current_price = None
                discount = 0
                price_available = False

            metacritic = data.get("metacritic", {}).get("score")
            rating = round(metacritic / 20, 1) if metacritic else round(random.uniform(3.8, 4.8), 1)

            from store_apis import resolve_game_image
            game = Game(
                title=title,
                slug=slug,
                description=(data.get("short_description") or "")[:1000],
                cover_image=resolve_game_image(steam_app_id=app_id, fallback_url=data.get("header_image", ""), verify=False),
                steam_app_id=app_id,
                developer=", ".join(data.get("developers", []) or [])[:120],
                publisher=", ".join(data.get("publishers", []) or [])[:120],
                release_date=parse_release_date(data.get("release_date", {}).get("date")),
                rating=rating,
                popularity_score=random.randint(400, 1000),
                category_id=category_objs[genre_name].id,
                is_free_to_play=is_free,
            )
            db.session.add(game)
            db.session.commit()

            # --- Aliases (abbreviations/nicknames) so search finds this
            # game via "GTAV", "CS2", "PUBG", "RDR2", "COD", "FC25" etc. ---
            for alias_text in GAME_ALIASES.get(app_id, []):
                db.session.add(GameAlias(game_id=game.id, alias=alias_text))
            db.session.commit()

            # --- Real Steam price/listing (None stays None = "Unavailable") ---
            db.session.add(GamePlatform(
                game_id=game.id,
                platform_id=platform_objs["Steam"].id,
                original_price=base_price,
                current_price=current_price,
                discount_percent=discount,
                store_url=f"https://store.steampowered.com/app/{app_id}",
                in_stock=price_available,
                source="steam",
            ))

            # No invented other-store listings and no fabricated price history:
            # prices come only from the official verifier (run after seeding).
            try:
                from official_prices import ensure_steam_listing
                game_obj = Game.query.filter_by(steam_app_id=app_id).first()
                if game_obj:
                    ensure_steam_listing(game_obj)
            except Exception as exc:
                print(f"  ! could not register Steam listing: {exc}")

            # --- Deal entry if currently discounted (or free-to-play) ---
            if discount >= 10:
                db.session.add(Deal(
                    game_id=game.id,
                    platform_id=platform_objs["Steam"].id,
                    deal_type="discount",
                    discount_percent=discount,
                    expires_at=datetime.utcnow() + timedelta(days=random.randint(2, 10)),
                    is_featured=discount >= 50,
                ))
            if is_free:
                db.session.add(Deal(
                    game_id=game.id,
                    platform_id=platform_objs["Steam"].id,
                    deal_type="free",
                    discount_percent=100,
                    expires_at=None,
                    is_featured=True,
                ))

            db.session.add(Review(
                user_id=demo.id,
                game_id=game.id,
                rating=random.randint(4, 5),
                comment="Real Steam data pulled live — great pricing to track!",
            ))

            db.session.commit()
            added += 1
            price_str = f"${current_price:.2f}" if current_price is not None else "Unavailable"
            print(f"  + Added: {title} ({price_str}, -{discount}%)")

        print(f"\nDone. Added {added} real Steam games out of {len(STEAM_APP_IDS)} attempted.")

        from store_apis import itad_enabled, sync_game_from_apis
        print("\nVerifying prices + Buy links against the official stores...")
        for game in Game.query.filter(Game.steam_app_id.isnot(None)).all():
            try:
                summary = sync_game_from_apis(game)
                print(f"  {game.title}: {summary['stores_updated']} store(s) verified")
            except Exception as exc:
                print(f"  {game.title}: sync error — {exc}")


if __name__ == "__main__":
    run_seed()
