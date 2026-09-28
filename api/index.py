# Vercel serverless entry point.
# Vercel looks for an ASGI/WSGI callable named `app` in this file.
# We simply import the Flask application created in the project root.
import sys
import os

# Make sure the project root is on the path so all imports work.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app  # noqa: E402  (Flask app instance)
