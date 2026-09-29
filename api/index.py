import sys
import os
import urllib.parse

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from app import app as flask_app  # noqa: E402


class VercelPathMiddleware:
    """Extracts the real requested path on Vercel.

    Strategy (in order of priority):
    1. x-matched-path header – Vercel sets this to the original user path.
    2. x-forwarded-uri – alternate Vercel header.
    3. x-now-route-matches – URL-encoded capture groups from the rewrite rule.
    4. REQUEST_URI / RAW_URI – raw URI from the server.
    5. PATH_INFO passthrough – if none of the above, clear any /api/index prefix
       and reset to "/" so Flask sees the root route, not a dead-end 404.

    Additionally we always clear SCRIPT_NAME because Vercel sets it to
    "/api/index.py" (the function file path), which makes Flask strip that
    prefix from every route and produce 404s for every non-root URL.
    """

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # CRITICAL: Vercel sets SCRIPT_NAME = "/api/index.py".
        # Flask uses SCRIPT_NAME as a prefix when matching routes, so every
        # route that doesn't start with "/api/index.py" returns 404.
        # Clearing it to "" makes Flask match from the root "/" again.
        environ["SCRIPT_NAME"] = ""

        path = None

        # 1. x-matched-path (most reliable on Vercel)
        m = environ.get("HTTP_X_MATCHED_PATH")
        if m and m not in ("/api/index", "/api", "/api/index.py", "/api/"):
            path = m

        # 2. x-forwarded-uri
        if not path:
            f = environ.get("HTTP_X_FORWARDED_URI")
            if f and f not in ("/api/index", "/api", "/api/index.py", "/api/"):
                path = f

        # 3. REQUEST_URI / RAW_URI
        if not path:
            r = environ.get("REQUEST_URI") or environ.get("RAW_URI")
            if r and r not in ("/api/index", "/api", "/api/index.py", "/api/"):
                path = r

        # 4. x-now-route-matches (URL-encoded capture groups)
        if not path:
            rm = environ.get("HTTP_X_NOW_ROUTE_MATCHES")
            if rm:
                try:
                    params = urllib.parse.parse_qs(rm)
                    for k in sorted(params.keys()):
                        val = params[k][0]
                        if val:
                            val = urllib.parse.unquote(val)
                            if not val.startswith("/"):
                                val = "/" + val
                            if val not in ("/api/index", "/api", "/api/index.py", "/api/"):
                                path = val
                                break
                except Exception:
                    pass

        curr = environ.get("PATH_INFO", "")
        if path:
            # Strip query string from path if accidentally included
            if "?" in path:
                parts = path.split("?", 1)
                path = parts[0]
                if len(parts) > 1 and not environ.get("QUERY_STRING"):
                    environ["QUERY_STRING"] = parts[1]
            if not path.startswith("/"):
                path = "/" + path
            environ["PATH_INFO"] = path
        elif curr in ("/api/index", "/api", "/api/index.py", "/api/", ""):
            # 5. Fallback: if Vercel gave us its internal path and nothing else,
            #    assume the user requested root "/"
            environ["PATH_INFO"] = "/"

        return self.wsgi_app(environ, start_response)


app = VercelPathMiddleware(flask_app)
