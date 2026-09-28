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
        path = None
        matched = environ.get("HTTP_X_MATCHED_PATH")
        if matched and matched not in ("/api/index", "/api", "/api/index.py"):
            path = matched
        if not path:
            fwd = environ.get("HTTP_X_FORWARDED_URI")
            if fwd and fwd not in ("/api/index", "/api", "/api/index.py"):
                path = fwd
        if not path:
            req_uri = environ.get("REQUEST_URI") or environ.get("RAW_URI")
            if req_uri and req_uri not in ("/api/index", "/api", "/api/index.py"):
                path = req_uri
        if not path:
            route_matches = environ.get("HTTP_X_NOW_ROUTE_MATCHES")
            if route_matches:
                try:
                    params = urllib.parse.parse_qs(route_matches)
                    for k in sorted(params.keys()):
                        val = params[k][0]
                        if val:
                            val = urllib.parse.unquote(val)
                            if not val.startswith("/"):
                                val = "/" + val
                            if val not in ("/api/index", "/api", "/api/index.py"):
                                path = val
                                break
                except Exception:
                    pass

        if path:
            if "?" in path:
                parts = path.split("?", 1)
                path = parts[0]
                if len(parts) > 1 and not environ.get("QUERY_STRING"):
                    environ["QUERY_STRING"] = parts[1]
            if not path.startswith("/"):
                path = "/" + path
            environ["PATH_INFO"] = path
        else:
            curr_path = environ.get("PATH_INFO", "")
            if curr_path in ("/api/index", "/api", "/api/index.py", ""):
                environ["PATH_INFO"] = "/"

        return self.wsgi_app(environ, start_response)


app = VercelPathMiddleware(flask_app)
