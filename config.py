import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    # ------------------------------------------------------------------
    # DATABASE
    # By default the app runs on SQLite so it works instantly with zero
    # setup (great for demos / running the college project on a laptop).
    #
    # For the real MySQL deployment, set an environment variable:
    #   DATABASE_URL=mysql+pymysql://user:password@localhost:3306/game_deals_db
    # and the app will use MySQL automatically. The full MySQL schema is
    # provided in database/schema.sql if you want to create the DB by hand
    # instead of letting SQLAlchemy create the tables.
    # ------------------------------------------------------------------
    # Railway / Heroku supply DATABASE_URL as "postgres://..." but SQLAlchemy
    # requires "postgresql://...". Fix it transparently here.
    _db_url = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'game_deals.db')}")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Sessions
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Mail (deal-price-alert emails). Fill these in with real SMTP creds
    # to enable actual email sending; otherwise alerts are just logged.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_USERNAME", "noreply@gamevault.com")
    MAIL_SUPPRESS_SEND = os.environ.get("MAIL_SUPPRESS_SEND", "1") == "1"

    ITEMS_PER_PAGE = 12

    # ------------------------------------------------------------------
    # OFFICIAL PRICE VERIFICATION (see official_prices.py)
    # Every price shown on the site is read from the game's OWN store and
    # must be re-verified within PRICE_MAX_AGE_MINUTES, otherwise it is
    # hidden and the UI says "Unable to verify price".
    # ------------------------------------------------------------------
    # Region whose official storefront prices we show. One region at a time
    # keeps prices comparable/sortable and identical to what the store shows.
    STORE_COUNTRY = os.environ.get("STORE_COUNTRY", "IN").upper()      # ISO country code
    STORE_LOCALE = os.environ.get("STORE_LOCALE", "en-IN")             # used in Xbox/Epic URLs
    PRICE_MAX_AGE_MINUTES = int(os.environ.get("PRICE_MAX_AGE_MINUTES", 720))   # hide prices older than 12 h
    PRICE_REFRESH_MINUTES = int(os.environ.get("PRICE_REFRESH_MINUTES", 120))   # background re-verify cadence
    REFRESH_ON_VIEW_MINUTES = int(os.environ.get("REFRESH_ON_VIEW_MINUTES", 30))  # re-verify when a game page is opened
    PROBE_PURCHASE_URLS = os.environ.get("PROBE_PURCHASE_URLS", "1") == "1"  # HTTP-check every Buy link
    # Games with NO verified price are hidden from Browse by default
    # ("accuracy over showing a game"). Set to 1 to list them as "Unable to verify price".
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
