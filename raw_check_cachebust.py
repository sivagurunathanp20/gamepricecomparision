"""
Same as raw_check.py, but adds a random, never-repeated query parameter to
each request. If Steam's CDN edge is serving a stale/wrongly-cached response
(rather than something intercepting locally), a cache-busted request should
force a fresh hit to Steam's real backend and return the CORRECT app id.
"""
import random
import requests

UA = {"User-Agent": "GameVault/2.0 (student project; official price verifier)"}

for app_id in [730, 570, 292030]:  # CS2, Dota 2, The Witcher 3
    resp = requests.get(
        "https://store.steampowered.com/api/appdetails",
        params={
            "appids": app_id,
            "cc": "in",
            "l": "english",
            "_cb": random.randint(1, 999999999),  # cache-buster, ignored by Steam's own logic
        },
        headers=UA, timeout=10,
    )
    print(f"--- app {app_id} ---")
    print("status code:", resp.status_code)
    print("body (first 300 chars):", resp.text[:300])
    print()
