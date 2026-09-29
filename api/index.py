import sys
import os
import urllib.parse

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from app import app as flask_app  # noqa: E402


class VercelPathMiddleware:
    """Extracts the real requested path on Vercel from x-matched-path,
    x-forwarded-uri, request_uri, or x-now-route-matches so that Flask routes
    every game page, deals page, compare page, etc. accurately instead of falling back to /."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = ""
        path = None
        m = environ.get("HTTP_X_MATCHED_PATH")
        if m and m not in ("/api/index", "/api", "/api/index.py", "/api/"):
            path = m

        if not path:
            f = environ.get("HTTP_X_FORWARDED_URI")
            if f and f not in ("/api/index", "/api", "/api/index.py", "/api/"):
                path = f

        if not path:
            r = environ.get("REQUEST_URI") or environ.get("RAW_URI")
            if r and r not in ("/api/index", "/api", "/api/index.py", "/api/"):
                path = r

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
            if "?" in path:
                parts = path.split("?", 1)
                path = parts[0]
                if len(parts) > 1 and not environ.get("QUERY_STRING"):
                    environ["QUERY_STRING"] = parts[1]
            if not path.startswith("/"):
                path = "/" + path
            environ["PATH_INFO"] = path
        elif curr in ("/api/index", "/api", "/api/index.py", "/api/", ""):
            environ["PATH_INFO"] = "/"

        return self.wsgi_app(environ, start_response)


app = VercelPathMiddleware(flask_app)
