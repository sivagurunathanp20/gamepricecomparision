"""
Re-verifies all prices with a much longer delay between games, to stay
under Steam's soft rate limit (it returns success:false instead of a
real 429 when you go too fast, which looks like "not sold here").

official_prices.py now cross-checks any "not found" against a sanity-probe
app (Counter-Strike 2, which always has a store page everywhere). If the
probe also fails, it correctly treats that as Steam rate-limiting rather
than dozens of real games vanishing, stops immediately, and leaves
existing prices untouched. This script cools down and resumes
automatically when that happens, instead of requiring a manual re-run.

Run this instead of `flask --app app verify-prices` if that command
produced a wall of "no store page for app X in region IN" failures for
obviously real, popular games.
"""
import time

from app import app
from official_prices import verify_all, expire_stale_prices

MAX_ATTEMPTS = 6
COOLDOWN_SECONDS = 90  # grows with each retry

with app.app_context():
    totals = {"verified": 0, "failed": 0, "unverified": 0, "retry": 0}
    attempt = 1
    while attempt <= MAX_ATTEMPTS:
        print(f"--- pass {attempt} ---")
        counts = verify_all(sleep=2.5, progress=lambda g: print(f"  checked {g.title}"))
        for key in totals:
            totals[key] += counts.get(key, 0)

        if not counts.get("rate_limited"):
            print("Finished: Steam answered for every remaining game.")
            break

        cooldown = COOLDOWN_SECONDS * attempt
        print(f"Steam looks soft rate-limited (sanity probe also failed). "
              f"Cooling down {cooldown}s before resuming...")
        time.sleep(cooldown)
        attempt += 1
    else:
        print("Still rate-limited after all retries - stopping for now. "
              "Existing prices were left untouched; just run this script "
              "again later.")

    expire_stale_prices()
    print(f"Done: {totals}")
