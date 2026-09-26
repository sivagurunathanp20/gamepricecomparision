"""
store_apis.py
=================================================================
Handles two things automatically, with no manual uploads needed:

1. STEAM IMAGES
   Steam serves predictable, public CDN image URLs for every App ID —
   no API key or auth required. We build these URLs directly from the
   Steam App ID and (optionally) verify they resolve with a cheap HEAD
   request, falling back to a generic placeholder if not.

2. MULTI-STORE PRICE COMPARISON
   There is no single free API that covers Epic/GOG/Humble/Fanatical/
   Green Man Gaming/Ubisoft/EA/Xbox individually — most of those stores
   don't offer public, keyless pricing APIs at all. Two real aggregators
   fill that gap, and this module uses both:

   - CheapShark (https://apidocs.cheapshark.com) — completely free, NO
     API KEY REQUIRED, works out of the box. Covers Steam, GOG, Humble
     Store, Fanatical, Green Man Gaming, Epic Games Store, Origin (EA),
     Ubisoft Store, Gamesplanet, and more. This is the primary source.

   - IsThereAnyDeal (ITAD, https://isthereanydeal.com/apps/) — also free,
     but needs a personal API key (one signup, no cost). Used as a
     secondary source to fill in anything CheapShark doesn't have.

   Steam itself is always fetched directly (no key needed) as the most
   authoritative source for that one store.

Every external call in this file is wrapped in try/except: a failure on
one store never blocks the others, and results are cached in memory for
CACHE_TTL_SECONDS so repeated page loads don't hammer the APIs.
=================================================================
"""
import os
import time
import logging
from urllib.parse import quote_plus

import requests

logger = logging.getLogger("store_apis")

CACHE_TTL_SECONDS = 1800  # 30 minutes
REQUEST_TIMEOUT = 8

ITAD_API_KEY = os.environ.get("ITAD_API_KEY", "").strip()
ITAD_BASE = "https://api.isthereanydeal.com"

CHEAPSHARK_BASE = "https://www.cheapshark.com/api/1.0"
# CheapShark now enforces a descriptive User-Agent; requests without one get HTTP 400.
CHEAPSHARK_HEADERS = {
    "User-Agent": "GameVault/1.0 (academic project; github.com/gamevault)"
}

# Per-store search URL templates. Use {title} as the URL-encoded game title
# placeholder. These are used as the primary fallback when no exact product
# URL is known, sending users directly to a useful search-results page
# rather than a generic homepage.
#
# Pattern: build_store_url() substitutes quote_plus(game_title) for {title}.
STORE_SEARCH_URL_TEMPLATES = {
    "Steam":             "https://store.steampowered.com/search/?term={title}",
    "Epic Games Store":  "https://store.epicgames.com/en-US/browse?q={title}&sortBy=relevancy",
    "GOG":               "https://www.gog.com/games?query={title}",
    "Humble Bundle":     "https://www.humblebundle.com/store/search?search={title}",
    "Fanatical":         "https://www.fanatical.com/en/search?search={title}",
    "Green Man Gaming":  "https://www.greenmangaming.com/search?query={title}",
    "Ubisoft Connect":   "https://store.ubisoft.com/us/search?search={title}",
    "EA App":            "https://www.ea.com/search#q={title}",
    "PlayStation Store": "https://store.playstation.com/en-us/search/{title}",
    "Xbox Store":        "https://www.xbox.com/en-US/search?q={title}",
    "Nintendo eShop":    "https://www.nintendo.com/us/search/?q={title}",
    "WinGameStore":      "https://www.wingamestore.com/search/?term={title}",
    "GameBillet":        "https://www.gamebillet.com/search?search={title}",
    "Gamesplanet":       "https://us.gamesplanet.com/search?search={title}",
    "GamersGate":        "https://www.gamersgate.com/games/?q={title}",
    "Gamesload":         "https://www.gamesload.com/search?searchKey={title}",
    "IndieGala":         "https://www.indiegala.com/search#search/{title}",
    "DreamGame":         "https://www.dreamgame.com/search?q={title}",
}

# Last-resort homepages — only used when no search template exists for the store.
# Not exported; prefer build_store_url() which uses the search templates first.
_STORE_HOMEPAGE_URLS = {
    "Steam":             "https://store.steampowered.com/",
    "Epic Games Store":  "https://store.epicgames.com/en-US/",
    "GOG":               "https://www.gog.com/",
    "PlayStation Store": "https://store.playstation.com/",
    "Xbox Store":        "https://www.xbox.com/en-US/games/store",
    "Nintendo eShop":    "https://www.nintendo.com/us/store/games/",
    "Humble Bundle":     "https://www.humblebundle.com/store",
    "Fanatical":         "https://www.fanatical.com/",
    "Green Man Gaming":  "https://www.greenmangaming.com/",
    "Ubisoft Connect":   "https://store.ubisoft.com/",
    "EA App":            "https://www.ea.com/games",
    "WinGameStore":      "https://www.wingamestore.com/",
    "GameBillet":        "https://www.gamebillet.com/",
    "Gamesplanet":       "https://us.gamesplanet.com/",
    "GamersGate":        "https://www.gamersgate.com/",
    "Gamesload":         "https://www.gamesload.com/",
    "IndieGala":         "https://www.indiegala.com/store",
    "DreamGame":         "https://www.dreamgame.com/",
}

PLACEHOLDER_IMAGE = "https://placehold.co/500x700/1a1a2e/ffffff?text=No+Image"


def _normalize_url(url):
    """Lower-cases and strips trailing slashes so homepage comparisons
    aren't fooled by 'https://www.gog.com' vs 'https://www.gog.com/'."""
    return (url or "").strip().lower().rstrip("/")


_BARE_HOMEPAGES = {_normalize_url(u) for u in _STORE_HOMEPAGE_URLS.values()}


def is_bad_store_url(url):
    """True when a stored URL is unusable as a Buy link: empty, '#', or a
    bare store homepage (which doesn't take the user to the game)."""
    cleaned = (url or "").strip()
    if cleaned in ("", "#"):
        return True
    return _normalize_url(cleaned) in _BARE_HOMEPAGES


def build_store_url(store_name, game_title=None, steam_app_id=None, deal_id=None, existing_url=None):
    """Returns an EXACT official product-page URL or None.
    Search pages, homepages and aggregator redirects are never returned:
    a missing link is better than a wrong one."""
    from official_prices import validate_official_url
    if existing_url and validate_official_url(store_name, existing_url):
        return existing_url.strip()
    if store_name == "Steam" and steam_app_id:
        return f"https://store.steampowered.com/app/{steam_app_id}"
    return None


# Maps the shop names ITAD returns to the Platform rows we already have
# (or a sensible new Platform name if ITAD returns a store we don't).
ITAD_SHOP_NAME_MAP = {
    "steam": "Steam",
    "epic games store": "Epic Games Store",
    "epic": "Epic Games Store",
    "gog": "GOG",
    "gog.com": "GOG",
    "humble store": "Humble Bundle",
    "humble bundle": "Humble Bundle",
    "fanatical": "Fanatical",
    "green man gaming": "Green Man Gaming",
    "microsoft store": "Xbox Store",
    "xbox": "Xbox Store",
    "ubisoft store": "Ubisoft Connect",
}

# CheapShark's storeID -> our Platform name. (GET /stores for the full,
# occasionally-changing list — these are the stable, currently-active ones.)
# Last verified against https://www.cheapshark.com/api/1.0/stores (2026-09-21).
CHEAPSHARK_STORE_MAP = {
    "1":  "Steam",
    "2":  "GamersGate",
    "3":  "Green Man Gaming",
    "7":  "GOG",
    "11": "Humble Bundle",
    "13": "Ubisoft Connect",   # CheapShark lists as "Uplay" but same storefront
    "15": "Fanatical",
    "21": "WinGameStore",
    "23": "GameBillet",
    "25": "Epic Games Store",
    "27": "Gamesplanet",
    "28": "Gamesload",
    "30": "IndieGala",
    "35": "DreamGame",
}

# A recognizable accent color per store for badges in the UI.
PLATFORM_BRAND_COLORS = {
    "Steam": "#1a9fff",
    "Epic Games Store": "#8b5cf6",
    "GOG": "#a855f7",
    "Humble Bundle": "#cc2929",
    "Fanatical": "#e8a318",
    "Green Man Gaming": "#00966d",
    "Ubisoft Connect": "#0070ff",
    "Xbox Store": "#0e7a0e",
    "PlayStation Store": "#0070d1",
    "EA App": "#e63946",
    "Gamesplanet": "#c47f0e",
    "GamersGate": "#e85d04",
    "Gamesload": "#7209b7",
    "IndieGala": "#f72585",
    "DreamGame": "#4cc9f0",
    "WinGameStore": "#43aa8b",
    "GameBillet": "#f4a261",
}

# ---------------------------------------------------------------
# Simple in-memory TTL cache (per process). Good enough for a
# college project; swap for Redis/Flask-Caching in real production.
# ---------------------------------------------------------------
_cache = {}


def _cache_get(key):
    entry = _cache.get(key)
    if not entry:
        return None
    value, expires_at = entry
    if time.time() > expires_at:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key, value, ttl=CACHE_TTL_SECONDS):
    _cache[key] = (value, time.time() + ttl)


# =================================================================
# 1. STEAM IMAGES (automatic, no upload, no API key needed)
# =================================================================

def steam_image_urls(steam_app_id):
    """Deterministic Steam CDN image URLs for a given App ID.
    No API call needed — Steam's asset CDN is keyed purely by App ID."""
    if not steam_app_id:
        return {}
    base = f"https://cdn.akamai.steamstatic.com/steam/apps/{steam_app_id}"
    return {
        "header": f"{base}/header.jpg",          # 460x215, used across the site
        "capsule": f"{base}/capsule_616x353.jpg",  # store capsule
        "library": f"{base}/library_600x900.jpg",  # tall cover, best for cards
    }


def _url_is_reachable(url):
    cache_key = f"img_check::{url}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    ok = False
    try:
        resp = requests.head(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        ok = resp.status_code == 200
    except Exception as exc:
        logger.warning(f"Image HEAD check failed for {url}: {exc}")
        ok = False

    _cache_set(cache_key, ok, ttl=CACHE_TTL_SECONDS)
    return ok


def resolve_game_image(steam_app_id=None, fallback_url=None, verify=True):
    """Best available image for a game, in priority order:
    Steam library cover -> Steam header -> fallback_url -> placeholder.
    Set verify=False to skip the HEAD request (faster, less accurate —
    fine for bulk seeding where you already trust the App ID)."""
    if steam_app_id:
        urls = steam_image_urls(steam_app_id)
        for key in ("library", "header"):
            candidate = urls.get(key)
            if candidate and (not verify or _url_is_reachable(candidate)):
                return candidate

    if fallback_url:
        return fallback_url

    return PLACEHOLDER_IMAGE


# =================================================================
# 2a. MULTI-STORE PRICES via CheapShark (free, no API key required)
# =================================================================

def cheapshark_lookup_game_id(title=None, steam_app_id=None):
    """Resolves a title or Steam App ID to CheapShark's internal gameID."""
    cache_key = f"cs_lookup::{steam_app_id}::{title}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    game_id = None
    try:
        if steam_app_id:
            resp = requests.get(
                f"{CHEAPSHARK_BASE}/games",
                params={"steamAppID": steam_app_id},
                headers=CHEAPSHARK_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            results = resp.json()
            if results:
                game_id = results[0].get("gameID") if isinstance(results, list) else results.get("gameID")
        if not game_id and title:
            resp = requests.get(
                f"{CHEAPSHARK_BASE}/games",
                params={"title": title, "limit": 1, "exact": 0},
                headers=CHEAPSHARK_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            results = resp.json()
            if results:
                game_id = results[0].get("gameID")
    except Exception as exc:
        logger.warning(f"CheapShark lookup failed for title={title} appid={steam_app_id}: {exc}")
        game_id = None

    _cache_set(cache_key, game_id)
    return game_id


def cheapshark_fetch_prices(cheapshark_game_id):
    """Returns a list of {shop, current_price, original_price,
    discount_percent, store_url, historical_low} dicts — one per store
    CheapShark currently tracks a deal for — plus the all-time cheapest
    price it has ever recorded for this game."""
    if not cheapshark_game_id:
        return [], None

    cache_key = f"cs_prices::{cheapshark_game_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    results = []
    historical_low = None
    try:
        resp = requests.get(
            f"{CHEAPSHARK_BASE}/games",
            params={"id": cheapshark_game_id},
            headers=CHEAPSHARK_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()

        cheapest_ever = payload.get("cheapestPriceEver", {})
        historical_low = float(cheapest_ever["price"]) if cheapest_ever.get("price") else None

        for deal in payload.get("deals", []):
            store_id = str(deal.get("storeID"))
            shop_name = CHEAPSHARK_STORE_MAP.get(store_id)
            if not shop_name:
                continue  # skip defunct/unmapped stores rather than guess a name

            try:
                current = float(deal["price"])
                original = float(deal["retailPrice"])
            except (TypeError, ValueError, KeyError):
                continue

            results.append({
                "shop": shop_name,
                "current_price": current,
                "original_price": original,
                "discount_percent": round(float(deal.get("savings", 0))),
                "store_url": f"https://www.cheapshark.com/redirect?dealID={deal.get('dealID', '')}",
                "historical_low": historical_low,
            })

        _cache_set(cache_key, (results, historical_low))
    except Exception as exc:
        logger.warning(f"CheapShark price fetch failed for game_id={cheapshark_game_id}: {exc}")
        return [], None

    return results, historical_low


# =================================================================
# 2b. MULTI-STORE PRICES via IsThereAnyDeal (free, needs a personal key)
# =================================================================

def itad_enabled():
    return bool(ITAD_API_KEY)


def itad_lookup_game_id(title=None, steam_app_id=None):
    """Resolves a game title or Steam App ID to ITAD's internal game id."""
    if not itad_enabled():
        return None

    cache_key = f"itad_lookup::{steam_app_id}::{title}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Use ITAD-API-Key header (preferred since v2.9) instead of key= query param.
    _itad_headers = {"ITAD-API-Key": ITAD_API_KEY}
    try:
        if steam_app_id:
            resp = requests.get(
                f"{ITAD_BASE}/games/lookup/v1",
                params={"appid": steam_app_id},
                headers=_itad_headers,
                timeout=REQUEST_TIMEOUT,
            )
        else:
            resp = requests.get(
                f"{ITAD_BASE}/games/lookup/v1",
                params={"title": title},
                headers=_itad_headers,
                timeout=REQUEST_TIMEOUT,
            )
        resp.raise_for_status()
        data = resp.json()
        game_id = data.get("game", {}).get("id") if data.get("found") else None
        _cache_set(cache_key, game_id)
        return game_id
    except Exception as exc:
        logger.warning(f"ITAD lookup failed for title={title} appid={steam_app_id}: {exc}")
        return None


def itad_fetch_prices(itad_game_id, country="US"):
    """Returns a list of {shop, current_price, original_price,
    discount_percent, store_url} dicts, one per store ITAD tracks
    a live deal for. Empty list on any failure — callers should treat
    that as 'no additional stores found', not an error."""
    if not itad_enabled() or not itad_game_id:
        return []

    cache_key = f"itad_prices::{itad_game_id}::{country}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    results = []
    try:
        # Upgraded to /v3 (adds 'deals' param); ITAD-API-Key header preferred since v2.9.
        resp = requests.post(
            f"{ITAD_BASE}/games/prices/v3",
            params={"country": country},
            headers={"ITAD-API-Key": ITAD_API_KEY},
            json=[itad_game_id],
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()

        entries = payload[0].get("deals", []) if payload else []
        for deal in entries:
            shop_name_raw = (deal.get("shop", {}).get("name") or "").strip()
            mapped_name = ITAD_SHOP_NAME_MAP.get(shop_name_raw.lower(), shop_name_raw or "Other Store")

            results.append({
                "shop": mapped_name,
                "current_price": deal.get("price", {}).get("amount"),
                "original_price": deal.get("regular", {}).get("amount"),
                "discount_percent": int(deal.get("cut", 0)),
                "store_url": deal.get("url") or None,  # None means no link, never '#'
            })

        _cache_set(cache_key, results)
    except Exception as exc:
        logger.warning(f"ITAD price fetch failed for game_id={itad_game_id}: {exc}")
        return []

    return results


def sync_game_from_apis(game):
    """Kept for the admin/CLI callers. Prices now come ONLY from the game's
    official store (official_prices.py); CheapShark/ITAD are no longer used
    for displayed prices."""
    from official_prices import verify_game
    summary = {"image_updated": False, "stores_updated": 0, "stores_failed": 0, "sources_used": ["official stores"]}
    if game.steam_app_id:
        new_image = resolve_game_image(steam_app_id=game.steam_app_id, fallback_url=game.cover_image)
        if new_image and new_image != game.cover_image:
            game.cover_image = new_image
            summary["image_updated"] = True
    for status in verify_game(game).values():
        if status == "verified":
            summary["stores_updated"] += 1
        else:
            summary["stores_failed"] += 1
    return summary
