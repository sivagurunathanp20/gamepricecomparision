"""
Two checks:
1. Shows exactly which 'requests' module Python is actually loading
   (its file path and version) - reveals a shadowed/tampered install.
2. Repeats the Steam appdetails call using ONLY Python's built-in
   urllib (nothing from pip, nothing from this project) to see if the
   problem still happens with zero third-party code involved at all.
"""
import json
import urllib.request

import requests
print("=== requests module info ===")
print("requests.__file__   :", requests.__file__)
print("requests.__version__:", getattr(requests, "__version__", "unknown"))
print()

print("=== raw urllib check (no 'requests' library at all) ===")
url = "https://store.steampowered.com/api/appdetails?appids=730&cc=in&l=english"
req = urllib.request.Request(url, headers={"User-Agent": "GameVault/2.0 (student project)"})
with urllib.request.urlopen(req, timeout=10) as resp:
    body = resp.read().decode("utf-8", errors="replace")
    print("status:", resp.status)
    print("body (first 300 chars):", body[:300])
    try:
        parsed = json.loads(body)
        print("top-level key(s) in response:", list(parsed.keys()))
    except Exception as exc:
        print("could not parse JSON:", exc)
