"""
slow_resync.py
==============
Re-verify all unverified/failed Steam listings with long inter-request
delays so Steam's rate limiter doesn't trigger again.

Usage:
    python slow_resync.py

The script will:
  1. Wait until Steam's API is healthy (polls every 60s, up to 30 min)
  2. Re-verify all unverified/failed Steam listings one at a time
  3. Sleep DELAY_BETWEEN_GAMES seconds between each game to stay under
     Steam's soft rate limit

Run this once after a rate-limit event to restore all prices.
"""
import time
import sys

DELAY_BETWEEN_GAMES = 8        # seconds between each game verify call
MAX_WAIT_FOR_STEAM = 30 * 60   # 30 minutes max wait for Steam to recover
POLL_INTERVAL = 60             # check Steam every 60 s while waiting


def main():
    from app import create_app
    app = create_app()
    with app.app_context():
        from official_prices import (
            _steam_is_healthy, _steam_sanity_cache, verify_listing,
            RateLimited, STEAM_SANITY_TTL_UNHEALTHY
        )
        from models import GamePlatform, Platform
        from extensions import db

        country = app.config.get("STORE_COUNTRY", "IN")

        # Step 1: Wait for Steam to become healthy
        print("Checking whether Steam is healthy...")
        waited = 0
        while not _steam_is_healthy(country):
            if waited >= MAX_WAIT_FOR_STEAM:
                print("Steam did not recover within 30 minutes. Aborting.")
                sys.exit(1)
            print(f"  Steam still rate-limiting. Waiting {POLL_INTERVAL}s "
                  f"(total waited: {waited}s / {MAX_WAIT_FOR_STEAM}s)...")
            _steam_sanity_cache["checked_at"] = None
            time.sleep(POLL_INTERVAL)
            waited += POLL_INTERVAL

        print("Steam is healthy! Starting re-verification.\n")

        # Step 2: Collect all Steam listings to re-verify
        steam_platform = Platform.query.filter_by(name="Steam").first()
        if not steam_platform:
            print("No Steam platform in DB. Nothing to do.")
            return

        pending = GamePlatform.query.filter(
            GamePlatform.platform_id == steam_platform.id,
            GamePlatform.verify_status.in_(["unverified", "failed", "retry"]),
            GamePlatform.store_product_id.isnot(None),
        ).all()

        print(f"Found {len(pending)} Steam listings to re-verify.\n")
        ok = failed = skipped = 0

        for i, listing in enumerate(pending, 1):
            game_title = listing.game.title
            app_id = listing.store_product_id
            print(f"[{i}/{len(pending)}] {game_title} (app {app_id})...", end=" ", flush=True)

            try:
                status = verify_listing(listing)
                if status == "verified":
                    price = listing.current_price
                    cur = listing.price_currency
                    print(f"OK verified - {cur} {price:.0f}")
                    ok += 1
                elif status == "retry":
                    print(f"~ retry (transient) - {listing.verify_error[:60]}")
                    skipped += 1
                else:
                    print(f"FAIL {status} - {listing.verify_error[:60]}")
                    failed += 1
            except RateLimited as e:
                print(f"\n  Rate-limited again ({e}). Pausing 3 minutes...")
                db.session.rollback()
                _steam_sanity_cache["checked_at"] = None
                time.sleep(180)
                inner_wait = 0
                while not _steam_is_healthy(country) and inner_wait < 600:
                    _steam_sanity_cache["checked_at"] = None
                    time.sleep(60)
                    inner_wait += 60
                if not _steam_is_healthy(country):
                    print("Steam still unavailable after 10 min. Stopping early.")
                    break
                print("Steam recovered. Resuming...")
                skipped += 1
                continue
            except Exception as e:
                print(f"  ERROR: {e}")
                db.session.rollback()
                skipped += 1

            time.sleep(DELAY_BETWEEN_GAMES)

        print(f"\nDone! verified={ok}, failed={failed}, skipped/retry={skipped}")


if __name__ == "__main__":
    main()
