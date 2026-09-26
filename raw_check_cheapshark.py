"""
Hits CheapShark directly for a known Steam app id (Elden Ring = 1245620)
and prints the raw response, the same way raw_check.py does for Steam.
This is a completely separate domain/endpoint from store.steampowered.com,
so it tells us whether the interception problem is Steam-specific or
affects everything.
"""
import requests

HEADERS = {"User-Agent": "GameVault/1.0 (academic project; github.com/gamevault)"}

print("--- CheapShark: lookup by Steam App ID (Elden Ring, 1245620) ---")
resp = requests.get(
    "https://www.cheapshark.com/api/1.0/games",
    params={"steamAppID": 1245620},
    headers=HEADERS, timeout=10,
)
print("status code:", resp.status_code)
print("body (first 500 chars):", resp.text[:500])
print()

game_id = None
try:
    data = resp.json()
    if data:
        game_id = data[0].get("gameID") if isinstance(data, list) else data.get("gameID")
except Exception as exc:
    print("could not parse JSON:", exc)

if game_id:
    print(f"--- CheapShark: prices for gameID {game_id} ---")
    resp2 = requests.get(
        f"https://www.cheapshark.com/api/1.0/games?id={game_id}",
        headers=HEADERS, timeout=10,
    )
    print("status code:", resp2.status_code)
    print("body (first 500 chars):", resp2.text[:500])
else:
    print("No gameID resolved - check the first response above.")
