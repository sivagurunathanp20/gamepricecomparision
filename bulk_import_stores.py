"""
Bulk-registers official store products (Xbox / PlayStation / Nintendo /
Epic) from a CSV file, then verifies each one, instead of running
`add-official-product` by hand for every single game/store combo.

USAGE:
  1. Put your data into stores.csv (same folder as this script),
     with exactly these columns:

         game,store,url

     game  -> the game's title as it appears in your database
              (or its slug -- either works)
     store -> one of exactly:
                Xbox Store
                PlayStation Store
                Nintendo eShop
                Epic Games Store
              (GOG and Ubisoft Connect are skipped -- there's no price
              API support for them in official_prices.py yet)
     url   -> the game's real purchase page on that store

  2. Copy stores.csv and this script into your project folder
     (next to app.py), then run:

         python bulk_import_stores.py

  Xbox: the product id is the 12-character code at the end of the URL
  -- extracted automatically, no extra work needed.

  PlayStation / Nintendo: no price API exists for these stores, so the
  URL itself is all that's needed -- prices stay "Unable to verify",
  but the Buy link gets checked and shown.

  Epic: needs an internal "catalog namespace" that isn't visible in
  the URL. This script tries to pull it automatically from the page's
  own embedded data. If that fails for a given game, it's skipped and
  printed at the end so you can add it by hand later.
"""
import csv
import re
import time
import sys

from app import app
from extensions import db
from models import Game
from official_prices import (
    register_official_product, verify_listing, validate_official_url,
    XBOX, EPIC, PLAYSTATION, NINTENDO,
)

CSV_PATH = "stores.csv"
UNSUPPORTED_STORES = {"GOG", "Ubisoft Connect"}

XBOX_ID_RE = re.compile(r"/([0-9A-Za-z]{12})/?$")
EPIC_NAMESPACE_RE = re.compile(r'"namespace"\s*:\s*"([a-zA-Z0-9]+)"')


def find_game(key):
    g = Game.query.filter(db.func.lower(Game.title) == key.lower()).first()
    if g:
        return g
    return Game.query.filter_by(slug=key).first()


def extract_xbox_id(url):
    m = XBOX_ID_RE.search(url.strip())
    return m.group(1) if m else None


EPIC_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://store.epicgames.com/",
}


def extract_epic_namespace(url):
    """Best-effort: fetch the product page and pull the namespace out of
    its embedded page data. Epic doesn't expose this in the URL itself.
    Epic's storefront blocks plain scripted requests fairly aggressively
    (bot protection), so this can legitimately fail even with browser-like
    headers -- that's a known limitation, not a bug to chase forever."""
    import requests
    try:
        resp = requests.get(url, headers=EPIC_BROWSER_HEADERS, timeout=10)
    except requests.RequestException as exc:
        return None, f"could not fetch page: {exc}"
    if resp.status_code == 403:
        return None, "blocked by Epic's bot protection (HTTP 403) -- add this one manually, see note below"
    if resp.status_code >= 400:
        return None, f"page returned HTTP {resp.status_code}"
    m = EPIC_NAMESPACE_RE.search(resp.text)
    if not m:
        return None, "namespace not found in page (may need to be added manually)"
    return m.group(1), None


def main():
    try:
        rows = list(csv.DictReader(open(CSV_PATH, newline="", encoding="utf-8")))
    except FileNotFoundError:
        print(f"!! {CSV_PATH} not found -- create it next to this script first.")
        sys.exit(1)

    skipped, failed, ok = [], [], []

    with app.app_context():
        for i, row in enumerate(rows, 1):
            game_key = (row.get("game") or "").strip()
            store = (row.get("store") or "").strip()
            url = (row.get("url") or "").strip()

            if not game_key or not store or not url:
                skipped.append((row, "missing game/store/url"))
                continue

            game = find_game(game_key)
            if not game:
                skipped.append((row, f"no game found matching '{game_key}'"))
                continue

            if store in UNSUPPORTED_STORES:
                skipped.append((row, f"{store} has no price API support yet"))
                continue

            try:
                if store == XBOX:
                    pid = extract_xbox_id(url)
                    if not pid:
                        skipped.append((row, "couldn't extract a 12-char Xbox product id from URL"))
                        continue
                    listing = register_official_product(game, store, product_id=pid)

                elif store == EPIC:
                    if not validate_official_url(EPIC, url):
                        skipped.append((row, "URL doesn't look like an exact Epic product page"))
                        continue
                    namespace, err = extract_epic_namespace(url)
                    if not namespace:
                        skipped.append((row, f"Epic: {err}"))
                        continue
                    listing = register_official_product(game, store, product_id=namespace)

                elif store in (PLAYSTATION, NINTENDO):
                    listing = register_official_product(game, store, url=url)

                else:
                    skipped.append((row, f"unrecognized store name '{store}'"))
                    continue

                status = verify_listing(listing)
                print(f"[{i}/{len(rows)}] {game.title} / {store}: {status} {listing.verify_error or ''}")
                if status == "verified":
                    ok.append(row)
                elif store in (PLAYSTATION, NINTENDO) and status == "unverified":
                    # Expected outcome for these stores -- there's no public
                    # price API, so the Buy link is registered/checked but
                    # the price is honestly "unable to verify". Not a failure.
                    ok.append(row)
                else:
                    failed.append((row, listing.verify_error))

            except ValueError as exc:
                skipped.append((row, str(exc)))
            except Exception as exc:  # noqa
                skipped.append((row, f"unexpected error: {exc}"))

            time.sleep(1.0)  # be polite to each store's servers

        db.session.commit()

    print(f"\nDone. verified={len(ok)} failed={len(failed)} skipped={len(skipped)}")
    if skipped:
        print("\n--- skipped ---")
        for row, reason in skipped:
            print(f"  {row.get('game')} / {row.get('store')}: {reason}")
    if failed:
        print("\n--- failed (registered but not verified) ---")
        for row, reason in failed:
            print(f"  {row.get('game')} / {row.get('store')}: {reason}")


if __name__ == "__main__":
    main()
