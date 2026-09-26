"""
fix_store_urls.py
=================================================================
One-shot migration script that finds all GamePlatform rows with a
bad store_url (NULL / "#" / bare store homepage) and rewrites them
using the build_store_url() priority waterfall from store_apis.py.

Safe to run multiple times (idempotent): rows that already have a
good URL are left untouched.

Usage:
    python fix_store_urls.py          # dry-run (prints what WOULD change)
    python fix_store_urls.py --apply  # actually writes changes to the DB
"""
import sys

from app import create_app
from extensions import db
from models import GamePlatform, Game, Platform
from store_apis import build_store_url, is_bad_store_url

DRY_RUN = "--apply" not in sys.argv


def fix_store_urls():
    app = create_app()
    with app.app_context():
        rows = (
            db.session.query(GamePlatform, Game, Platform)
            .join(Game, Game.id == GamePlatform.game_id)
            .join(Platform, Platform.id == GamePlatform.platform_id)
            .all()
        )

        total = len(rows)
        fixed = 0
        skipped = 0
        by_store: dict[str, int] = {}

        for listing, game, platform in rows:
            if not is_bad_store_url(listing.store_url):
                skipped += 1
                continue

            new_url = build_store_url(
                store_name=platform.name,
                game_title=game.title,
                steam_app_id=game.steam_app_id if platform.name == "Steam" else None,
                existing_url=None,  # Force rebuild — existing is already bad
            )

            if not new_url or new_url == listing.store_url:
                skipped += 1
                continue

            old = listing.store_url or "<null>"
            print(
                f"  [{platform.name:20s}] {game.title[:40]:40s} "
                f"| {old[:40]:40s} → {new_url}"
            )

            if not DRY_RUN:
                listing.store_url = new_url

            fixed += 1
            by_store[platform.name] = by_store.get(platform.name, 0) + 1

        if not DRY_RUN and fixed:
            db.session.commit()

        # --- Summary ---
        print()
        print("=" * 70)
        if DRY_RUN:
            print(f"DRY RUN — would fix {fixed} / {total} rows (pass --apply to write).")
        else:
            print(f"APPLIED — fixed {fixed} / {total} rows ({skipped} already good).")

        if by_store:
            print("\nBreakdown by store:")
            for store, count in sorted(by_store.items(), key=lambda x: -x[1]):
                print(f"  {store:<25s} {count:>4d} rows")
        print("=" * 70)


if __name__ == "__main__":
    fix_store_urls()
