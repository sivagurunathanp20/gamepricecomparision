import sys
import os

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from app import app as flask_app  # noqa: E402


class VercelPathMiddleware:
    """Extracts the real requested path on Vercel from x-matched-path,
    x-forwarded-uri, or request_uri so that Flask routes every game page,
    deals page, compare page, etc. accurately instead of falling back to /."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        matched = (
            environ.get("HTTP_X_MATCHED_PATH")
            or environ.get("HTTP_X_FORWARDED_URI")
            or environ.get("REQUEST_URI")
            or environ.get("RAW_URI")
        )
        if matched:
            if "?" in matched:
                matched = matched.split("?", 1)[0]
            if matched and matched not in ("/api/index", "/api", "/api/index.py"):
                environ["PATH_INFO"] = matched

        return self.wsgi_app(environ, start_response)


app = VercelPathMiddleware(flask_app)
