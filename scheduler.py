"""
scheduler.py
============
Background scheduler that keeps deal data fresh automatically.

Jobs:
  - sync_prices          : Every 6 hours  — refresh prices/images for all
                           games that have a steam_app_id via CheapShark/ITAD.
  - discover_new_deals   : Every 3 hours  — find NEW free-games/limited-time
                           deals (CheapShark + Epic's weekly freebies) and
                           add them automatically. This is what refills the
                           Free Games / Deals pages once an old promo's time
                           limit ends — pairs with cleanup_expired_deals below.
  - cleanup_expired_deals: Every 1 hour   — delete Deal rows whose expires_at
                           is in the past and mark stale GamePlatform rows as
                           out-of-stock.

The scheduler is a daemon BackgroundScheduler (APScheduler) so it runs inside
the same Python process as Flask/gunicorn without needing a separate worker,
Redis, or Celery.  Works in both dev (flask run) and production (gunicorn).
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("scheduler")

# ── one global instance, started once inside create_app() ─────────────────────
scheduler = BackgroundScheduler(daemon=True)


# =============================================================================
# Job 1 — Price & image sync  (every 6 hours)
# =============================================================================

def job_sync_all_prices(app):
    """Re-verify every game's price against its official store(s)."""
    with app.app_context():
        from official_prices import verify_all, expire_stale_prices
        counts = verify_all()
        expired = expire_stale_prices()
        logger.info("[scheduler] official price verification: %s (expired %d stale)", counts, expired)


# =============================================================================
# Job 2 — Discover new free-games / deals  (every 3 hours)
# =============================================================================

def job_discover_new_deals(app):
    """Finds newly-free / newly-on-sale games (CheapShark + Epic's weekly
    freebies) and adds them so the Free Games / Deals pages refill
    automatically once an old promo expires."""
    with app.app_context():
        from deal_discovery import discover_new_deals

        try:
            summary = discover_new_deals()
            logger.info(
                "[scheduler] discover_new_deals done — CheapShark: %d added/%d extended, "
                "Epic: %d added/%d extended.",
                summary["cheapshark_added"], summary["cheapshark_extended"],
                summary["epic_added"], summary["epic_extended"],
            )
        except Exception as exc:
            logger.warning("[scheduler] discover_new_deals failed: %s", exc)


# =============================================================================
# Job 3 — Expired deal cleanup  (every 1 hour)
# =============================================================================

def job_cleanup_expired_deals(app):
    """
    Delete Deal rows whose expires_at has passed.
    Also marks any GamePlatform row as out-of-stock when that store no longer
    has an active deal for the game (discount_percent drops to 0).
    """
    with app.app_context():
        from extensions import db
        from models import Deal, GamePlatform

        now = datetime.now(timezone.utc).replace(tzinfo=None)  # DB stores naive UTC

        # ── 1. Remove expired Deal rows ────────────────────────────────────────
        expired = Deal.query.filter(
            Deal.expires_at.isnot(None),
            Deal.expires_at < now,
        ).all()

        removed = len(expired)
        for deal in expired:
            db.session.delete(deal)

        # ── 2. Mark GamePlatform rows as out-of-stock when discount is 0 ──────
        # A listing that came from an auto-sync (source != "manual") but now
        # has a 0 % discount and no active Deal is effectively "not on sale".
        stale = GamePlatform.query.filter(
            GamePlatform.discount_percent == 0,
            GamePlatform.in_stock == True,           # noqa: E712
            GamePlatform.source != "manual",
            GamePlatform.verify_status != "verified",
        ).all()

        marked_stale = 0
        for listing in stale:
            # Only flip to out-of-stock if there is truly no active deal for
            # this game+platform combo (an expired free game, for example).
            has_active_deal = Deal.query.filter_by(
                game_id=listing.game_id,
                platform_id=listing.platform_id,
            ).filter(
                (Deal.expires_at.is_(None)) | (Deal.expires_at >= now)
            ).first()

            if not has_active_deal and (listing.current_price is None or listing.current_price > 0):
                listing.in_stock = False
                marked_stale += 1

        db.session.commit()
        logger.info(
            "[scheduler] cleanup done — removed %d expired deals, "
            "marked %d listings as out-of-stock.",
            removed, marked_stale,
        )


# =============================================================================
# Scheduler startup  (called from create_app in app.py)
# =============================================================================

def init_scheduler(app):
    """
    Register and start background jobs.  Safe to call multiple times —
    APScheduler's running check prevents double-registration in Flask's
    debug reloader (which forks the process).
    """
    if scheduler.running:
        return  # already started (e.g. Flask debug reloader second process)

    # Price sync — every 6 hours, first run 60 s after startup so the app
    # is fully initialised before the first (potentially slow) sync.
    scheduler.add_job(
        func=job_sync_all_prices,
        args=[app],
        trigger=IntervalTrigger(minutes=app.config.get("PRICE_REFRESH_MINUTES", 120)),
        id="sync_prices",
        name="Verify prices against official stores",
        replace_existing=True,
        max_instances=1,           # don't overlap if a run takes > 6 h
        misfire_grace_time=300,    # allow up to 5 min lateness before skipping
    )

    # Discover new free-games / deals — every 3 hours, first run 90 s after
    # startup (staggered after sync_prices' 60 s so they don't overlap).
    scheduler.add_job(
        func=job_discover_new_deals,
        args=[app],
        trigger=IntervalTrigger(hours=3),
        id="discover_new_deals",
        name="Discover new free games / deals (CheapShark + Epic)",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    # Expired deal cleanup — every 1 hour
    scheduler.add_job(
        func=job_cleanup_expired_deals,
        args=[app],
        trigger=IntervalTrigger(hours=1),
        id="cleanup_expired_deals",
        name="Remove expired free-game / deal rows",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    scheduler.start()
    logger.info(
        "[scheduler] started — sync_prices every 6 h, "
        "discover_new_deals every 3 h, cleanup_expired_deals every 1 h."
    )
