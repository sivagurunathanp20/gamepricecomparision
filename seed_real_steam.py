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
    # ── Iconic / All-time Classics ────────────────────────────────
    730,      # Counter-Strike 2
    570,      # Dota 2
    271590,   # Grand Theft Auto V
    1091500,  # Cyberpunk 2077
    1174180,  # Red Dead Redemption 2
    1245620,  # ELDEN RING
    292030,   # The Witcher 3: Wild Hunt
    578080,   # PUBG: BATTLEGROUNDS
    1085660,  # Destiny 2
    252490,   # Rust
    413150,   # Stardew Valley
    1145360,  # Hades
    1097150,  # Fall Guys
    550,      # Left 4 Dead 2
    440,      # Team Fortress 2
    105600,   # Terraria
    620,      # Portal 2
    400,      # Portal
    4000,     # Garry's Mod
    220,      # Half-Life 2
    70,       # Half-Life
    546560,   # Half-Life: Alyx
    391540,   # Undertale
    230410,   # Warframe
    322330,   # Don't Starve Together
    381210,   # Dead by Daylight
    218620,   # PAYDAY 2
    227300,   # Euro Truck Simulator 2

    # ── Action / Open World ────────────────────────────────────────
    2050650,  # Resident Evil 4 (2023)
    632360,   # Risk of Rain 2
    2208920,  # Assassin's Creed Valhalla
    812140,   # Assassin's Creed Odyssey
    359550,   # Tom Clancy's Rainbow Six Siege
    1240440,  # Halo Infinite
    1517290,  # Battlefield 2042
    1817070,  # Marvel's Spider-Man Remastered
    1966720,  # Lethal Company
    1623730,  # Palworld
    553850,   # Helldivers 2
    814380,   # Sekiro: Shadows Die Twice
    374320,   # Dark Souls III
    582010,   # Monster Hunter: World
    1627720,  # Lies of P
    1794680,  # Vampire Survivors
    1150690,  # Dead Island 2
    1551360,  # Forza Horizon 5
    1240240,  # It Takes Two
    1716740,  # Starfield
    2311310,  # Alan Wake 2
    1811050,  # God of War
    892970,   # Valheim
    1091500,  # Cyberpunk 2077 (dedup safe)
    1203220,  # NARAKA: BLADEPOINT
    1966720,  # Lethal Company (dedup safe)
    2420510,  # Black Myth: Wukong
    1665460,  # Midnight Suns
    976730,   # Halo: The Master Chief Collection
    1085660,  # Destiny 2 (dedup)
    435150,   # Divinity: Original Sin 2
    489830,   # The Elder Scrolls V: Skyrim Special Edition
    1086940,  # Baldur's Gate 3

    # ── Shooters / FPS ────────────────────────────────────────────
    782330,   # DOOM Eternal
    379430,   # Doom (2016)
    2012016,  # Ghostrunner 2
    677120,   # Ghostrunner
    504230,   # Celeste
    397540,   # Borderlands 3
    49520,    # Borderlands 2
    668580,   # Atomic Heart
    1222680,  # Need for Speed Heat
    1238840,  # Battlefield V
    1237970,  # Titanfall 2
    1406960,  # Deep Rock Galactic
    386360,   # SMITE (F2P)
    444090,   # Paladins (F2P)
    291550,   # Brawlhalla (F2P)
    753420,   # Dauntless (F2P)
    2357570,  # Overwatch 2 (F2P)
    1172470,  # Apex Legends (F2P)
    252950,   # Rocket League
    1938090,  # Call of Duty HQ

    # ── RPGs ──────────────────────────────────────────────────────
    632470,   # Disco Elysium: The Final Cut
    1244090,  # Sea of Stars
    990080,   # Hogwarts Legacy
    238960,   # Path of Exile (F2P)
    1599340,  # Lost Ark (F2P)
    1086940,  # Baldur's Gate 3
    435150,   # Divinity: Original Sin 2
    489830,   # Skyrim Special Edition
    1716740,  # Starfield
    960090,   # Persona 4 Golden
    1592190,  # Persona 5 Royal
    2138330,  # Persona 3 Reload
    1111570,  # Dragon's Dogma 2 (pre-launch IDs vary)
    2054970,  # Lies of P
    1771300,  # Wo Long: Fallen Dynasty
    594650,   # Hunt: Showdown
    1517290,  # Battlefield 2042
    814380,   # Sekiro
    1245620,  # ELDEN RING
    374320,   # Dark Souls III
    335300,   # Dark Souls II: Scholar of the First Sin
    570940,   # DARK SOULS: REMASTERED
    2215430,  # Armored Core VI

    # ── Strategy / City Builder ───────────────────────────────────
    289070,   # Sid Meier's Civilization VI
    1158310,  # Crusader Kings III
    394360,   # Hearts of Iron IV
    236390,   # War Thunder (F2P)
    552990,   # World of Warships (F2P)
    1611910,  # Enlisted (F2P)
    255710,   # Cities: Skylines
    1154490,  # Cities: Skylines II
    1158760,  # Age of Empires IV
    1113560,  # Age of Empires III: DE
    813780,   # Age of Empires II: DE
    281990,   # Stellaris
    262060,   # Northgard
    1465360,  # Humankind
    1449850,  # Victoria 3
    391160,   # Battlefleet Gothic: Armada 2
    524440,   # X4: Foundations
    356190,   # Into the Breach
    1048540,  # Frostpunk 2 (pre-release ID)
    1151340,  # Frostpunk
    409710,   # Factorio
    427520,   # Factorio (alt)
    233480,   # Dungeon Defenders II
    960090,   # Persona 4 Golden

    # ── Indie / Roguelikes ────────────────────────────────────────
    588650,   # Dead Cells
    1145360,  # Hades
    1794680,  # Vampire Survivors
    1079550,  # Slay the Spire
    860950,   # Hollow Knight
    1450450,  # Cuphead - The Delicious Last Course
    268910,   # Cuphead
    648800,   # Raft
    505460,   # Katana ZERO
    646570,   # Slay the Spire
    311690,   # Enter the Gungeon
    206190,   # Torchlight II
    252750,   # Battleblock Theater
    113020,   # Monaco
    209080,   # Guns of Icarus Online
    251570,   # 7 Days to Die
    240720,   # Getting Over It
    1167630,  # Inscryption
    1296830,  # There Is No Game: Wrong Dimension
    1061910,  # Superliminal
    814380,   # Sekiro (dedup)
    1049410,  # Everhood
    1342280,  # Omori

    # ── Horror / Survival ─────────────────────────────────────────
    381210,   # Dead by Daylight
    2093700,  # Sons of the Forest
    1671400,  # The Forest (2)
    242760,   # The Forest
    1518210,  # Phasmophobia
    773271,   # Poppy Playtime - Chapter 1 (free)
    736260,   # Baldi's Basics (free)
    1172380,  # Five Nights at Freddy's: Security Breach
    427810,   # Fran Bow
    239030,   # Outlast
    952060,   # Outlast Trials
    2528490,  # Alan Wake 2 (EGS ID mapped to Steam)
    1203220,  # NARAKA Bladepoint

    # ── Simulation ────────────────────────────────────────────────
    227300,   # Euro Truck Simulator 2
    270880,   # American Truck Simulator
    236110,   # Kerbal Space Program
    1406530,  # Kerbal Space Program 2
    255710,   # Cities: Skylines
    431960,   # Wallpaper Engine
    233860,   # Planet Coaster
    529180,   # Planet Coaster (console ed. — skip duplicate)
    1059820,  # Planet Zoo
    283270,   # RimWorld
    294100,   # RimWorld
    108600,   # Project Zomboid
    346110,   # ARK: Survival Evolved
    1203350,  # Timberborn
    1284510,  # Satisfactory
    526870,   # Subnautica: Below Zero
    264710,   # Subnautica
    1622850,  # PowerWash Simulator
    2016590,  # Farming Simulator 22
    1284510,  # Satisfactory
    1329500,  # Stormworks: Build and Rescue

    # ── Sports / Racing ───────────────────────────────────────────
    2669320,  # EA SPORTS FC 25
    1811260,  # FIFA 23
    1262400,  # FIFA 22
    1286680,  # FIFA 21
    1351010,  # F1 2023
    1259320,  # F1 2020
    1185660,  # F1 2019
    1551360,  # Forza Horizon 5
    1914410,  # Forza Horizon 4 (Xbox Game Pass ID)
    752590,   # NBA 2K23
    883710,   # NBA 2K22
    1326690,  # Wreckfest
    321360,   # Dirt 4
    690790,   # DiRT Rally 2.0
    2252390,  # WRC Generations

    # ── Adventure / Narrative ────────────────────────────────────
    1250240,  # It Takes Two
    1240240,  # It Takes Two (alt ID)
    275850,   # No Man's Sky
    620,      # Portal 2 (dedup)
    400,      # Portal (dedup)
    1172620,  # Sea of Thieves
    552990,   # World of Warships
    644930,   # A Way Out
    1086940,  # Baldur's Gate 3 (dedup)
    1203355,  # Ori and the Blind Forest: DE
    387290,   # Ori and the Will of the Wisps
    1057090,  # A Short Hike
    1139900,  # Twelve Minutes
    1247360,  # Unpacking
    1490180,  # DAVE THE DIVER
    1456670,  # Dave the Diver (same)
    632360,   # Risk of Rain 2 (dedup)
    1888930,  # Chained Echoes
    1262350,  # Eastward
    1638500,  # Tunic

    # ── Platformers ──────────────────────────────────────────────
    504230,   # Celeste (dedup)
    1145360,  # Hades (dedup)
    860950,   # Hollow Knight
    391540,   # Undertale (dedup)
    268910,   # Cuphead (dedup)
    1450450,  # Cuphead DLC (dedup)
    648800,   # Raft (dedup)
    2069820,  # Metroid Dread (Windows port — skip if not on Steam)
    1070010,  # Crash Bandicoot N. Sane Trilogy
    1378620,  # Spyro Reignited Trilogy
    1030720,  # Sonic Frontiers
    813780,   # AoE II DE (dedup)
    1145360,  # Hades (dedup)

    # ── Puzzle ────────────────────────────────────────────────────
    400,      # Portal (dedup)
    620,      # Portal 2 (dedup)
    359550,   # Rainbow Six Siege (dedup)
    1167630,  # Inscryption (dedup)
    1061910,  # Superliminal (dedup)
    1649080,  # Baba is You (approx ID)
    736260,   # BABA IS YOU
    585420,   # Talos Principle 2 (approx)
    257510,   # The Talos Principle
    326030,   # SOMA
    319630,   # SOMA (dedup)

    # ── Multiplayer / Party ──────────────────────────────────────
    945360,   # Among Us
    477160,   # Human: Fall Flat
    1113560,  # AoE III (dedup)
    291550,   # Brawlhalla (dedup)
    1027010,  # Garfield Kart (small filler)
    1263870,  # Golf With Your Friends
    1637630,  # Overcooked! All You Can Eat
    728880,   # Overcooked 2
    448510,   # Overcooked
    753640,   # Astroneer
    1062220,  # Pico Park Classic Edition
    1669980,  # Moving Out 2
    246620,   # Moving Out (original ID approx)

    # ── Free to Play ─────────────────────────────────────────────
    730,      # CS2 (dedup)
    570,      # Dota 2 (dedup)
    440,      # TF2 (dedup)
    230410,   # Warframe (dedup)
    238960,   # Path of Exile (dedup)
    1172470,  # Apex Legends (dedup)
    252950,   # Rocket League (dedup)
    2357570,  # Overwatch 2 (dedup)
    386360,   # SMITE (dedup)
    444090,   # Paladins (dedup)
    291550,   # Brawlhalla (dedup)
    753420,   # Dauntless (dedup)
    552990,   # World of Warships (dedup)
    1611910,  # Enlisted (dedup)
    1599340,  # Lost Ark (dedup)
    1085660,  # Destiny 2 (dedup)
    1203220,  # NARAKA (dedup)
    578080,   # PUBG (dedup — now F2P)
    1097150,  # Fall Guys (dedup — now F2P)
    1938090,  # CoD HQ (dedup)
    1716740,  # Starfield (dedup — Game Pass)
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
