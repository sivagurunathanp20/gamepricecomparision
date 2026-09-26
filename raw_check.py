"""
Hits Steam's appdetails endpoint directly for a couple of known-failing
app ids (CS2 = 730, Dota 2 = 570) and a known-working one, and prints
the raw response so we can see exactly what Steam is sending back --
not just the interpreted error message.
"""
import requests

UA = {"User-Agent": "GameVault/2.0 (student project; official price verifier)"}

for app_id in [730, 570, 292030]:  # CS2, Dota 2, The Witcher 3
    resp = requests.get(
        "https://store.steampowered.com/api/appdetails",
        params={"appids": app_id, "cc": "in", "l": "english"},
        headers=UA, timeout=10,
    )
    print(f"--- app {app_id} ---")
    print("status code:", resp.status_code)
    print("response headers content-type:", resp.headers.get("content-type"))
    print("body (first 500 chars):", resp.text[:500])
    print()
