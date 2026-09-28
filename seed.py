"""
Populates the database with realistic demo data so the app looks and feels
like a live platform out of the box.

Run with:  flask --app app seed-db
"""
import random
from datetime import date, datetime, timedelta

from app import create_app
from extensions import db
from store_apis import PLATFORM_BRAND_COLORS, build_store_url
from models import (
    User, Category, Platform, Game, GamePlatform, Deal, PriceHistory, Review
)

PLATFORMS = ["Steam", "Epic Games Store", "GOG", "Ubisoft Connect", "Xbox Store", "PlayStation Store"]

CATEGORIES = ["Action", "RPG", "Adventure", "Shooter", "Strategy", "Sports", "Racing", "Simulation"]

# Real games with known Steam App IDs so CheapShark + image sync work correctly
# Last audited: 2026-09-21 — App IDs verified against SteamDB.
GAMES = [
    dict(title="Terraria",                       category="Adventure",  dev="Re-Logic",             pub="Re-Logic",           rating=4.9, popularity=790, ftp=False, appid=105600),
    dict(title="Among Us",                       category="Strategy",   dev="Innersloth",           pub="Innersloth",         rating=4.2, popularity=650, ftp=False, appid=945360),
    dict(title="Counter-Strike 2",               category="Shooter",    dev="Valve",               pub="Valve",              rating=4.0, popularity=990, ftp=True,  appid=730),
    dict(title="Dota 2",                         category="Strategy",   dev="Valve",               pub="Valve",              rating=4.2, popularity=920, ftp=True,  appid=570),
    dict(title="Team Fortress 2",                category="Shooter",    dev="Valve",               pub="Valve",              rating=4.5, popularity=880, ftp=True,  appid=440),
    dict(title="Warframe",                       category="Action",     dev="Digital Extremes",    pub="Digital Extremes",   rating=4.4, popularity=860, ftp=True,  appid=230410),
    # --- RPGs ---
    dict(title="Baldur's Gate 3",                category="RPG",        dev="Larian Studios",      pub="Larian Studios",     rating=4.9, popularity=999, ftp=False, appid=1086940),
    dict(title="Divinity: Original Sin 2",       category="RPG",        dev="Larian Studios",      pub="Larian Studios",     rating=4.9, popularity=890, ftp=False, appid=435150),
    dict(title="Skyrim Special Edition",         category="RPG",        dev="Bethesda",            pub="Bethesda",           rating=4.8, popularity=940, ftp=False, appid=489830),
    dict(title="Disco Elysium: The Final Cut",   category="RPG",        dev="ZA/UM",               pub="ZA/UM",              rating=4.8, popularity=760, ftp=False, appid=632470),
    dict(title="Sea of Stars",                   category="RPG",        dev="Sabotage Studio",     pub="Sabotage Studio",    rating=4.7, popularity=740, ftp=False, appid=1244090),
    dict(title="Hogwarts Legacy",                category="RPG",        dev="Avalanche Software",  pub="Warner Bros. Games", rating=4.5, popularity=890, ftp=False, appid=990080),
    dict(title="Starfield",                      category="RPG",        dev="Bethesda Game Studios", pub="Bethesda Softworks", rating=4.0, popularity=820, ftp=False, appid=1716740),
    dict(title="Path of Exile",                  category="RPG",        dev="Grinding Gear Games", pub="Grinding Gear Games", rating=4.4, popularity=870, ftp=True,  appid=238960),
    dict(title="Lost Ark",                       category="RPG",        dev="Smilegate RPG",       pub="Amazon Games",       rating=4.0, popularity=860, ftp=True,  appid=1599340),
    # --- Action / Souls-likes ---
    dict(title="Elden Ring",                     category="Action",     dev="FromSoftware",         pub="Bandai Namco",        rating=4.9, popularity=998, ftp=False, appid=1245620),
    dict(title="Sekiro: Shadows Die Twice",      category="Action",     dev="FromSoftware",         pub="Activision",         rating=4.8, popularity=860, ftp=False, appid=814380),
    dict(title="Dark Souls III",                 category="Action",     dev="FromSoftware",         pub="Bandai Namco",        rating=4.8, popularity=870, ftp=False, appid=374320),
    dict(title="Monster Hunter: World",          category="Action",     dev="Capcom",              pub="Capcom",             rating=4.7, popularity=910, ftp=False, appid=582010),
    dict(title="Lies of P",                      category="Action",     dev="NEOWIZ",              pub="NEOWIZ",             rating=4.5, popularity=730, ftp=False, appid=1627720),
    dict(title="Vampire Survivors",              category="Action",     dev="poncle",              pub="poncle",             rating=4.9, popularity=840, ftp=False, appid=1794680),
    dict(title="Dead Island 2",                  category="Action",     dev="Dambuster Studios",   pub="Deep Silver",        rating=4.3, popularity=700, ftp=False, appid=1150690),
    dict(title="Palworld",                       category="Action",     dev="Pocketpair",          pub="Pocketpair",         rating=4.4, popularity=950, ftp=False, appid=1623730),
    dict(title="Grand Theft Auto V",             category="Action",     dev="Rockstar Games",      pub="Rockstar Games",     rating=4.5, popularity=985, ftp=False, appid=271590),
    # --- Shooters ---
    dict(title="DOOM Eternal",                   category="Shooter",    dev="id Software",         pub="Bethesda",           rating=4.8, popularity=930, ftp=False, appid=782330),
    dict(title="Borderlands 3",                  category="Shooter",    dev="Gearbox Software",    pub="2K Games",           rating=4.3, popularity=760, ftp=False, appid=397540),
    dict(title="Apex Legends",                   category="Shooter",    dev="Respawn Entertainment", pub="EA",               rating=4.3, popularity=930, ftp=True,  appid=1172470),
    dict(title="Destiny 2",                      category="Shooter",    dev="Bungie",              pub="Bungie",             rating=4.1, popularity=900, ftp=True,  appid=1085660),
    dict(title="Helldivers 2",                   category="Shooter",    dev="Arrowhead Game Studios", pub="PlayStation Publishing LLC", rating=4.6, popularity=960, ftp=False, appid=553850),
    dict(title="Atomic Heart",                   category="Shooter",    dev="Mundfish",            pub="Focus Entertainment", rating=4.2, popularity=710, ftp=False, appid=668580),
    # --- Adventure / Exploration ---
    dict(title="Portal 2",                       category="Adventure",  dev="Valve",               pub="Valve",              rating=4.9, popularity=950, ftp=False, appid=620),
    dict(title="Celeste",                        category="Adventure",  dev="Maddy Makes Games",   pub="Maddy Makes Games",  rating=4.9, popularity=780, ftp=False, appid=504230),
    dict(title="Subnautica",                     category="Adventure",  dev="Unknown Worlds Entertainment", pub="Unknown Worlds Entertainment", rating=4.8, popularity=810, ftp=False, appid=264710),
    dict(title="The Forest",                     category="Adventure",  dev="Endnight Games",      pub="Endnight Games",     rating=4.5, popularity=760, ftp=False, appid=242760),
    dict(title="Sons Of The Forest",             category="Adventure",  dev="Endnight Games",      pub="Endnight Games",     rating=4.3, popularity=760, ftp=False, appid=1326470),
    dict(title="Green Hell",                     category="Adventure",  dev="Creepy Jar",          pub="Creepy Jar",         rating=4.4, popularity=700, ftp=False, appid=815370),
    dict(title="Dave the Diver",                 category="Adventure",  dev="MINTROCKET",          pub="NEXON",              rating=4.8, popularity=790, ftp=False, appid=1868140),
    dict(title="Alan Wake 2",                    category="Adventure",  dev="Remedy Entertainment", pub="Epic Games Publishing", rating=4.7, popularity=770, ftp=False, appid=2370650),
    dict(title="Half-Life: Alyx",                category="Adventure",  dev="Valve",               pub="Valve",              rating=4.9, popularity=780, ftp=False, appid=546560),
    # --- Strategy ---
    dict(title="Civilization VI",                category="Strategy",   dev="Firaxis Games",       pub="2K Games",           rating=4.5, popularity=780, ftp=False, appid=289070),
    dict(title="Total War: WARHAMMER III",       category="Strategy",   dev="Creative Assembly",   pub="SEGA",               rating=4.4, popularity=720, ftp=False, appid=1142710),
    dict(title="Crusader Kings III",             category="Strategy",   dev="Paradox Development Studio", pub="Paradox Interactive", rating=4.7, popularity=760, ftp=False, appid=1158310),
    dict(title="Stellaris",                      category="Strategy",   dev="Paradox Development Studio", pub="Paradox Interactive", rating=4.4, popularity=820, ftp=False, appid=281990),
    dict(title="Factorio",                       category="Strategy",   dev="Wube Software",       pub="Wube Software",      rating=4.9, popularity=770, ftp=False, appid=427520),
    dict(title="RimWorld",                       category="Strategy",   dev="Ludeon Studios",      pub="Ludeon Studios",     rating=4.9, popularity=790, ftp=False, appid=294100),
    dict(title="Manor Lords",                    category="Strategy",   dev="Slavic Magic",        pub="Hooded Horse",       rating=4.3, popularity=780, ftp=False, appid=1363080),
    # --- Simulation ---
    dict(title="No Man's Sky",                   category="Simulation", dev="Hello Games",          pub="Hello Games",         rating=4.5, popularity=820, ftp=False, appid=275850),
    dict(title="Valheim",                        category="Simulation", dev="Iron Gate AB",        pub="Coffee Stain Publishing", rating=4.6, popularity=840, ftp=False, appid=892970),
    dict(title="Satisfactory",                   category="Simulation", dev="Coffee Stain Studios", pub="Coffee Stain Publishing", rating=4.8, popularity=800, ftp=False, appid=526870),
    dict(title="Cities: Skylines",               category="Simulation", dev="Colossal Order",      pub="Paradox Interactive", rating=4.7, popularity=810, ftp=False, appid=255710),
    dict(title="Planet Zoo",                     category="Simulation", dev="Frontier Developments", pub="Frontier Developments", rating=4.6, popularity=720, ftp=False, appid=703080),
    dict(title="Enshrouded",                     category="Simulation", dev="Keen Games",          pub="Keen Games",         rating=4.5, popularity=800, ftp=False, appid=1203950),
    # --- Racing / Sports ---
    dict(title="Forza Horizon 5",                category="Racing",     dev="Playground Games",    pub="Xbox Game Studios",  rating=4.8, popularity=920, ftp=False, appid=1551360),
    dict(title="F1 23",                          category="Racing",     dev="Codemasters",         pub="Electronic Arts",    rating=4.3, popularity=680, ftp=False, appid=2108330),
    dict(title="Rocket League",                  category="Sports",     dev="Psyonix",             pub="Epic Games",         rating=4.5, popularity=910, ftp=True,  appid=252950),
    dict(title="FIFA 23",                        category="Sports",     dev="EA Vancouver",        pub="Electronic Arts",    rating=4.1, popularity=750, ftp=False, appid=1811260),

    # --- New Additions (2024–2026) ---
    # Action
    dict(title="Black Myth: Wukong",             category="Action",     dev="Game Science",        pub="Game Science",       rating=4.8, popularity=997, ftp=False, appid=2358720),
    dict(title="Warhammer 40K: Space Marine 2",  category="Action",     dev="Saber Interactive",   pub="Focus Entertainment", rating=4.7, popularity=920, ftp=False, appid=2183900),
    dict(title="Stellar Blade",                  category="Action",     dev="Shift Up",            pub="Sony Interactive Entertainment", rating=4.6, popularity=870, ftp=False, appid=3489700),
    dict(title="Devil May Cry 5",                category="Action",     dev="Capcom",              pub="Capcom",             rating=4.8, popularity=840, ftp=False, appid=601150),
    dict(title="Ghostrunner 2",                  category="Action",     dev="One More Level",      pub="505 Games",          rating=4.5, popularity=720, ftp=False, appid=1798650),
    dict(title="Sifu",                           category="Action",     dev="Sloclap",             pub="Sloclap",            rating=4.6, popularity=750, ftp=False, appid=2138710),
    dict(title="WARDOGS",                        category="Shooter",    dev="Emberstrike",         pub="Emberstrike",        rating=4.5, popularity=910, ftp=False, appid=1867240),

    # RPG
    dict(title="Final Fantasy XVI",              category="RPG",        dev="Square Enix",         pub="Square Enix",        rating=4.5, popularity=860, ftp=False, appid=2515020),
    dict(title="Like a Dragon: Ishin!",          category="RPG",        dev="Ryu Ga Gotoku Studio", pub="SEGA",              rating=4.6, popularity=790, ftp=False, appid=1843600),
    dict(title="Persona 5 Royal",                category="RPG",        dev="Atlus",               pub="Atlus",              rating=4.9, popularity=910, ftp=False, appid=1687950),
    dict(title="Dragon's Dogma 2",               category="RPG",        dev="Capcom",              pub="Capcom",             rating=4.4, popularity=860, ftp=False, appid=2054970),
    dict(title="Metaphor: ReFantazio",           category="RPG",        dev="Atlus",               pub="Atlus",              rating=4.9, popularity=930, ftp=False, appid=2679460),
    dict(title="Path of Exile 2",                category="RPG",        dev="Grinding Gear Games", pub="Grinding Gear Games", rating=4.6, popularity=940, ftp=True,  appid=2694490),
    dict(title="Clair Obscur: Expedition 33",    category="RPG",        dev="Sandfall Interactive", pub="Kepler Interactive", rating=4.9, popularity=970, ftp=False, appid=1903340),
    dict(title="Crimson Desert",                 category="RPG",        dev="Pearl Abyss",         pub="Pearl Abyss",        rating=4.3, popularity=830, ftp=False, appid=3321460),

    # Shooter
    dict(title="Call of Duty: Modern Warfare III", category="Shooter",  dev="Sledgehammer Games",  pub="Activision",         rating=4.0, popularity=880, ftp=False, appid=2519060),
    dict(title="The Finals",                     category="Shooter",    dev="Embark Studios",      pub="Embark Studios",     rating=4.3, popularity=860, ftp=True,  appid=2073850),

    # Adventure
    dict(title="Indiana Jones and the Great Circle", category="Adventure", dev="MachineGames",     pub="Bethesda Softworks", rating=4.7, popularity=870, ftp=False, appid=2677660),
    dict(title="A Plague Tale: Requiem",         category="Adventure",  dev="Asobo Studio",        pub="Focus Entertainment", rating=4.7, popularity=820, ftp=False, appid=1881700),
    dict(title="Ori and the Will of the Wisps",  category="Adventure",  dev="Moon Studios",        pub="Xbox Game Studios",  rating=4.9, popularity=800, ftp=False, appid=1057090),
    dict(title="Death Stranding: Director's Cut", category="Adventure", dev="Kojima Productions",  pub="505 Games",          rating=4.5, popularity=810, ftp=False, appid=1738090),
    dict(title="Split Fiction",                  category="Adventure",  dev="Hazelight Studios",   pub="Electronic Arts",    rating=4.9, popularity=965, ftp=False, appid=2001120),
    dict(title="Control Resonant",               category="Adventure",  dev="Remedy Entertainment", pub="505 Games",         rating=4.6, popularity=840, ftp=False, appid=3669870),
    dict(title="Resident Evil Requiem",          category="Adventure",  dev="Capcom",              pub="Capcom",             rating=4.7, popularity=920, ftp=False, appid=3764200),

    # Strategy
    dict(title="Against the Storm",              category="Strategy",   dev="Eremite Games",       pub="Hooded Horse",       rating=4.9, popularity=780, ftp=False, appid=1336490),
    dict(title="Victoria 3",                     category="Strategy",   dev="Paradox Development", pub="Paradox Interactive", rating=4.3, popularity=710, ftp=False, appid=529340),
    dict(title="Old World",                      category="Strategy",   dev="Mohawk Games",        pub="Hooded Horse",       rating=4.6, popularity=690, ftp=False, appid=597180),
    dict(title="Slay the Spire 2",               category="Strategy",   dev="Mega Crit",           pub="Mega Crit",          rating=4.8, popularity=880, ftp=False, appid=2868840),

    # Simulation
    dict(title="Minecraft",                      category="Simulation", dev="Mojang Studios",      pub="Microsoft",          rating=4.9, popularity=999, ftp=False, appid=None),
    dict(title="Planet Coaster 2",               category="Simulation", dev="Frontier Developments", pub="Frontier Developments", rating=4.4, popularity=720, ftp=False, appid=2688950),
    dict(title="Schedule I",                     category="Simulation", dev="TVGS",                pub="TVGS",               rating=4.8, popularity=890, ftp=False, appid=3164500),
    dict(title="Subnautica 2",                   category="Simulation", dev="Unknown Worlds Entertainment", pub="Unknown Worlds Entertainment", rating=4.7, popularity=880, ftp=False, appid=1962700),

    # Racing
    dict(title="EA Sports WRC",                  category="Racing",     dev="Codemasters",         pub="Electronic Arts",    rating=4.4, popularity=680, ftp=False, appid=1080600),
    dict(title="Assetto Corsa Competizione",     category="Racing",     dev="Kunos Simulazioni",   pub="505 Games",          rating=4.6, popularity=710, ftp=False, appid=805550),
    dict(title="F1 25",                          category="Racing",     dev="Codemasters",         pub="Electronic Arts",    rating=4.4, popularity=700, ftp=False, appid=3059520),

    # --- Extended Catalog ---
    # Action / Souls-likes
    dict(title="Bloodborne",                     category="Action",     dev="FromSoftware",         pub="Sony Interactive Entertainment", rating=4.9, popularity=910, ftp=False, appid=None),  # PS4 exclusive
    dict(title="Code Vein",                      category="Action",     dev="Bandai Namco Studios", pub="Bandai Namco",        rating=4.3, popularity=680, ftp=False, appid=678960),
    dict(title="Remnant II",                     category="Action",     dev="Gunfire Games",        pub="Gearbox Publishing", rating=4.5, popularity=760, ftp=False, appid=1282100),
    dict(title="Wo Long: Fallen Dynasty",        category="Action",     dev="Team Ninja",           pub="Koei Tecmo",         rating=4.3, popularity=700, ftp=False, appid=2015310),
    dict(title="Hi-Fi Rush",                     category="Action",     dev="Tango Gameworks",      pub="Bethesda Softworks", rating=4.8, popularity=840, ftp=False, appid=1817230),
    dict(title="Bayonetta 3",                    category="Action",     dev="PlatinumGames",        pub="Nintendo",           rating=4.6, popularity=760, ftp=False, appid=None),  # Switch exclusive
    dict(title="God of War",                     category="Action",     dev="Santa Monica Studio",  pub="PlayStation Publishing LLC", rating=4.9, popularity=970, ftp=False, appid=1593500),
    dict(title="God of War: Ragnarök",           category="Action",     dev="Santa Monica Studio",  pub="PlayStation Publishing LLC", rating=4.9, popularity=975, ftp=False, appid=2322010),
    dict(title="Spider-Man: Miles Morales",      category="Action",     dev="Insomniac Games",      pub="PlayStation Publishing LLC", rating=4.8, popularity=920, ftp=False, appid=1817190),
    dict(title="Marvel's Spider-Man Remastered", category="Action",     dev="Insomniac Games",      pub="PlayStation Publishing LLC", rating=4.8, popularity=940, ftp=False, appid=1817070),
    dict(title="Ghostwire: Tokyo",               category="Action",     dev="Tango Gameworks",      pub="Bethesda Softworks", rating=4.2, popularity=680, ftp=False, appid=1475810),
    dict(title="Nioh 2",                         category="Action",     dev="Team Ninja",           pub="Koei Tecmo",         rating=4.6, popularity=760, ftp=False, appid=1325200),
    dict(title="Star Wars Jedi: Survivor",       category="Action",     dev="Respawn Entertainment", pub="EA",               rating=4.5, popularity=820, ftp=False, appid=1774580),

    # RPG / JRPG
    dict(title="Nier: Automata",                 category="RPG",        dev="PlatinumGames",        pub="Square Enix",        rating=4.8, popularity=890, ftp=False, appid=524220),
    dict(title="Octopath Traveler II",           category="RPG",        dev="Square Enix",          pub="Square Enix",        rating=4.7, popularity=760, ftp=False, appid=1971650),
    dict(title="Fire Emblem: Three Houses",      category="RPG",        dev="Intelligent Systems",  pub="Nintendo",           rating=4.8, popularity=800, ftp=False, appid=None),  # Switch exclusive
    dict(title="Xenoblade Chronicles 3",         category="RPG",        dev="Monolith Soft",        pub="Nintendo",           rating=4.7, popularity=760, ftp=False, appid=None),  # Switch exclusive
    dict(title="The Elder Scrolls Online",       category="RPG",        dev="ZeniMax Online Studios", pub="Bethesda Softworks", rating=4.2, popularity=820, ftp=False, appid=306130),
    dict(title="World of Warcraft",              category="RPG",        dev="Blizzard Entertainment", pub="Blizzard Entertainment", rating=4.3, popularity=900, ftp=False, appid=None),  # Battle.net
    dict(title="Final Fantasy XIV Online",       category="RPG",        dev="Square Enix",          pub="Square Enix",        rating=4.6, popularity=870, ftp=False, appid=39210),
    dict(title="Diablo IV",                      category="RPG",        dev="Blizzard Entertainment", pub="Blizzard Entertainment", rating=4.3, popularity=890, ftp=False, appid=2344520),
    dict(title="Like a Dragon: Infinite Wealth", category="RPG",        dev="Ryu Ga Gotoku Studio", pub="SEGA",              rating=4.8, popularity=860, ftp=False, appid=2683460),
    dict(title="Warhammer 40K: Rogue Trader",   category="RPG",        dev="Owlcat Games",          pub="Owlcat Games",       rating=4.4, popularity=700, ftp=False, appid=2186680),

    # Shooter / FPS
    dict(title="Rainbow Six Siege",              category="Shooter",    dev="Ubisoft Montreal",     pub="Ubisoft",            rating=4.3, popularity=870, ftp=False, appid=359550),
    dict(title="Escape from Tarkov",             category="Shooter",    dev="Battlestate Games",    pub="Battlestate Games",  rating=4.0, popularity=810, ftp=False, appid=None),  # Launcher-only, not on Steam
    dict(title="Hunt: Showdown 1896",            category="Shooter",    dev="Crytek",               pub="Crytek",             rating=4.4, popularity=780, ftp=False, appid=594650),
    dict(title="Deep Rock Galactic",             category="Shooter",    dev="Ghost Ship Games",     pub="Coffee Stain Publishing", rating=4.9, popularity=860, ftp=False, appid=548430),
    dict(title="PAYDAY 3",                       category="Shooter",    dev="Overkill Software",    pub="Deep Silver",        rating=3.8, popularity=640, ftp=False, appid=1272080),
    dict(title="Warhammer 40K: Darktide",        category="Shooter",    dev="Fatshark",             pub="Fatshark",           rating=4.2, popularity=720, ftp=False, appid=1361210),
    dict(title="Insurgency: Sandstorm",          category="Shooter",    dev="New World Interactive", pub="Focus Entertainment", rating=4.5, popularity=700, ftp=False, appid=581320),

    # Adventure / Indie
    dict(title="Hades II",                       category="Action",     dev="Supergiant Games",     pub="Supergiant Games",   rating=4.9, popularity=960, ftp=False, appid=1145350),
    dict(title="Outer Wilds",                    category="Adventure",  dev="Mobius Digital",       pub="Annapurna Interactive", rating=4.9, popularity=810, ftp=False, appid=753640),
    dict(title="Inside",                         category="Adventure",  dev="Playdead",             pub="Playdead",           rating=4.8, popularity=740, ftp=False, appid=304430),
    dict(title="Limbo",                          category="Adventure",  dev="Playdead",             pub="Playdead",           rating=4.7, popularity=700, ftp=False, appid=48000),
    # (Disco Elysium listed above in main catalog)
    dict(title="The Stanley Parable: Ultra Deluxe", category="Adventure", dev="Galactic Cafe",     pub="Crows Crows Crows",  rating=4.9, popularity=720, ftp=False, appid=1703340),
    dict(title="Stray",                          category="Adventure",  dev="BlueTwelve Studio",    pub="Annapurna Interactive", rating=4.7, popularity=830, ftp=False, appid=1332010),
    dict(title="A Short Hike",                   category="Adventure",  dev="Adam Robinson-Yu",     pub="Adam Robinson-Yu",   rating=4.9, popularity=680, ftp=False, appid=1055540),
    dict(title="Unpacking",                      category="Adventure",  dev="Witch Beam",           pub="Witch Beam",         rating=4.8, popularity=710, ftp=False, appid=1135690),
    dict(title="Pentiment",                      category="Adventure",  dev="Obsidian Entertainment", pub="Xbox Game Studios", rating=4.8, popularity=720, ftp=False, appid=1929870),
    dict(title="Tunic",                          category="Adventure",  dev="Andrew Shouldice",     pub="Finji",              rating=4.7, popularity=700, ftp=False, appid=553420),

    # Strategy / City-builder
    dict(title="Anno 1800",                      category="Strategy",   dev="Ubisoft Blue Byte",    pub="Ubisoft",            rating=4.7, popularity=760, ftp=False, appid=916440),
    dict(title="Frostpunk 2",                    category="Strategy",   dev="11 bit studios",       pub="11 bit studios",     rating=4.6, popularity=810, ftp=False, appid=1601580),
    dict(title="Age of Empires IV",              category="Strategy",   dev="Relic Entertainment",  pub="Xbox Game Studios",  rating=4.5, popularity=780, ftp=False, appid=1466860),
    dict(title="Homeworld 3",                    category="Strategy",   dev="Blackbird Interactive", pub="Gearbox Publishing", rating=4.1, popularity=650, ftp=False, appid=784080),
    dict(title="Dungeon of the Endless",         category="Strategy",   dev="Amplitude Studios",    pub="SEGA",               rating=4.5, popularity=650, ftp=False, appid=249190),

    # Simulation / Survival
    dict(title="Subnautica: Below Zero",         category="Simulation", dev="Unknown Worlds Entertainment", pub="Unknown Worlds Entertainment", rating=4.5, popularity=770, ftp=False, appid=848450),
    dict(title="V Rising",                       category="Simulation", dev="Stunlock Studios",     pub="Stunlock Studios",   rating=4.7, popularity=800, ftp=False, appid=1604030),
    dict(title="Stranded Deep",                  category="Simulation", dev="Beam Team Games",      pub="Beam Team Games",    rating=4.2, popularity=640, ftp=False, appid=313120),
    dict(title="The Long Dark",                  category="Simulation", dev="Hinterland Studio",    pub="Hinterland Studio",  rating=4.6, popularity=700, ftp=False, appid=305620),
    dict(title="Planet Crafter",                 category="Simulation", dev="Miju Games",           pub="Miju Games",         rating=4.7, popularity=730, ftp=False, appid=1284190),
    dict(title="Coral Island",                   category="Simulation", dev="Stairway Games",       pub="Stairway Games",     rating=4.4, popularity=680, ftp=False, appid=1158160),
    dict(title="Disney Dreamlight Valley",       category="Simulation", dev="Gameloft",             pub="Gameloft",           rating=4.2, popularity=720, ftp=False, appid=1401590),
    dict(title="Farming Simulator 22",           category="Simulation", dev="GIANTS Software",      pub="GIANTS Software",    rating=4.3, popularity=640, ftp=False, appid=1248130),
    dict(title="House Flipper 2",                category="Simulation", dev="Empyrean",             pub="Frozen District",    rating=4.5, popularity=660, ftp=False, appid=1990400),
    dict(title="PowerWash Simulator",            category="Simulation", dev="FuturLab",             pub="Square Enix",        rating=4.7, popularity=750, ftp=False, appid=1290000),

    # Racing / Sports
    dict(title="Gran Turismo 7",                 category="Racing",     dev="Polyphony Digital",    pub="Sony Interactive Entertainment", rating=4.7, popularity=840, ftp=False, appid=None),  # PS5 exclusive, not on Steam
    dict(title="Wreckfest",                      category="Racing",     dev="Bugbear Entertainment", pub="THQ Nordic",         rating=4.7, popularity=720, ftp=False, appid=228380),
    dict(title="BeamNG.drive",                   category="Racing",     dev="BeamNG",               pub="BeamNG",             rating=4.9, popularity=880, ftp=False, appid=284160),
    dict(title="F1 24",                          category="Racing",     dev="Codemasters",          pub="EA Sports",          rating=4.2, popularity=670, ftp=False, appid=2488780),

    # Free-to-Play
    dict(title="Genshin Impact",                 category="RPG",        dev="HoYoverse",            pub="HoYoverse",          rating=4.4, popularity=970, ftp=True,  appid=1888160),
    dict(title="Honkai: Star Rail",              category="RPG",        dev="HoYoverse",            pub="HoYoverse",          rating=4.6, popularity=960, ftp=True,  appid=1546560),
    dict(title="Wuthering Waves",                category="Action",     dev="Kuro Games",           pub="Kuro Games",         rating=4.3, popularity=880, ftp=True,  appid=2479070),
    dict(title="Smite 2",                        category="Strategy",   dev="Titan Forge Games",    pub="Hi-Rez Studios",     rating=4.0, popularity=700, ftp=True,  appid=1658780),
    dict(title="Fall Guys",                      category="Action",     dev="Mediatonic",           pub="Epic Games",         rating=4.2, popularity=820, ftp=True,  appid=1097150),
    dict(title="Splitgate: Arena Reloaded",      category="Shooter",    dev="1047 Games",           pub="1047 Games",         rating=4.1, popularity=720, ftp=True,  appid=2918300),
    dict(title="Brawlhalla",                     category="Action",     dev="Blue Mammoth Games",   pub="Ubisoft",            rating=4.3, popularity=750, ftp=True,  appid=291550),

    # ── Batch 2 – filling toward 400 ──────────────────────────────────────
    # Action
    dict(title="Cuphead",                        category="Action",     dev="Studio MDHR",           pub="Studio MDHR",        rating=4.9, popularity=800, ftp=False, appid=268910),
    dict(title="Hollow Knight",                  category="Action",     dev="Team Cherry",           pub="Team Cherry",        rating=4.9, popularity=890, ftp=False, appid=367520),
    dict(title="Silksong",                       category="Action",     dev="Team Cherry",           pub="Team Cherry",        rating=4.9, popularity=960, ftp=False, appid=1030300),
    dict(title="Hades",                          category="Action",     dev="Supergiant Games",      pub="Supergiant Games",   rating=4.9, popularity=950, ftp=False, appid=1145360),
    dict(title="Dead Cells",                     category="Action",     dev="Motion Twin",           pub="Motion Twin",        rating=4.8, popularity=820, ftp=False, appid=588650),
    dict(title="Katana ZERO",                    category="Action",     dev="Askiisoft",             pub="Devolver Digital",   rating=4.8, popularity=760, ftp=False, appid=460950),
    dict(title="Neon White",                     category="Action",     dev="Angel Matrix",          pub="Annapurna Interactive", rating=4.8, popularity=720, ftp=False, appid=1533420),
    dict(title="Metal Gear Solid V",             category="Action",     dev="Konami",                pub="Konami",             rating=4.7, popularity=840, ftp=False, appid=287700),
    dict(title="Assassin's Creed Odyssey",       category="Action",     dev="Ubisoft Quebec",        pub="Ubisoft",            rating=4.5, popularity=830, ftp=False, appid=812140),
    dict(title="Assassin's Creed Origins",       category="Action",     dev="Ubisoft Montreal",      pub="Ubisoft",            rating=4.5, popularity=810, ftp=False, appid=582160),
    dict(title="Assassin's Creed Valhalla",      category="Action",     dev="Ubisoft Montreal",      pub="Ubisoft",            rating=4.3, popularity=800, ftp=False, appid=2208920),
    dict(title="Batman: Arkham Knight",          category="Action",     dev="Rocksteady Studios",    pub="Warner Bros. Games", rating=4.7, popularity=850, ftp=False, appid=208650),
    dict(title="Batman: Arkham City",            category="Action",     dev="Rocksteady Studios",    pub="Warner Bros. Games", rating=4.8, popularity=840, ftp=False, appid=200260),
    dict(title="Shadow of the Tomb Raider",      category="Action",     dev="Eidos Montreal",        pub="Square Enix",        rating=4.4, popularity=730, ftp=False, appid=750920),
    dict(title="Rise of the Tomb Raider",        category="Action",     dev="Crystal Dynamics",      pub="Square Enix",        rating=4.6, popularity=760, ftp=False, appid=391220),
    dict(title="Tomb Raider (2013)",             category="Action",     dev="Crystal Dynamics",      pub="Square Enix",        rating=4.6, popularity=770, ftp=False, appid=203160),
    dict(title="Cyberpunk 2077",                 category="Action",     dev="CD Projekt Red",        pub="CD Projekt",         rating=4.7, popularity=980, ftp=False, appid=1091500),
    dict(title="The Witcher 3: Wild Hunt",       category="RPG",        dev="CD Projekt Red",        pub="CD Projekt",         rating=4.9, popularity=999, ftp=False, appid=292030),
    dict(title="The Witcher 2",                  category="RPG",        dev="CD Projekt Red",        pub="CD Projekt",         rating=4.7, popularity=840, ftp=False, appid=20920),
    dict(title="Watch Dogs: Legion",             category="Action",     dev="Ubisoft Toronto",       pub="Ubisoft",            rating=4.1, popularity=720, ftp=False, appid=2291680),
    dict(title="Ghost of Tsushima",              category="Action",     dev="Sucker Punch Productions", pub="PlayStation Publishing LLC", rating=4.9, popularity=960, ftp=False, appid=2215430),
    dict(title="Returnal",                       category="Action",     dev="Housemarque",           pub="PlayStation Publishing LLC", rating=4.7, popularity=820, ftp=False, appid=1649250),
    dict(title="The Last of Us Part I",          category="Action",     dev="Naughty Dog",           pub="PlayStation Publishing LLC", rating=4.8, popularity=940, ftp=False, appid=1888930),
    dict(title="Horizon Zero Dawn",              category="Action",     dev="Guerrilla Games",       pub="PlayStation Publishing LLC", rating=4.7, popularity=900, ftp=False, appid=1151640),
    dict(title="Horizon Forbidden West",         category="Action",     dev="Guerrilla Games",       pub="PlayStation Publishing LLC", rating=4.7, popularity=890, ftp=False, appid=2420110),
    dict(title="Uncharted: Legacy of Thieves",   category="Adventure",  dev="Naughty Dog",           pub="PlayStation Publishing LLC", rating=4.7, popularity=860, ftp=False, appid=1659420),
    dict(title="Mortal Kombat 1",                category="Action",     dev="NetherRealm Studios",   pub="Warner Bros. Games", rating=4.4, popularity=830, ftp=False, appid=1971870),
    dict(title="Tekken 8",                       category="Action",     dev="Bandai Namco Studios",  pub="Bandai Namco",       rating=4.6, popularity=840, ftp=False, appid=1778820),
    dict(title="Street Fighter 6",               category="Action",     dev="Capcom",                pub="Capcom",             rating=4.7, popularity=850, ftp=False, appid=1966403),
    dict(title="Dragon Ball FighterZ",           category="Action",     dev="Arc System Works",      pub="Bandai Namco",       rating=4.6, popularity=800, ftp=False, appid=678950),
    dict(title="Guilty Gear: Strive",            category="Action",     dev="Arc System Works",      pub="Arc System Works",   rating=4.7, popularity=790, ftp=False, appid=1384160),
    dict(title="Nickelodeon All-Star Brawl 2",   category="Action",     dev="Fair Play Labs",         pub="GameMill Entertainment", rating=3.9, popularity=600, ftp=False, appid=2313910),
    dict(title="Multiversus",                    category="Action",     dev="Player First Games",    pub="Warner Bros. Games", rating=3.8, popularity=680, ftp=True,  appid=1818750),

    # RPG / JRPG
    dict(title="Persona 4 Golden",              category="RPG",        dev="Atlus",                 pub="Atlus",              rating=4.9, popularity=870, ftp=False, appid=1113000),
    dict(title="Persona 3 Reload",              category="RPG",        dev="Atlus",                 pub="Sega",               rating=4.8, popularity=880, ftp=False, appid=2161700),
    dict(title="Tales of Arise",                category="RPG",        dev="Bandai Namco Studios",  pub="Bandai Namco",       rating=4.6, popularity=790, ftp=False, appid=1277400),
    dict(title="Dragon Quest XI S",             category="RPG",        dev="Square Enix",           pub="Square Enix",        rating=4.8, popularity=800, ftp=False, appid=742120),
    dict(title="Triangle Strategy",             category="RPG",        dev="Square Enix",           pub="Square Enix",        rating=4.6, popularity=710, ftp=False, appid=1546580),
    dict(title="Tactics Ogre: Reborn",          category="Strategy",   dev="Square Enix",           pub="Square Enix",        rating=4.6, popularity=700, ftp=False, appid=1973530),
    dict(title="Xenoblade Chronicles: DE",      category="RPG",        dev="Monolith Soft",         pub="Nintendo",           rating=4.8, popularity=790, ftp=False, appid=None),
    dict(title="Final Fantasy VII Rebirth",     category="RPG",        dev="Square Enix",           pub="Square Enix",        rating=4.9, popularity=950, ftp=False, appid=2909400),
    dict(title="Final Fantasy VII Remake",      category="RPG",        dev="Square Enix",           pub="Square Enix",        rating=4.8, popularity=920, ftp=False, appid=1462040),
    dict(title="Crisis Core: Final Fantasy VII Reunion", category="RPG", dev="Square Enix",         pub="Square Enix",        rating=4.7, popularity=800, ftp=False, appid=2161940),
    dict(title="Kingdom Hearts III",            category="RPG",        dev="Square Enix",           pub="Square Enix",        rating=4.7, popularity=840, ftp=False, appid=2552430),
    dict(title="Scarlet Nexus",                 category="RPG",        dev="Bandai Namco Studios",  pub="Bandai Namco",       rating=4.4, popularity=720, ftp=False, appid=775500),
    dict(title="Blue Protocol",                 category="RPG",        dev="Bandai Namco Online",   pub="Bandai Namco",       rating=3.9, popularity=690, ftp=True,  appid=None),
    dict(title="Genshin Impact (PC)",            category="RPG",        dev="HoYoverse",             pub="HoYoverse",          rating=4.4, popularity=971, ftp=True,  appid=None),
    dict(title="Zenless Zone Zero",             category="RPG",        dev="HoYoverse",             pub="HoYoverse",          rating=4.3, popularity=900, ftp=True,  appid=2406523),
    dict(title="Sword Art Online: FB",          category="RPG",        dev="Bandai Namco Studios",  pub="Bandai Namco",       rating=4.2, popularity=680, ftp=False, appid=1329860),
    dict(title="Eiyuden Chronicle: Hundred Heroes", category="RPG",   dev="Rabbit & Bear Studios", pub="505 Games",          rating=4.5, popularity=750, ftp=False, appid=1658260),
    dict(title="Granblue Fantasy: Relink",      category="RPG",        dev="Cygames",               pub="Cygames",            rating=4.7, popularity=820, ftp=False, appid=881020),
    dict(title="Asterigos: Curse of the Stars", category="RPG",        dev="Acme Gamestudio",       pub="tinyBuild",          rating=4.3, popularity=650, ftp=False, appid=1819820),
    dict(title="Outward: Definitive Edition",   category="RPG",        dev="Nine Dots Studio",      pub="Deep Silver",        rating=4.2, popularity=640, ftp=False, appid=1743750),

    # Shooter / FPS
    dict(title="Titanfall 2",                   category="Shooter",    dev="Respawn Entertainment", pub="EA",                 rating=4.9, popularity=880, ftp=False, appid=1237970),
    dict(title="Doom (2016)",                   category="Shooter",    dev="id Software",           pub="Bethesda",           rating=4.8, popularity=890, ftp=False, appid=379720),
    dict(title="Wolfenstein II: The New Colossus", category="Shooter", dev="MachineGames",          pub="Bethesda",           rating=4.6, popularity=770, ftp=False, appid=612880),
    dict(title="Deathloop",                     category="Shooter",    dev="Arkane Lyon",           pub="Bethesda",           rating=4.5, popularity=750, ftp=False, appid=1252330),
    dict(title="Prey (2017)",                   category="Shooter",    dev="Arkane Studios",        pub="Bethesda",           rating=4.6, popularity=760, ftp=False, appid=480490),
    dict(title="Dishonored 2",                  category="Shooter",    dev="Arkane Studios",        pub="Bethesda",           rating=4.6, popularity=760, ftp=False, appid=403640),
    dict(title="Bioshock Infinite",             category="Shooter",    dev="Irrational Games",      pub="2K Games",           rating=4.8, popularity=840, ftp=False, appid=8870),
    dict(title="Bioshock 2 Remastered",         category="Shooter",    dev="2K Marin",              pub="2K Games",           rating=4.6, popularity=780, ftp=False, appid=409720),
    dict(title="Far Cry 6",                     category="Shooter",    dev="Ubisoft Toronto",       pub="Ubisoft",            rating=4.2, popularity=750, ftp=False, appid=2369390),
    dict(title="Far Cry 5",                     category="Shooter",    dev="Ubisoft Montreal",      pub="Ubisoft",            rating=4.4, popularity=780, ftp=False, appid=552520),
    dict(title="Far Cry New Dawn",              category="Shooter",    dev="Ubisoft Montreal",      pub="Ubisoft",            rating=4.1, popularity=700, ftp=False, appid=939960),
    dict(title="Battlefield V",                 category="Shooter",    dev="EA DICE",               pub="Electronic Arts",    rating=4.0, popularity=740, ftp=False, appid=1238810),
    dict(title="Battlefield 2042",              category="Shooter",    dev="EA DICE",               pub="Electronic Arts",    rating=3.8, popularity=700, ftp=False, appid=1517290),
    dict(title="Halo Infinite",                 category="Shooter",    dev="343 Industries",        pub="Xbox Game Studios",  rating=4.2, popularity=800, ftp=False, appid=1240440),
    dict(title="PUBG: Battlegrounds",           category="Shooter",    dev="Krafton",               pub="Krafton",            rating=4.0, popularity=880, ftp=True,  appid=578080),
    dict(title="Fortnite",                      category="Shooter",    dev="Epic Games",            pub="Epic Games",         rating=4.0, popularity=990, ftp=True,  appid=None),
    dict(title="Warzone 2.0",                   category="Shooter",    dev="Raven Software",        pub="Activision",         rating=3.9, popularity=900, ftp=True,  appid=None),
    dict(title="XDefiant",                      category="Shooter",    dev="Ubisoft San Francisco", pub="Ubisoft",            rating=3.8, popularity=700, ftp=True,  appid=1483950),
    dict(title="Valorant",                      category="Shooter",    dev="Riot Games",            pub="Riot Games",         rating=4.3, popularity=980, ftp=True,  appid=None),
    dict(title="Overwatch 2",                   category="Shooter",    dev="Blizzard Entertainment", pub="Blizzard Entertainment", rating=3.9, popularity=900, ftp=True, appid=2357570),
    dict(title="Quake Champions",               category="Shooter",    dev="id Software",           pub="Bethesda",           rating=4.0, popularity=650, ftp=True,  appid=611500),
    dict(title="Paladins",                      category="Shooter",    dev="Evil Mojo",             pub="Hi-Rez Studios",     rating=4.0, popularity=700, ftp=True,  appid=444090),
    dict(title="Planetside 2",                  category="Shooter",    dev="Rogue Planet Games",    pub="Daybreak Game Company", rating=4.1, popularity=650, ftp=True, appid=218230),

    # Adventure / Exploration
    dict(title="Red Dead Redemption 2 (GOTY)",   category="Adventure",  dev="Rockstar Games",        pub="Rockstar Games",     rating=4.9, popularity=994, ftp=False, appid=None),
    dict(title="Elden Ring: Shadow of the Erdtree", category="Action", dev="FromSoftware",          pub="Bandai Namco",       rating=4.8, popularity=960, ftp=False, appid=None),
    dict(title="Firewatch",                     category="Adventure",  dev="Campo Santo",           pub="Campo Santo",        rating=4.7, popularity=770, ftp=False, appid=383870),
    dict(title="Oxenfree II",                   category="Adventure",  dev="Night School Studio",   pub="Netflix Games",      rating=4.5, popularity=680, ftp=False, appid=1795400),
    dict(title="Oxenfree",                      category="Adventure",  dev="Night School Studio",   pub="Night School Studio", rating=4.6, popularity=700, ftp=False, appid=388880),
    dict(title="What Remains of Edith Finch",   category="Adventure",  dev="Giant Sparrow",         pub="Annapurna Interactive", rating=4.9, popularity=780, ftp=False, appid=501300),
    dict(title="Disco Elysium: FC Redux",        category="RPG",        dev="ZA/UM",                 pub="ZA/UM",              rating=4.8, popularity=751, ftp=False, appid=None),
    dict(title="Spiritfarer",                   category="Adventure",  dev="Thunder Lotus Games",   pub="Thunder Lotus Games", rating=4.8, popularity=730, ftp=False, appid=972660),
    dict(title="Sable",                         category="Adventure",  dev="Shedworks",             pub="Raw Fury",           rating=4.2, popularity=650, ftp=False, appid=1285690),
    dict(title="Journey (thatgamecompany)",     category="Adventure",  dev="thatgamecompany",       pub="Annapurna Interactive", rating=4.9, popularity=750, ftp=False, appid=638230),
    dict(title="Abzu",                          category="Adventure",  dev="Giant Squid",           pub="505 Games",          rating=4.7, popularity=700, ftp=False, appid=384190),
    dict(title="The Forgotten City",            category="Adventure",  dev="Modern Storyteller",    pub="Dear Villagers",     rating=4.8, popularity=720, ftp=False, appid=874260),
    dict(title="Control",                       category="Adventure",  dev="Remedy Entertainment",  pub="505 Games",          rating=4.6, popularity=820, ftp=False, appid=870780),
    dict(title="The Medium",                    category="Adventure",  dev="Bloober Team",          pub="Bloober Team",       rating=4.3, popularity=680, ftp=False, appid=1293160),
    dict(title="Observer: System Redux",        category="Adventure",  dev="Bloober Team",          pub="Bloober Team",       rating=4.4, popularity=650, ftp=False, appid=1386860),
    dict(title="Layers of Fear",                category="Adventure",  dev="Bloober Team",          pub="Bloober Team",       rating=4.2, popularity=650, ftp=False, appid=391720),
    dict(title="Layers of Fear 2",              category="Adventure",  dev="Bloober Team",          pub="Bloober Team",       rating=4.1, popularity=620, ftp=False, appid=947270),
    dict(title="Endling: Extinction is Forever", category="Adventure", dev="HeroBeard",             pub="HandyGames",         rating=4.5, popularity=660, ftp=False, appid=1584550),
    dict(title="As Dusk Falls",                 category="Adventure",  dev="Interior/Night",        pub="Xbox Game Studios",  rating=4.5, popularity=660, ftp=False, appid=1580140),
    dict(title="Somerville",                    category="Adventure",  dev="Jumpship",              pub="Jumpship",           rating=4.2, popularity=620, ftp=False, appid=1581530),
    dict(title="Immortality",                   category="Adventure",  dev="Sam Barlow",            pub="Half Mermaid",       rating=4.7, popularity=680, ftp=False, appid=1929580),

    # Horror
    dict(title="Resident Evil 4 Remake",        category="Action",     dev="Capcom",                pub="Capcom",             rating=4.9, popularity=970, ftp=False, appid=2050650),
    dict(title="Resident Evil Village",         category="Action",     dev="Capcom",                pub="Capcom",             rating=4.7, popularity=890, ftp=False, appid=1196590),
    dict(title="Resident Evil 3 Remake",        category="Action",     dev="Capcom",                pub="Capcom",             rating=4.4, popularity=820, ftp=False, appid=952060),
    dict(title="Resident Evil 2 Remake",        category="Action",     dev="Capcom",                pub="Capcom",             rating=4.8, popularity=890, ftp=False, appid=883710),
    dict(title="Dead Space Remake",             category="Action",     dev="Motive Studio",         pub="Electronic Arts",    rating=4.8, popularity=850, ftp=False, appid=1693980),
    dict(title="The Callisto Protocol",         category="Action",     dev="Striking Distance Studios", pub="Krafton",        rating=4.1, popularity=700, ftp=False, appid=1272260),
    dict(title="Alien: Isolation",              category="Adventure",  dev="Creative Assembly",     pub="SEGA",               rating=4.8, popularity=800, ftp=False, appid=214490),
    dict(title="Amnesia: The Bunker",           category="Adventure",  dev="Frictional Games",      pub="Frictional Games",   rating=4.6, popularity=720, ftp=False, appid=1944430),
    dict(title="Phasmophobia",                  category="Adventure",  dev="Kinetic Games",         pub="Kinetic Games",      rating=4.7, popularity=800, ftp=False, appid=739630),
    dict(title="Dead by Daylight",              category="Action",     dev="Behaviour Interactive", pub="Behaviour Interactive", rating=4.1, popularity=810, ftp=False, appid=381210),
    dict(title="The Quarry",                    category="Adventure",  dev="Supermassive Games",    pub="2K Games",           rating=4.4, popularity=730, ftp=False, appid=1336790),
    dict(title="Until Dawn",                    category="Adventure",  dev="Supermassive Games",    pub="PlayStation Publishing LLC", rating=4.6, popularity=760, ftp=False, appid=2172010),
    dict(title="Little Nightmares II",          category="Adventure",  dev="Tarsier Studios",       pub="Bandai Namco",       rating=4.7, popularity=790, ftp=False, appid=860510),
    dict(title="Little Nightmares",             category="Adventure",  dev="Tarsier Studios",       pub="Bandai Namco",       rating=4.7, popularity=770, ftp=False, appid=424840),
    dict(title="Signalis",                      category="Adventure",  dev="rose-engine",           pub="Humble Games",       rating=4.8, popularity=740, ftp=False, appid=1262350),
    dict(title="Dread Templar",                 category="Shooter",    dev="T19 Games",             pub="1C Entertainment",   rating=4.5, popularity=640, ftp=False, appid=1305610),

    # Strategy / Tactics
    dict(title="XCOM 2",                        category="Strategy",   dev="Firaxis Games",         pub="2K Games",           rating=4.8, popularity=820, ftp=False, appid=268500),
    dict(title="XCOM: Enemy Unknown",           category="Strategy",   dev="Firaxis Games",         pub="2K Games",           rating=4.7, popularity=780, ftp=False, appid=200510),
    dict(title="Into the Breach",               category="Strategy",   dev="Subset Games",          pub="Subset Games",       rating=4.8, popularity=760, ftp=False, appid=590380),
    dict(title="Frozen Synapse",                category="Strategy",   dev="Mode 7",                pub="Mode 7",             rating=4.5, popularity=620, ftp=False, appid=98200),
    dict(title="Total War: Three Kingdoms",     category="Strategy",   dev="Creative Assembly",     pub="SEGA",               rating=4.5, popularity=730, ftp=False, appid=779340),
    dict(title="Total War: Shogun 2",           category="Strategy",   dev="Creative Assembly",     pub="SEGA",               rating=4.8, popularity=760, ftp=False, appid=34330),
    dict(title="Hearts of Iron IV",             category="Strategy",   dev="Paradox Development Studio", pub="Paradox Interactive", rating=4.6, popularity=800, ftp=False, appid=394360),
    dict(title="Europa Universalis IV",         category="Strategy",   dev="Paradox Development Studio", pub="Paradox Interactive", rating=4.5, popularity=760, ftp=False, appid=236850),
    dict(title="Sid Meier's Civilization V",    category="Strategy",   dev="Firaxis Games",         pub="2K Games",           rating=4.8, popularity=810, ftp=False, appid=8930),
    dict(title="Age of Mythology: Retold",      category="Strategy",   dev="World's Edge",          pub="Xbox Game Studios",  rating=4.5, popularity=760, ftp=False, appid=1934680),
    dict(title="Northgard",                     category="Strategy",   dev="Shiro Games",           pub="Shiro Games",        rating=4.6, popularity=720, ftp=False, appid=466560),
    dict(title="They Are Billions",             category="Strategy",   dev="Numantian Games",       pub="Numantian Games",    rating=4.5, popularity=670, ftp=False, appid=644930),
    dict(title="Desperados III",                category="Strategy",   dev="Mimimi Games",          pub="THQ Nordic",         rating=4.8, popularity=730, ftp=False, appid=610370),
    dict(title="Shadow Tactics: Blades of the Shogun", category="Strategy", dev="Mimimi Games",    pub="Daedalic Entertainment", rating=4.8, popularity=740, ftp=False, appid=418240),
    dict(title="Wartales",                      category="Strategy",   dev="Shiro Games",           pub="Shiro Games",        rating=4.6, popularity=720, ftp=False, appid=1527950),
    dict(title="Battle Brothers",               category="Strategy",   dev="Overhype Studios",      pub="Overhype Studios",   rating=4.7, popularity=700, ftp=False, appid=365360),
    dict(title="Hard West 2",                   category="Strategy",   dev="Ice Code Games",        pub="Good Shepherd Entertainment", rating=4.4, popularity=650, ftp=False, appid=1865760),
    dict(title="Dune: Spice Wars",              category="Strategy",   dev="Shiro Games",           pub="Funcom",             rating=4.3, popularity=700, ftp=False, appid=1605220),
    dict(title="Homeworld Remastered",          category="Strategy",   dev="Gearbox Software",      pub="Gearbox Publishing", rating=4.6, popularity=680, ftp=False, appid=244160),
    dict(title="Endless Space 2",               category="Strategy",   dev="Amplitude Studios",     pub="SEGA",               rating=4.5, popularity=660, ftp=False, appid=392110),
    dict(title="Galactic Civilizations IV",     category="Strategy",   dev="Stardock Entertainment", pub="Stardock Entertainment", rating=4.2, popularity=620, ftp=False, appid=1846600),
    dict(title="Master of Orion",               category="Strategy",   dev="NGD Studios",           pub="Wargaming",          rating=4.1, popularity=580, ftp=False, appid=410950),

    # Simulation / Sandbox
    dict(title="Kerbal Space Program 2",        category="Simulation", dev="Intercept Games",       pub="Private Division",   rating=3.9, popularity=750, ftp=False, appid=954850),
    dict(title="Kerbal Space Program",          category="Simulation", dev="Squad",                 pub="Private Division",   rating=4.8, popularity=820, ftp=False, appid=220200),
    dict(title="Space Engineers",               category="Simulation", dev="Keen Software House",   pub="Keen Software House", rating=4.6, popularity=790, ftp=False, appid=244850),
    dict(title="Rust",                          category="Simulation", dev="Facepunch Studios",     pub="Facepunch Studios",  rating=4.3, popularity=880, ftp=False, appid=252490),
    dict(title="DayZ",                          category="Simulation", dev="Bohemia Interactive",   pub="Bohemia Interactive", rating=4.1, popularity=790, ftp=False, appid=221100),
    dict(title="Scum",                          category="Simulation", dev="Gamepires",             pub="Devolver Digital",   rating=4.2, popularity=700, ftp=False, appid=513710),
    dict(title="The Isle",                      category="Simulation", dev="Afterthought LLC",      pub="Afterthought LLC",   rating=4.0, popularity=650, ftp=False, appid=376210),
    dict(title="Euro Truck Simulator 2",        category="Simulation", dev="SCS Software",          pub="SCS Software",       rating=4.8, popularity=840, ftp=False, appid=227300),
    dict(title="American Truck Simulator",      category="Simulation", dev="SCS Software",          pub="SCS Software",       rating=4.8, popularity=810, ftp=False, appid=270880),
    dict(title="Microsoft Flight Simulator",    category="Simulation", dev="Asobo Studio",          pub="Xbox Game Studios",  rating=4.7, popularity=850, ftp=False, appid=1250410),
    dict(title="Flight Simulator 2024",         category="Simulation", dev="Asobo Studio",          pub="Xbox Game Studios",  rating=4.5, popularity=820, ftp=False, appid=2537590),
    dict(title="Cities: Skylines II",           category="Simulation", dev="Colossal Order",        pub="Paradox Interactive", rating=3.8, popularity=730, ftp=False, appid=949230),
    dict(title="Two Point Hospital",            category="Simulation", dev="Two Point Studios",     pub="SEGA",               rating=4.7, popularity=760, ftp=False, appid=535930),
    dict(title="Two Point Campus",              category="Simulation", dev="Two Point Studios",     pub="SEGA",               rating=4.5, popularity=720, ftp=False, appid=1649080),
    dict(title="Parkitect",                     category="Simulation", dev="Texel Raptor",          pub="Texel Raptor",       rating=4.8, popularity=710, ftp=False, appid=453090),
    dict(title="Offworld Trading Company",      category="Strategy",   dev="Mohawk Games",          pub="Stardock Entertainment", rating=4.5, popularity=620, ftp=False, appid=271240),
    dict(title="Oxygen Not Included",           category="Simulation", dev="Klei Entertainment",   pub="Klei Entertainment", rating=4.8, popularity=760, ftp=False, appid=457140),
    dict(title="Dwarf Fortress",                category="Simulation", dev="Bay 12 Games",          pub="Bay 12 Games",       rating=4.8, popularity=740, ftp=False, appid=975370),
    dict(title="Caves of Qud",                  category="RPG",        dev="Freehold Games",        pub="Freehold Games",     rating=4.8, popularity=680, ftp=False, appid=333640),
    dict(title="Going Medieval",                category="Simulation", dev="Foxy Voxel",            pub="Hooded Horse",       rating=4.5, popularity=680, ftp=False, appid=1029780),
    dict(title="Patron",                        category="Simulation", dev="Overseer Games",        pub="Overseer Games",     rating=4.3, popularity=620, ftp=False, appid=1538570),
    dict(title="Frostpunk",                     category="Simulation", dev="11 bit studios",        pub="11 bit studios",     rating=4.8, popularity=830, ftp=False, appid=323190),
    dict(title="This War of Mine",              category="Simulation", dev="11 bit studios",        pub="11 bit studios",     rating=4.7, popularity=760, ftp=False, appid=282070),
    dict(title="Spiritfall",                    category="Action",     dev="Gentle Giant",          pub="Gentle Giant",       rating=4.5, popularity=640, ftp=False, appid=1835880),
    dict(title="Hardspace: Shipbreaker",        category="Simulation", dev="Blackbird Interactive", pub="Focus Entertainment", rating=4.6, popularity=690, ftp=False, appid=1161580),

    # Platformer
    dict(title="Ori and the Blind Forest: DE", category="Adventure",  dev="Moon Studios",          pub="Microsoft Studios",  rating=4.9, popularity=810, ftp=False, appid=387290),
    dict(title="Shovel Knight: Treasure Trove", category="Action",    dev="Yacht Club Games",      pub="Yacht Club Games",   rating=4.9, popularity=790, ftp=False, appid=250760),
    dict(title="Blasphemous 2",                 category="Action",     dev="The Game Kitchen",      pub="Team17",             rating=4.7, popularity=740, ftp=False, appid=2114740),
    dict(title="Blasphemous",                   category="Action",     dev="The Game Kitchen",      pub="Team17",             rating=4.7, popularity=730, ftp=False, appid=774361),
    dict(title="Salt and Sacrifice",            category="Action",     dev="Ska Studios",           pub="Ska Studios",        rating=4.2, popularity=660, ftp=False, appid=1580130),
    dict(title="Salt and Sanctuary",            category="Action",     dev="Ska Studios",           pub="Ska Studios",        rating=4.5, popularity=680, ftp=False, appid=283640),
    dict(title="Nine Sols",                     category="Action",     dev="RedCandleGames",        pub="RedCandleGames",     rating=4.9, popularity=810, ftp=False, appid=1809540),
    dict(title="Axiom Verge 2",                 category="Action",     dev="Thomas Happ Games",     pub="Thomas Happ Games",  rating=4.4, popularity=640, ftp=False, appid=1605510),
    dict(title="Axiom Verge",                   category="Action",     dev="Thomas Happ Games",     pub="Thomas Happ Games",  rating=4.6, popularity=660, ftp=False, appid=332200),
    dict(title="Pseudoregalia",                 category="Action",     dev="Rittzler",              pub="Rittzler",           rating=4.8, popularity=680, ftp=False, appid=2140790),
    dict(title="Islets",                        category="Action",     dev="Kyle Thompson",         pub="Armor Games Studios", rating=4.6, popularity=630, ftp=False, appid=1728870),
    dict(title="Deedlit in Wonder Labyrinth",   category="Action",     dev="TEAM LADYBUG",          pub="TEAM LADYBUG",       rating=4.7, popularity=650, ftp=False, appid=1082900),
    dict(title="Record of Lodoss War: Deedlit in WL", category="Action", dev="TEAM LADYBUG",         pub="TEAM LADYBUG",       rating=4.7, popularity=640, ftp=False, appid=None),
    dict(title="Castlevania: Symphony of the Night", category="Action", dev="Konami",              pub="Konami",             rating=4.9, popularity=800, ftp=False, appid=None),
    dict(title="Yooka-Laylee and the Impossible Lair", category="Action", dev="Playtonic Games",   pub="Team17",             rating=4.5, popularity=640, ftp=False, appid=1044020),
    dict(title="A Hat in Time",                 category="Action",     dev="Gears for Breakfast",   pub="Humble Bundle",      rating=4.9, popularity=830, ftp=False, appid=253230),
    dict(title="Super Lucky's Tale",            category="Action",     dev="Playful Studios",       pub="Xbox Game Studios",  rating=4.6, popularity=680, ftp=False, appid=967050),
    dict(title="Spyro Reignited Trilogy",       category="Action",     dev="Toys for Bob",          pub="Activision",         rating=4.8, popularity=790, ftp=False, appid=996580),
    dict(title="Crash Bandicoot N. Sane Trilogy", category="Action",   dev="Vicarious Visions",     pub="Activision",         rating=4.7, popularity=790, ftp=False, appid=731490),
    dict(title="Rayman Legends Definitive Ed.", category="Action",     dev="Ubisoft Montpellier",   pub="Ubisoft",            rating=4.8, popularity=760, ftp=False, appid=None),

    # Puzzle
    dict(title="The Witness",                   category="Adventure",  dev="Jonathan Blow",         pub="Jonathan Blow",      rating=4.6, popularity=720, ftp=False, appid=210970),
    dict(title="Baba Is You",                   category="Strategy",   dev="Hempuli Oy",            pub="Hempuli Oy",         rating=4.8, popularity=740, ftp=False, appid=736260),
    dict(title="Stephen's Sausage Roll",        category="Strategy",   dev="Increpare Games",       pub="Increpare Games",    rating=4.6, popularity=610, ftp=False, appid=353540),
    dict(title="Talos Principle 2",             category="Adventure",  dev="Croteam",               pub="Devolver Digital",   rating=4.8, popularity=750, ftp=False, appid=835960),
    dict(title="The Talos Principle",           category="Adventure",  dev="Croteam",               pub="Devolver Digital",   rating=4.8, popularity=740, ftp=False, appid=257510),
    dict(title="Patrick's Parabox",             category="Strategy",   dev="Patrick Traynor",       pub="Devolver Digital",   rating=4.8, popularity=690, ftp=False, appid=1260520),
    dict(title="Cocoon",                        category="Adventure",  dev="Geometric Interactive", pub="Annapurna Interactive", rating=4.8, popularity=740, ftp=False, appid=1497440),
    dict(title="Viewfinder",                    category="Adventure",  dev="Sad Owl Studios",       pub="Thunderful Publishing", rating=4.6, popularity=680, ftp=False, appid=1382070),
    dict(title="Superliminal",                  category="Adventure",  dev="Pillow Castle Games",   pub="Pillow Castle Games", rating=4.7, popularity=720, ftp=False, appid=1049410),
    dict(title="Manifold Garden",               category="Adventure",  dev="William Chyr Studio",   pub="William Chyr Studio", rating=4.7, popularity=670, ftp=False, appid=1162970),
    dict(title="Moncage",                       category="Adventure",  dev="Optillusion",           pub="Optillusion",        rating=4.6, popularity=620, ftp=False, appid=1195290),
    dict(title="Chants of Sennaar",             category="Adventure",  dev="Rundisc",               pub="Focus Entertainment", rating=4.8, popularity=700, ftp=False, appid=1931280),
    dict(title="Lorelei and the Laser Eyes",    category="Adventure",  dev="Simogo",                pub="Annapurna Interactive", rating=4.7, popularity=710, ftp=False, appid=1922340),

    # Indie / Roguelite
    dict(title="Enter the Gungeon",             category="Action",     dev="Dodge Roll",            pub="Devolver Digital",   rating=4.8, popularity=830, ftp=False, appid=311690),
    dict(title="Slay the Spire",                category="Strategy",   dev="Mega Crit",             pub="Mega Crit",          rating=4.9, popularity=880, ftp=False, appid=646570),
    dict(title="Monster Train",                 category="Strategy",   dev="Shiny Shoe",            pub="Good Shepherd Entertainment", rating=4.8, popularity=790, ftp=False, appid=1102190),
    dict(title="Dicey Dungeons",                category="Strategy",   dev="Terry Cavanagh",        pub="Distractionware",    rating=4.6, popularity=690, ftp=False, appid=861540),
    dict(title="Roguebook",                     category="Strategy",   dev="Abrakam Entertainment", pub="Nacon",              rating=4.3, popularity=640, ftp=False, appid=1076300),
    dict(title="Skul: The Hero Slayer",         category="Action",     dev="SouthPAW Games",        pub="Neowiz",             rating=4.6, popularity=700, ftp=False, appid=1147560),
    dict(title="Rogue Legacy 2",                category="Action",     dev="Cellar Door Games",     pub="Cellar Door Games",  rating=4.8, popularity=800, ftp=False, appid=1253920),
    dict(title="Wizard of Legend",              category="Action",     dev="Contingent99",          pub="Humble Bundle",      rating=4.5, popularity=720, ftp=False, appid=445980),
    dict(title="Noita",                         category="Action",     dev="Nolla Games",           pub="Nolla Games",        rating=4.8, popularity=800, ftp=False, appid=881100),
    dict(title="Binding of Isaac: Repentance",  category="Action",     dev="Edmund McMillen",       pub="Nicalis",            rating=4.9, popularity=880, ftp=False, appid=1426300),
    dict(title="Risk of Rain 2",                category="Action",     dev="Hopoo Games",           pub="Gearbox Publishing", rating=4.7, popularity=850, ftp=False, appid=632360),
    dict(title="Risk of Rain Returns",          category="Action",     dev="Hopoo Games",           pub="Gearbox Publishing", rating=4.7, popularity=780, ftp=False, appid=1337520),
    dict(title="Cult of the Lamb",              category="Action",     dev="Massive Monster",       pub="Devolver Digital",   rating=4.6, popularity=840, ftp=False, appid=1313140),
    dict(title="Loop Hero",                     category="Strategy",   dev="Four Quarters",         pub="Devolver Digital",   rating=4.5, popularity=720, ftp=False, appid=1282730),
    dict(title="Darkest Dungeon 2",             category="RPG",        dev="Red Hook Studios",      pub="Red Hook Studios",   rating=4.5, popularity=780, ftp=False, appid=1940340),
    dict(title="Darkest Dungeon",               category="RPG",        dev="Red Hook Studios",      pub="Red Hook Studios",   rating=4.7, popularity=800, ftp=False, appid=262060),

    # Sports / Racing
    dict(title="Rocket League Sideswipe",       category="Sports",     dev="Psyonix",               pub="Epic Games",         rating=4.2, popularity=720, ftp=True,  appid=None),
    dict(title="eFootball 2025",                category="Sports",     dev="Konami",                pub="Konami",             rating=3.7, popularity=700, ftp=True,  appid=1665460),
    dict(title="iRacing",                       category="Racing",     dev="iRacing.com",           pub="iRacing.com",        rating=4.4, popularity=680, ftp=False, appid=266410),
    dict(title="rFactor 2",                     category="Racing",     dev="Studio 397",            pub="Studio 397",         rating=4.3, popularity=640, ftp=False, appid=365960),
    dict(title="CarX Drift Racing Online",      category="Racing",     dev="CarX Technologies",     pub="CarX Technologies",  rating=4.4, popularity=670, ftp=False, appid=635260),
    dict(title="Forza Motorsport",              category="Racing",     dev="Turn 10 Studios",       pub="Xbox Game Studios",  rating=4.3, popularity=800, ftp=False, appid=2440510),
    dict(title="MX vs ATV Legends",             category="Racing",     dev="Rainbow Studios",       pub="THQ Nordic",         rating=4.1, popularity=610, ftp=False, appid=1120940),
    dict(title="Riders Republic",               category="Sports",     dev="Ubisoft Annecy",        pub="Ubisoft",            rating=4.3, popularity=680, ftp=False, appid=1594320),
    dict(title="Steep",                         category="Sports",     dev="Ubisoft Annecy",        pub="Ubisoft",            rating=4.1, popularity=630, ftp=False, appid=460870),
    dict(title="Cricket 24",                    category="Sports",     dev="Big Ant Studios",       pub="Nacon",              rating=4.1, popularity=600, ftp=False, appid=2253610),
    dict(title="NBA 2K24",                      category="Sports",     dev="Visual Concepts",       pub="2K Games",           rating=4.0, popularity=720, ftp=False, appid=2338770),
    dict(title="PGA Tour 2K23",                 category="Sports",     dev="HB Studios",            pub="2K Games",           rating=4.2, popularity=620, ftp=False, appid=1946060),

    # Music / Rhythm
    dict(title="Crypt of the NecroDancer",      category="Action",     dev="Brace Yourself Games",  pub="Brace Yourself Games", rating=4.7, popularity=720, ftp=False, appid=247080),
    dict(title="Thumper",                       category="Action",     dev="Drool",                 pub="Drool",              rating=4.7, popularity=680, ftp=False, appid=356400),
    dict(title="BPM: Bullets Per Minute",       category="Shooter",    dev="Awe Interactive",       pub="Awe Interactive",    rating=4.5, popularity=650, ftp=False, appid=1100690),
    dict(title="Everhood",                      category="RPG",        dev="Foreign Gnomes",        pub="Foreign Gnomes",     rating=4.6, popularity=640, ftp=False, appid=1229380),
    dict(title="Muse Dash",                     category="Action",     dev="PeroPeroGames",         pub="X.D. Network",       rating=4.7, popularity=720, ftp=False, appid=774171),

    # Misc / Casual
    dict(title="Stardew Valley",                category="Simulation", dev="ConcernedApe",          pub="ConcernedApe",       rating=4.9, popularity=990, ftp=False, appid=413150),
    dict(title="Story of Seasons: A WL",        category="Simulation", dev="Marvelous",             pub="XSEED Games",        rating=4.5, popularity=680, ftp=False, appid=1575000),
    dict(title="Rune Factory 5",                category="RPG",        dev="Marvelous",             pub="XSEED Games",        rating=4.4, popularity=680, ftp=False, appid=None),
    dict(title="My Time at Portia",             category="Simulation", dev="Pathea Games",          pub="Team17",             rating=4.5, popularity=700, ftp=False, appid=666140),
    dict(title="My Time at Sandrock",           category="Simulation", dev="Pathea Games",          pub="Team17",             rating=4.6, popularity=720, ftp=False, appid=1084590),
    dict(title="Palia",                         category="Simulation", dev="Singularity 6",         pub="Singularity 6",      rating=4.1, popularity=680, ftp=True,  appid=2707930),
    dict(title="Garden Story",                  category="RPG",        dev="Picogram",              pub="Rose City Games",    rating=4.5, popularity=630, ftp=False, appid=1062140),
    dict(title="Potion Craft: Alchemist Sim",   category="Simulation", dev="niceplay games",        pub="tinyBuild",          rating=4.7, popularity=690, ftp=False, appid=1210320),
    dict(title="Tavern Master",                 category="Simulation", dev="MHGames",               pub="MHGames",            rating=4.4, popularity=620, ftp=False, appid=1600990),
    dict(title="Alchemy Garden",                category="Simulation", dev="Alchemy Garden Studio", pub="Alchemy Garden Studio", rating=4.2, popularity=590, ftp=False, appid=2015090),
    dict(title="Dinkum",                        category="Simulation", dev="James Bendon",          pub="James Bendon",       rating=4.7, popularity=700, ftp=False, appid=1745680),
    dict(title="Slime Rancher 2",               category="Simulation", dev="Monomi Park",           pub="Monomi Park",        rating=4.7, popularity=740, ftp=False, appid=1657630),
    dict(title="Bugsnax",                       category="Adventure",  dev="Young Horses",          pub="Young Horses",       rating=4.5, popularity=700, ftp=False, appid=1287830),
    dict(title="Chicory: A Colorful Tale",      category="Adventure",  dev="Greg Lobanov",          pub="Finji",              rating=4.8, popularity=700, ftp=False, appid=1123450),
    dict(title="Frog Detective Trilogy",        category="Adventure",  dev="Grace Bruxner",         pub="Worm Club",          rating=4.8, popularity=650, ftp=False, appid=1445870),
    dict(title="Coffee Talk",                   category="Adventure",  dev="Toge Productions",      pub="Toge Productions",   rating=4.7, popularity=680, ftp=False, appid=1090190),
    dict(title="Coffee Talk Episode 2",         category="Adventure",  dev="Toge Productions",      pub="Toge Productions",   rating=4.6, popularity=660, ftp=False, appid=1904800),
    dict(title="VA-11 Hall-A",                  category="Adventure",  dev="Sukeban Games",         pub="Ysbryd Games",       rating=4.8, popularity=700, ftp=False, appid=574420),
    dict(title="Emily is Away Too",             category="Adventure",  dev="Kyle Seeley",           pub="Kyle Seeley",        rating=4.5, popularity=620, ftp=False, appid=641760),
    dict(title="Celestia: Chain of Fate",       category="Adventure",  dev="Starfall Studio",       pub="Starfall Studio",    rating=4.3, popularity=600, ftp=False, appid=None),
]

COVER_COLORS = ["1a1a2e", "16213e", "0f3460", "533483", "e94560", "2b2d42", "222831", "393e46"]


def _game_cover(title, appid=None):
    """Returns the best available cover image for a game.
    Games with a Steam App ID get a real cover image from Steam CDN.
    Games without a Steam App ID fall back to the sleek local SVG placeholder."""
    if appid:
        return f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900.jpg"
    return "/static/img/placeholder.svg"


def _game_banner(appid=None):
    """Wide header/banner image (460x215) from Steam CDN, or empty string."""
    if appid:
        return f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"
    return ""


def populate_seed_data(drop=False):
    if drop:
        db.drop_all()
        db.create_all()

    # --- Users ---
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(username="admin", email="admin@gamevault.com", is_admin=True)
        admin.set_password("Admin@123")
        db.session.add(admin)

    demo = User.query.filter_by(username="demo_player").first()
    if not demo:
        demo = User(username="demo_player", email="demo@gamevault.com", is_admin=False)
        demo.set_password("Demo@123")
        db.session.add(demo)

    # --- Platforms ---
    platform_objs = {}
    for name in PLATFORMS:
        p = Platform.query.filter_by(name=name).first()
        if not p:
            p = Platform(name=name, brand_color=PLATFORM_BRAND_COLORS.get(name, "#00f5ff"))
            db.session.add(p)
        platform_objs[name] = p

    # --- Categories ---
    category_objs = {}
    for name in CATEGORIES:
        c = Category.query.filter_by(name=name).first()
        if not c:
            c = Category(name=name, slug=name.lower())
            db.session.add(c)
        category_objs[name] = c

    db.session.commit()
    platform_objs = {p.name: p for p in Platform.query.all()}
    category_objs = {c.name: c for c in Category.query.all()}

    if Game.query.first() is not None and not drop:
        return

    # --- Games + platform listings + price history + deals ---
    for i, g in enumerate(GAMES):
        slug = g["title"].lower().replace(" ", "-").replace(":", "").replace("'", "").replace("!", "")
        # random release date between 1 and 5 years ago
        release = date.today() - timedelta(days=random.randint(365, 365 * 5))
        game = Game(
            title=g["title"],
            slug=slug,
            steam_app_id=g.get("appid"),
            description=(
                f"{g['title']} is an acclaimed {g['category'].lower()} title from {g['dev']}, "
                f"published by {g['pub']}. Featuring a rich world, tight mechanics, and a "
                f"dedicated community of players since launch."
            ),
            cover_image=_game_cover(g["title"], g.get("appid")),
            banner_image=_game_banner(g.get("appid")),
            developer=g["dev"],
            publisher=g["pub"],
            release_date=release,
            rating=g["rating"],
            popularity_score=g["popularity"],
            category_id=category_objs[g["category"]].id,
            is_free_to_play=g["ftp"],
        )
        db.session.add(game)
        db.session.commit()

        base_price = 0.0 if g["ftp"] else round(random.uniform(19.99, 69.99), 2)
        num_platforms = random.randint(2, 5)
        chosen_platforms = random.sample(PLATFORMS, min(num_platforms, len(PLATFORMS)))

        for plat_name in chosen_platforms:
            platform = platform_objs[plat_name]
            discount = 0 if g["ftp"] else random.choice([0, 0, 10, 20, 25, 33, 40, 50, 60, 75])
            current = round(base_price * (1 - discount / 100), 2)

            # Build the most specific URL available:
            # Steam → direct app page, others → search URL with title,
            # so Buy buttons never land on a bare homepage.
            if plat_name == "Steam" and g.get("appid"):
                seed_url = build_store_url(
                    store_name="Steam",
                    game_title=g["title"],
                    steam_app_id=g["appid"],
                )
            else:
                seed_url = build_store_url(
                    store_name=plat_name,
                    game_title=g["title"],
                )

            listing = GamePlatform(
                game_id=game.id,
                platform_id=platform.id,
                original_price=base_price,
                current_price=current,  # 0.0 for F2P, real price otherwise
                discount_percent=discount,
                store_url=seed_url,
                in_stock=True,
            )
            db.session.add(listing)

            # 6 months of fabricated price history for the chart
            price = base_price
            for week in range(24, 0, -1):
                drift = random.choice([-0.05, 0, 0, 0.05, -0.1, 0.1])
                price = max(0, round(price * (1 + drift), 2))
                db.session.add(
                    PriceHistory(
                        game_id=game.id,
                        platform_id=platform.id,
                        price=price,
                        recorded_at=datetime.utcnow() - timedelta(weeks=week),
                    )
                )

            if discount >= 10:
                is_free_deal = g["ftp"] and discount == 0
                deal_type = "free" if g["ftp"] else "discount"
                db.session.add(
                    Deal(
                        game_id=game.id,
                        platform_id=platform.id,
                        deal_type=deal_type,
                        discount_percent=discount,
                        starts_at=datetime.utcnow() - timedelta(days=random.randint(0, 5)),
                        expires_at=datetime.utcnow() + timedelta(days=random.randint(1, 14)),
                        is_featured=discount >= 50,
                    )
                )

        if g["ftp"]:
            # ensure every free-to-play game has an explicit "free" deal entry
            platform = platform_objs[chosen_platforms[0]]
            db.session.add(
                Deal(
                    game_id=game.id,
                    platform_id=platform.id,
                    deal_type=random.choice(["free", "giveaway", "weekend_ftp"]),
                    discount_percent=100,
                    expires_at=datetime.utcnow() + timedelta(days=random.randint(1, 10)),
                    is_featured=True,
                )
            )

        # a couple of demo reviews per game
        if random.random() > 0.4:
            db.session.add(
                Review(
                    user_id=demo.id,
                    game_id=game.id,
                    rating=random.randint(3, 5),
                    comment=random.choice([
                        "Solid gameplay loop, well worth it on sale.",
                        "Great visuals and a gripping story.",
                        "A bit buggy at launch but much improved now.",
                        "One of my favorites this year!",
                    ]),
                )
            )

    db.session.commit()


def run_seed():
    app = create_app()
    with app.app_context():
        populate_seed_data(drop=True)


if __name__ == "__main__":
    run_seed()
