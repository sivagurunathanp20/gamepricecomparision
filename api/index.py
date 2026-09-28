import sys
import os

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from app import app as flask_app  # noqa: E402


class VercelPathFixMiddleware:
    """Restores the original request URL from Vercel headers so routing matches
    the actual page requested (/game/..., /deals, /compare, etc.) rather than
    the internal serverless rewrite destination (/api/index)."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path in ("/api/index", "/api", "/api/index.py", ""):
            # Check headers populated by Vercel's edge router
            real_path = (
                environ.get("HTTP_X_MATCHED_PATH")
                or environ.get("HTTP_X_FORWARDED_URI")
                or environ.get("HTTP_X_VERCEL_PATH")
                or environ.get("RAW_URI")
                or environ.get("REQUEST_URI")
                or "/"
            )
            # Remove query string if present
            if "?" in real_path:
                real_path = real_path.split("?", 1)[0]
            if real_path and real_path not in ("/api/index", "/api", "/api/index.py"):
                environ["PATH_INFO"] = real_path
        return self.wsgi_app(environ, start_response)


app = VercelPathFixMiddleware(flask_app)
