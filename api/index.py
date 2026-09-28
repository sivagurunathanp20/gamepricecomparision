# Vercel serverless entry point.
# Vercel looks for an ASGI/WSGI callable named `app` in this file.
# We simply import the Flask application created in the project root.
import sys
import os

# Make sure the project root is on the path so all imports work.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app as flask_app  # noqa: E402


class VercelWSGIHandler:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # Vercel rewrites sometimes pass /api/index as PATH_INFO.
        # Check if original path is stored in x-matched-path or x-forwarded-uri:
        matched_path = environ.get("HTTP_X_MATCHED_PATH") or environ.get("HTTP_X_FORWARDED_URI")
        if matched_path:
            path = matched_path.split("?")[0]
            if path:
                environ["PATH_INFO"] = path
        elif environ.get("PATH_INFO") in ("/api/index", "/api/index.py", "/api"):
            environ["PATH_INFO"] = "/"

        return self.wsgi_app(environ, start_response)


app = VercelWSGIHandler(flask_app)
