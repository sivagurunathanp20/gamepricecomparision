import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _get_int(key, default):
    val = os.environ.get(key)
    if not val:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-in-production"

    # ------------------------------------------------------------------
    # DATABASE
    # ------------------------------------------------------------------
    _db_url = os.environ.get("DATABASE_URL")
    if os.environ.get("VERCEL") and _db_url and "railway.internal" in _db_url:
        # railway.internal is only reachable within Railway's private network
        _db_url = None

    if not _db_url:
        if os.environ.get("VERCEL"):
            tmp_db = "/tmp/game_deals.db"
            possible_origs = [
                os.path.join(BASE_DIR, "game_deals.db"),
                os.path.join(BASE_DIR, "api", "game_deals.db"),
                os.path.join(os.getcwd(), "game_deals.db"),
                "/var/task/game_deals.db",
                "/var/task/api/game_deals.db",
            ]
            for orig in possible_origs:
                if os.path.exists(orig) and os.path.getsize(orig) > 100000:
                    import shutil
                    try:
                        shutil.copy2(orig, tmp_db)
                        break
                    except Exception:
                        pass
            _db_url = f"sqlite:///{tmp_db}"
        else:
            _db_url = f"sqlite:///{os.path.join(BASE_DIR, 'game_deals.db')}"
    elif _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif _db_url.startswith("postgresql://") and not _db_url.startswith("postgresql+"):
        _db_url = _db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Sessions
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Mail (deal-price-alert emails).
    MAIL_SERVER = os.environ.get("MAIL_SERVER") or "smtp.gmail.com"
    MAIL_PORT = _get_int("MAIL_PORT", 587)
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_USERNAME", "") or "noreply@gamevault.com"
    MAIL_SUPPRESS_SEND = os.environ.get("MAIL_SUPPRESS_SEND", "1") == "1"

    ITEMS_PER_PAGE = 12

    # ------------------------------------------------------------------
    # OFFICIAL PRICE VERIFICATION (see official_prices.py)
    # ------------------------------------------------------------------
    STORE_COUNTRY = (os.environ.get("STORE_COUNTRY") or "IN").upper()
    STORE_LOCALE = os.environ.get("STORE_LOCALE") or "en-IN"
    PRICE_MAX_AGE_MINUTES = _get_int("PRICE_MAX_AGE_MINUTES", 720)
    PRICE_REFRESH_MINUTES = _get_int("PRICE_REFRESH_MINUTES", 120)
    REFRESH_ON_VIEW_MINUTES = _get_int("REFRESH_ON_VIEW_MINUTES", 30)
    PROBE_PURCHASE_URLS = os.environ.get("PROBE_PURCHASE_URLS", "1") == "1"
    SHOW_UNVERIFIED_GAMES = os.environ.get("SHOW_UNVERIFIED_GAMES", "0") == "1"

    # ------------------------------------------------------------------
    # GOOGLE SIGN-IN (OAuth 2.0)
    # Get these from https://console.cloud.google.com/apis/credentials
    # (OAuth client ID, type "Web application"). Add this exact redirect
    # URI there: http://127.0.0.1:5000/auth/google/callback
    # (swap the domain for your real one in production).
    #
    # Leave these blank to run the app without Google Sign-In — the
    # "Sign in with Google" button simply won't be shown; everything
    # else works exactly as before.
    # ------------------------------------------------------------------
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    # Must match an Authorized redirect URI in Google Cloud Console exactly.
    # Default uses 127.0.0.1 (not localhost) — Google treats those as different.
    GOOGLE_REDIRECT_URI = os.environ.get(
        "GOOGLE_REDIRECT_URI", "http://127.0.0.1:5000/auth/google/callback"
    )

    # ------------------------------------------------------------------
    # VAULT AI ASSISTANT (Claude API)
    # The "Vault" chat widget uses Claude to answer in natural language,
    # grounded in real live site data (see routes/assistant.py). Get a
    # free key at https://console.anthropic.com/ and set it below.
    # Leave blank to fall back to the original keyword-matching bot —
    # the app runs fine either way, no setup required.
    # ------------------------------------------------------------------
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
