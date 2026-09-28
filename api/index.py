import sys
import os
import traceback

# Make sure the project root is on the path so all imports work.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from app import app as flask_app
    _init_error = None
except Exception:
    flask_app = None
    _init_error = traceback.format_exc()


class VercelWSGIHandler:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        if _init_error:
            start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8")])
            html = f"<div style='font-family:sans-serif;padding:30px;background:#1a1a1a;color:#fff;min-height:100vh;'><h2>Application Startup Error</h2><pre style='background:#0d1117;color:#ff7b72;padding:20px;border-radius:8px;white-space:pre-wrap;overflow-x:auto;font-size:14px;'>{_init_error}</pre></div>"
            return [html.encode("utf-8")]

        environ["SCRIPT_NAME"] = ""
        matched_path = (
            environ.get("HTTP_X_MATCHED_PATH")
            or environ.get("HTTP_X_FORWARDED_URI")
            or environ.get("REQUEST_URI")
        )
        if matched_path:
            path = matched_path.split("?")[0]
            if path and path not in ("/api/index", "/api/index.py"):
                environ["PATH_INFO"] = path
            else:
                environ["PATH_INFO"] = "/"
        elif environ.get("PATH_INFO") in ("/api/index", "/api/index.py", "/api", ""):
            environ["PATH_INFO"] = "/"

        try:
            return self.wsgi_app(environ, start_response)
        except Exception:
            tb = traceback.format_exc()
            start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8")])
            html = f"<div style='font-family:sans-serif;padding:30px;background:#1a1a1a;color:#fff;min-height:100vh;'><h2>Serverless Runtime Error</h2><pre style='background:#0d1117;color:#ff7b72;padding:20px;border-radius:8px;white-space:pre-wrap;overflow-x:auto;font-size:14px;'>{tb}</pre></div>"
            return [html.encode("utf-8")]


app = VercelWSGIHandler(flask_app)

