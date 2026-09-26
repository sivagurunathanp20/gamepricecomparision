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
]

COVER_COLORS = ["1a1a2e", "16213e", "0f3460", "533483", "e94560", "2b2d42", "222831", "393e46"]


def _game_cover(title, appid=None):
    """Returns the best available cover image for a game.
    Games with a Steam App ID get a real 600x900 library cover image from
    Steam's public CDN — no API key required, loads instantly.
    Games without a Steam App ID fall back to a styled placeholder."""
    if appid:
        return f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900.jpg"
    color = random.choice(COVER_COLORS)
    text = title.replace(" ", "+").replace(":", "")
    return f"https://placehold.co/600x900/{color}/ffffff?text={text}"


def _game_banner(appid=None):
    """Wide header/banner image (460x215) from Steam CDN, or empty string."""
    if appid:
        return f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"
    return ""


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
        platform_objs = {}
        for name in PLATFORMS:
            p = Platform(name=name, brand_color=PLATFORM_BRAND_COLORS.get(name, "#00f5ff"))
            db.session.add(p)
            platform_objs[name] = p

        # --- Categories ---
        category_objs = {}
        for name in CATEGORIES:
            c = Category(name=name, slug=name.lower())
            db.session.add(c)
            category_objs[name] = c

        db.session.commit()

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
        print(f"Seeded {len(GAMES)} games across {len(PLATFORMS)} platforms.")


if __name__ == "__main__":
    run_seed()
