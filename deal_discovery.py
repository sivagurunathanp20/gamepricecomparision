"""
deal_discovery.py
=================================================================
Finds NEW free-game and limited-time deals automatically, so the
"Free Games" / "Deals" pages keep refilling themselves once an
existing promo's time limit runs out — instead of needing an admin
to manually add the next one.

Two sources:

1. CheapShark "upperPrice=0" deals -> games that are currently free
   across Steam/Epic/GOG/Humble/Fanatical/GMG etc. CheapShark doesn't
   report an expiry date for these, so we assume a short window
   (DEFAULT_FREE_DEAL_DURATION_DAYS) and simply extend it on the next
   run for as long as CheapShark still reports the game as free.

2. Epic Games' public free-games-promotion feed -> the weekly Epic
   freebies, which DO have exact start/end timestamps, so those get
   an accurate expires_at. This is the classic "time limit ends"
   case the site needs to react to.

Both sources reuse the Game/Platform/Deal/GamePlatform models. A
title already in the catalogue is matched (by steam_app_id first,
then exact title) rather than duplicated, and re-running this job
never creates duplicate Deal rows for the same game+store+type — it
either finds nothing to do or extends the existing row's expiry.

Pairs with scheduler.py's job_cleanup_expired_deals: cleanup REMOVES
a deal once expires_at passes; this module is what RE-FILLS the
page with whatever is newly free/on sale. Run both on a schedule and
the free-games/deals pages stay current with zero manual work.
"""
import logging
import re
from datetime import datetime, timedelta

import requests

from store_apis import CHEAPSHARK_STORE_MAP, PLATFORM_BRAND_COLORS, build_store_url

logger = logging.getLogger("deal_discovery")

CHEAPSHARK_BASE = "https://www.cheapshark.com/api/1.0"
CHEAPSHARK_HEADERS = {
    "User-Agent": "GameVault/1.0 (academic project; github.com/gamevault)"
}
EPIC_FREE_GAMES_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
REQUEST_TIMEOUT = 8

# CheapShark gives no expiry for "currently free" deals, so we assume this
# window and let the next run extend it for as long as it's still free.
DEFAULT_FREE_DEAL_DURATION_DAYS = 3


# =================================================================
# Small helpers (Game / Platform / Deal upserts)
# =================================================================

def _slugify(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "game"


def _unique_slug(title):
    from models import Game
    base = _slugify(title)
    slug = base
    n = 2
    while Game.query.filter_by(slug=slug).first():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _get_or_create_game(title, steam_app_id=None, cover_image=None):
    """Matches an existing Game by steam_app_id (preferred) or exact title;
    creates a minimal row if neither exists. Never overwrites an existing
    game's data — discovery only fills in what's missing (e.g. a blank
    cover image), it never touches a game an admin has already curated."""
    from extensions import db
    from models import Game

    game = None
    if steam_app_id:
        game = Game.query.filter_by(steam_app_id=steam_app_id).first()
    if not game and title:
        game = Game.query.filter(Game.title.ilike(title)).first()

    if game:
        if cover_image and not game.cover_image:
            game.cover_image = cover_image
        return game, False

    game = Game(
        title=title,
        slug=_unique_slug(title),
        steam_app_id=steam_app_id,
        cover_image=cover_image or "",
        popularity_score=0,
    )
    db.session.add(game)
    db.session.flush()  # get game.id without a full commit
    return game, True


def _get_or_create_platform(name):
    from extensions import db
    from models import Platform

    platform = Platform.query.filter_by(name=name).first()
    if not platform:
        platform = Platform(name=name, brand_color=PLATFORM_BRAND_COLORS.get(name, "#00f5ff"))
        db.session.add(platform)
        db.session.flush()
    return platform


def _upsert_free_deal(game, platform, expires_at, store_url=None, deal_type="free"):
    """Creates the Deal row if there isn't already an active one for this
    game+platform+type; otherwise just extends its expiry. This is what
    makes the job safe to re-run every few hours without ever duplicating
    rows on the free-games page."""
    from extensions import db
    from models import Deal, GamePlatform

    now = datetime.utcnow()
    existing = (
        Deal.query.filter_by(game_id=game.id, platform_id=platform.id, deal_type=deal_type)
        .filter((Deal.expires_at.is_(None)) | (Deal.expires_at >= now))
        .first()
    )
    if existing:
        if expires_at and (existing.expires_at is None or expires_at > existing.expires_at):
            existing.expires_at = expires_at
        return existing, False

    deal = Deal(
        game_id=game.id,
        platform_id=platform.id,
        deal_type=deal_type,
        discount_percent=100,
        expires_at=expires_at,
    )
    db.session.add(deal)

    # A promo is only a *claim*. The price (0) and Buy link are written later
    # by official_prices.verify_listing, never copied from the promo feed.
    listing = GamePlatform.query.filter_by(game_id=game.id, platform_id=platform.id).first()
    if not listing:
        listing = GamePlatform(game_id=game.id, platform_id=platform.id)
        db.session.add(listing)
    listing.source = "auto-discovery"
    # Mark the listing as free immediately so _deal_is_verified() can pass
    # (current_price == 0 is the check). The official-price verifier will
    # overwrite this with a properly verified 0 if/when it runs.
    if listing.current_price is None:
        listing.current_price = 0
        listing.discount_percent = 100

    return deal, True


# =================================================================
# Source 1 — CheapShark: currently-free deals (upperPrice=0)
# =================================================================

def _fetch_cheapshark_free_deals(limit=25):
    try:
        resp = requests.get(
            f"{CHEAPSHARK_BASE}/deals",
            params={"upperPrice": 0, "pageSize": limit, "sortBy": "Recent", "desc": 1},
            headers=CHEAPSHARK_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json() or []
    except Exception as exc:
        logger.warning(f"CheapShark free-deals fetch failed: {exc}")
        return []


def discover_from_cheapshark():
    added, extended = 0, 0
    for deal in _fetch_cheapshark_free_deals():
        title = (deal.get("title") or "").strip()
        if not title:
            continue
        try:
            price = float(deal.get("salePrice", deal.get("price", 0)) or 0)
        except (TypeError, ValueError):
            continue
        if price > 0:
            continue  # not actually free right now — skip

        store_name = CHEAPSHARK_STORE_MAP.get(str(deal.get("storeID")))
        if not store_name:
            continue  # store we don't track

        steam_app_id = deal.get("steamAppID")
        steam_app_id = int(steam_app_id) if steam_app_id else None
        cover_image = deal.get("thumb") or None
        deal_id = deal.get("dealID", "")
        # CheapShark redirect is the best URL for a sale; build_store_url
        # will fall back to a search page if no dealID comes through.
        store_url = build_store_url(
            store_name=store_name,
            game_title=title,
            steam_app_id=steam_app_id if store_name == "Steam" else None,
            deal_id=deal_id or None,
        )
        expires_at = datetime.utcnow() + timedelta(days=DEFAULT_FREE_DEAL_DURATION_DAYS)

        # Only Steam promos are kept: a Steam app id is an exact identity that
        # the official verifier can confirm. Other aggregator promos can't be verified.
        if store_name != "Steam" or not steam_app_id:
            continue
        game, _ = _get_or_create_game(title, steam_app_id=steam_app_id, cover_image=cover_image)
        platform = _get_or_create_platform(store_name)
        _, created_deal = _upsert_free_deal(game, platform, expires_at, store_url=store_url)
        try:
            from official_prices import ensure_steam_listing, verify_listing
            verify_listing(ensure_steam_listing(game))
        except Exception as exc:
            logger.warning(f"verification of free promo failed: {exc}")

        added += created_deal
        extended += not created_deal

    return added, extended


# =================================================================
# Source 2 — Epic Games: weekly free-games promotion (real expiry dates)
# =================================================================

def discover_from_epic():
    added, extended = 0, 0
    try:
        resp = requests.get(
            EPIC_FREE_GAMES_URL,
            params={"locale": "en-US", "country": "US", "allowCountries": "US"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        elements = (
            resp.json()
            .get("data", {})
            .get("Catalog", {})
            .get("searchStore", {})
            .get("elements", [])
        )
    except Exception as exc:
        logger.warning(f"Epic free-games fetch failed: {exc}")
        return added, extended

    platform = _get_or_create_platform("Epic Games Store")

    for item in elements:
        promo_blocks = (item.get("promotions") or {}).get("promotionalOffers") or []
        active_windows = [w for block in promo_blocks for w in block.get("promotionalOffers", [])]
        if not active_windows:
            continue  # listed but not free RIGHT NOW (could be a future/upcoming freebie)

        title = (item.get("title") or "").strip()
        if not title:
            continue

        try:
            expires_at = datetime.strptime(active_windows[0]["endDate"], "%Y-%m-%dT%H:%M:%S.%fZ")
        except (KeyError, ValueError):
            expires_at = datetime.utcnow() + timedelta(days=7)

        images = item.get("keyImages") or []
        cover_image = next(
            (im["url"] for im in images if im.get("type") in ("Thumbnail", "OfferImageWide")), None
        )
        slug = (item.get("productSlug") or item.get("urlSlug") or "").strip("/")
        epic_url = f"https://store.epicgames.com/en-US/p/{slug}" if slug else None
        # Pass the Epic slug URL as existing_url — build_store_url will
        # keep it if valid, or fall back to an Epic search URL if the slug
        # is missing.
        store_url = build_store_url(
            store_name="Epic Games Store",
            game_title=title,
            existing_url=epic_url,
        )

        game, _ = _get_or_create_game(title, cover_image=cover_image)
        _, created_deal = _upsert_free_deal(game, platform, expires_at, store_url=store_url)
        namespace = (item.get("namespace") or "").strip()
        if namespace:
            try:
                from official_prices import register_official_product, verify_listing
                verify_listing(register_official_product(game, "Epic Games Store", product_id=namespace))
            except Exception as exc:
                logger.warning(f"verification of Epic freebie failed: {exc}")

        added += created_deal
        extended += not created_deal

    return added, extended


# =================================================================
# Entry point
# =================================================================

def discover_new_deals():
    """Runs both sources and commits once at the end. Never raises —
    each source is independently guarded, matching store_apis.py's
    'one failing source never blocks the others' pattern."""
    from extensions import db

    cs_added = cs_extended = epic_added = epic_extended = 0

    try:
        cs_added, cs_extended = discover_from_cheapshark()
    except Exception as exc:
        logger.warning(f"CheapShark discovery failed: {exc}")

    try:
        epic_added, epic_extended = discover_from_epic()
    except Exception as exc:
        logger.warning(f"Epic discovery failed: {exc}")

    db.session.commit()

    summary = {
        "cheapshark_added": cs_added,
        "cheapshark_extended": cs_extended,
        "epic_added": epic_added,
        "epic_extended": epic_extended,
    }
    logger.info(f"[deal_discovery] done — {summary}")
    return summary
