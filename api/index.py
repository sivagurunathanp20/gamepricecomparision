import sys
import os

# Make the project root importable
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from app import app as flask_app  # noqa: E402


def application(environ, start_response):
    """
    WSGI entry point for Vercel's @vercel/python runtime.

    When using `builds` + `routes` (not `rewrites`), Vercel sets PATH_INFO
    to the actual requested path correctly.  We only need to clear
    SCRIPT_NAME, which Vercel sometimes sets to '/api/index' — that would
    cause Flask to strip that prefix from every URL and return 404s.
    """
    environ["SCRIPT_NAME"] = ""

    # Vercel may set PATH_INFO to '' (empty) for the root path — normalise.
    if not environ.get("PATH_INFO"):
        environ["PATH_INFO"] = "/"

    return flask_app(environ, start_response)


# Vercel looks for a module-level `app` callable by convention.
app = application
