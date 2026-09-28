import sys
import os
import json

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from app import app as flask_app  # noqa: E402


def app(environ, start_response):
    path = environ.get("PATH_INFO", "")

    # Quick raw debug
    if "debug-raw" in environ.get("REQUEST_URI", "") or "debug-raw" in path or "debug-raw" in environ.get("HTTP_X_MATCHED_PATH", ""):
        debug_data = {
            k: str(v) for k, v in environ.items() if isinstance(v, (str, int, float, bool))
        }
        resp_body = json.dumps(debug_data, indent=2).encode("utf-8")
        start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(resp_body)))])
        return [resp_body]

    # Vercel WSGI routing fix
    # In Vercel, the original path is often in x-now-route-matches, x-matched-path, request_uri, or vercel-now-route-matches
    candidates = [
        environ.get("HTTP_X_NOW_ROUTE_MATCHES"),
        environ.get("HTTP_X_MATCHED_PATH"),
        environ.get("HTTP_X_FORWARDED_URI"),
        environ.get("HTTP_X_VERCEL_PATH"),
        environ.get("REQUEST_URI"),
        environ.get("RAW_URI"),
    ]

    for c in candidates:
        if c:
            # Check if JSON (x-now-route-matches is sometimes a query or json string)
            if c.startswith("1="):
                # e.g. 1=%2Fgame%2Fterraria
                import urllib.parse
                parsed = urllib.parse.parse_qs(c)
                if "1" in parsed and parsed["1"]:
                    c = parsed["1"][0]
            if "?" in c:
                c = c.split("?", 1)[0]
            if c and c not in ("/api/index", "/api", "/api/index.py"):
                environ["PATH_INFO"] = c
                break

    return flask_app(environ, start_response)
