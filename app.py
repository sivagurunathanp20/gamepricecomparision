import click
from flask import Flask, render_template
from sqlalchemy import inspect, text

from config import Config
from extensions import db, login_manager, bcrypt, mail, oauth
from models import User, Game
from scheduler import init_scheduler


def _ensure_google_auth_columns():
    """Add google_id / auth_provider to existing SQLite DBs created before OAuth."""
    try:
        inspector = inspect(db.engine)
        if "users" not in inspector.get_table_names():
            return
        existing = {col["name"] for col in inspector.get_columns("users")}
        statements = []
        if "google_id" not in existing:
            statements.append("ALTER TABLE users ADD COLUMN google_id VARCHAR(64)")
        if "auth_provider" not in existing:
            statements.append("ALTER TABLE users ADD COLUMN auth_provider VARCHAR(20) DEFAULT 'local'")
        if statements:
            with db.engine.begin() as conn:
                for sql in statements:
                    conn.execute(text(sql))
    except Exception:
        pass


def _ensure_price_verification_columns():
    """Adds the official-price columns to existing DBs, then neutralises every
    legacy price. Old rows were seeded/manual/aggregator numbers with no
    official backing, so they are cleared and only reappear once verified."""
    try:
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        if "game_platforms" not in tables:
            return
        gp = {c["name"] for c in inspector.get_columns("game_platforms")}
        is_postgres = db.engine.dialect.name == "postgresql"
        dt_type = "TIMESTAMP" if is_postgres else "DATETIME"
        bool_default = "FALSE" if is_postgres else "0"
        stmts = []
        if "store_product_id" not in gp:
            stmts.append("ALTER TABLE game_platforms ADD COLUMN store_product_id VARCHAR(128)")
        if "last_verified_at" not in gp:
            stmts.append(f"ALTER TABLE game_platforms ADD COLUMN last_verified_at {dt_type}")
        if "verify_status" not in gp:
            stmts.append("ALTER TABLE game_platforms ADD COLUMN verify_status VARCHAR(12)")
        if "verify_error" not in gp:
            stmts.append("ALTER TABLE game_platforms ADD COLUMN verify_error VARCHAR(255) DEFAULT ''")
        if "price_history" in tables and "verified" not in {c["name"] for c in inspector.get_columns("price_history")}:
            stmts.append(f"ALTER TABLE price_history ADD COLUMN verified BOOLEAN DEFAULT {bool_default}")
        with db.engine.begin() as conn:
            for sql in stmts:
                conn.execute(text(sql))
            conn.execute(text(
                "UPDATE game_platforms SET verify_status='unverified', current_price=NULL, "
                "original_price=NULL, discount_percent=0 WHERE verify_status IS NULL"))
            conn.execute(text(f"UPDATE price_history SET verified={bool_default} WHERE verified IS NULL"))
    except Exception:
        pass


def create_app(config_class=Config):
    import os
    app = Flask(
        __name__,
        template_folder=os.path.join(Config.BASE_DIR, "templates"),
        static_folder=os.path.join(Config.BASE_DIR, "static"),
    )
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    oauth.init_app(app)

    # Google Sign-In (OAuth 2.0) is optional: if credentials are missing,
    # the provider is not registered and the button explains how to set it up.
    if app.config.get("GOOGLE_CLIENT_ID") and app.config.get("GOOGLE_CLIENT_SECRET"):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    with app.app_context():
        try:
            db.create_all()          # auto-create tables on remote DB / sqlite
            _ensure_google_auth_columns()
            _ensure_price_verification_columns()
            if Game.query.first() is None:
                from seed import populate_seed_data
                populate_seed_data(drop=False)
        except Exception as e:
            app.logger.warning("Startup DB init check: %s", e)

    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.deals import deals_bp
    from routes.wishlist import wishlist_bp
    from routes.admin import admin_bp
    from routes.api import api_bp
    from routes.assistant import assistant_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(deals_bp)
    app.register_blueprint(wishlist_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(assistant_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    @app.errorhandler(Exception)
    def handle_exception(e):
        import traceback
        tb = traceback.format_exc()
        app.logger.error("Application error: %s\n%s", e, tb)
        if os.environ.get("VERCEL") or app.debug:
            return f"<div style='font-family:sans-serif;padding:30px;background:#1a1a1a;color:#fff;min-height:100vh;'><h2>Application Error (500)</h2><p>{e}</p><pre style='background:#0d1117;color:#ff7b72;padding:20px;border-radius:8px;white-space:pre-wrap;overflow-x:auto;font-size:14px;'>{tb}</pre></div>", 500
        return f"<h2>500 Internal Server Error</h2><p>{e}</p>", 500

    @app.context_processor
    def inject_globals():
        from datetime import datetime
        from flask import current_app, session
        from currency import SUPPORTED_CURRENCIES
        return {
            "now": datetime.utcnow(),
            "current_currency": session.get("currency", "INR"),
            "supported_currencies": SUPPORTED_CURRENCIES,
            "google_oauth_enabled": bool(
                current_app.config.get("GOOGLE_CLIENT_ID")
                and current_app.config.get("GOOGLE_CLIENT_SECRET")
            ),
        }

    @app.template_filter("currency")
    def currency_filter(value, from_currency="USD"):
        from flask import session
        from currency import format_price
        code = session.get("currency", "INR")
        return format_price(value, code, from_currency)

    @app.template_filter("official_price")
    def official_price_filter(value, currency_code="USD"):
        """Formats a price exactly as the store shows it (its own currency,
        never converted)."""
        from currency import SUPPORTED_CURRENCIES
        if value is None:
            return "Unable to verify price"
        symbol = SUPPORTED_CURRENCIES.get(currency_code, {}).get("symbol", currency_code + " ")
        if value == 0:
            return "Free"
        whole = currency_code in ("INR", "JPY") and float(value).is_integer()
        return f"{symbol}{value:,.0f}" if whole else f"{symbol}{value:,.2f}"

    @app.template_filter("time_ago")
    def time_ago_filter(dt):
        from datetime import datetime
        if not dt:
            return "never"
        secs = int((datetime.utcnow() - dt).total_seconds())
        if secs < 90:
            return "just now"
        if secs < 3600:
            return f"{secs // 60} min ago"
        if secs < 86400:
            return f"{secs // 3600} h ago"
        return f"{secs // 86400} d ago"

    _expiry = {"last": 0.0}

    @app.before_request
    def _hide_stale_prices():
        """At most once a minute, hide prices that were not re-verified in time."""
        import time
        from flask import request
        if request.endpoint == "static" or time.time() - _expiry["last"] < 60:
            return
        _expiry["last"] = time.time()
        try:
            from official_prices import expire_stale_prices
            expire_stale_prices()
        except Exception:
            db.session.rollback()

    @app.route("/set-currency/<code>", methods=["POST"])
    def set_currency(code):
        from flask import session, redirect, request
        from currency import SUPPORTED_CURRENCIES
        if code in SUPPORTED_CURRENCIES:
            session["currency"] = code
        return redirect(request.referrer or "/")

    @app.cli.command("init-db")
    def init_db():
        """Create all tables: flask --app app init-db"""
        db.create_all()
        print("Database tables created.")

    @app.cli.command("seed-db")
    def seed_db():
        """Populate the database with demo data: flask --app app seed-db"""
        print("The demo seed contained invented prices, so it is disabled. Seeding real Steam data instead.")
        from seed_real_steam import run_seed as run_real_seed
        run_real_seed()

    @app.cli.command("seed-steam")
    def seed_steam():
        """Populate the database with REAL live Steam data (needs internet):
        flask --app app seed-steam"""
        from seed_real_steam import run_seed as run_real_seed
        run_real_seed()

    @app.cli.command("check-price-alerts")
    def check_price_alerts():
        """Scan wishlists and email users whose target price has been hit."""
        from alerts import check_and_send_alerts
        count = check_and_send_alerts()
        print(f"Sent {count} price alert(s).")

    @app.cli.command("verify-prices")
    def verify_prices():
        """Verify every price + Buy link against the official stores:
        flask --app app verify-prices"""
        from official_prices import verify_all, expire_stale_prices
        counts = verify_all(progress=lambda g: print(f"  checked {g.title}"))
        expire_stale_prices()
        print(f"Done: {counts}")
        if counts["rate_limited"]:
            print("A store rate-limited us - run the command again in a few minutes.")

    @app.cli.command("sync-all-prices")
    def sync_all_prices():
        """Alias of verify-prices (prices now come only from official stores)."""
        verify_prices.callback()

    @app.cli.command("add-official-product")
    @click.option("--game", "slug", required=True, help="game slug")
    @click.option("--store", required=True, help='"Xbox Store", "Epic Games Store", "GOG", "PlayStation Store", "Nintendo eShop", "Ubisoft Connect"')
    @click.option("--product-id", default=None, help="Xbox: 12-char product id(s), comma separated. Epic: catalog namespace. GOG: numeric product id.")
    @click.option("--url", default=None, help="exact official product URL (PlayStation / Nintendo)")
    @click.option("--edition", default=None, help="edition label for link-only stores")
    def add_official_product(slug, store, product_id, url, edition):
        """Attach an official store product to a game, then verify it."""
        from models import Game
        from official_prices import register_official_product, verify_listing
        game = Game.query.filter_by(slug=slug).first()
        if not game:
            raise click.ClickException(f"no game with slug {slug}")
        try:
            listing = register_official_product(game, store, product_id, url, edition)
        except ValueError as exc:
            raise click.ClickException(str(exc))
        print(f"{store}: {verify_listing(listing)} {listing.verify_error or ''}")

    @app.cli.command("purge-legacy-data")
    @click.option("--yes", is_flag=True, help="actually delete")
    def purge_legacy_data(yes):
        """Delete seeded/manual store rows and unverified price history that
        have no official backing: flask --app app purge-legacy-data --yes"""
        from models import GamePlatform, PriceHistory
        rows = GamePlatform.query.filter(GamePlatform.store_product_id.is_(None), ~GamePlatform.editions.any()).all()
        hist = PriceHistory.query.filter(PriceHistory.verified.is_(False)).count()
        print(f"{len(rows)} unbacked store listings, {hist} unverified price-history rows")
        if not yes:
            print("Dry run. Re-run with --yes to delete.")
            return
        for r in rows:
            db.session.delete(r)
        PriceHistory.query.filter(PriceHistory.verified.is_(False)).delete()
        db.session.commit()
        print("Deleted.")

    @app.cli.command("discover-deals")
    def discover_deals():
        """Finds newly-free / newly-on-sale games (CheapShark + Epic's
        weekly freebies) right now, instead of waiting for the 3-hour
        scheduled job: flask --app app discover-deals"""
        from deal_discovery import discover_new_deals
        summary = discover_new_deals()
        print(
            f"CheapShark: {summary['cheapshark_added']} added, "
            f"{summary['cheapshark_extended']} extended. "
            f"Epic: {summary['epic_added']} added, "
            f"{summary['epic_extended']} extended."
        )

    @app.cli.command("steam-seed-queue")
    def steam_seed_queue():
        """Pulls Steam's full app list (~260k entries) into the import
        queue. Safe to re-run — only adds apps not already queued/imported.
        flask --app app steam-seed-queue"""
        from steam_importer import seed_import_queue
        count = seed_import_queue()
        print(f"Queued {count} new Steam app(s) for import.")

    @app.cli.command("steam-import-batch")
    def steam_import_batch():
        """Imports ONE batch (default 20 apps) from the queue and stops —
        useful for testing or a cron job that runs every few minutes.
        flask --app app steam-import-batch"""
        from steam_importer import run_import_batch
        from models import ImportJob
        from extensions import db
        job = ImportJob.query.first()
        if not job:
            job = ImportJob(status="running")
            db.session.add(job)
            db.session.commit()
        elif job.status != "running":
            job.status = "running"
            db.session.commit()
        summary = run_import_batch()
        print(f"Batch done: {summary}")

    @app.cli.command("steam-import-run")
    def steam_import_run():
        """Runs the importer continuously in THIS terminal (not a
        background thread) until the whole queue is processed or you
        Ctrl+C. Good for a dedicated long-running import session, e.g.
        inside a `screen`/`tmux` session or as a systemd service.
        flask --app app steam-import-run"""
        from steam_importer import seed_import_queue, run_import_batch, _count_pending
        from models import ImportJob
        from extensions import db

        job = ImportJob.query.first()
        if not job:
            job = ImportJob()
            db.session.add(job)
        job.status = "running"
        db.session.commit()

        if _count_pending() == 0:
            print("Queue empty — seeding from Steam's full app list (this alone can take a minute)...")
            n = seed_import_queue()
            print(f"Queued {n} apps.")

        print("Importing continuously. Ctrl+C to stop safely (progress is saved after every app).")
        try:
            while True:
                db.session.refresh(job)
                if job.status != "running":
                    print("Job paused/stopped from the admin panel — exiting.")
                    break
                summary = run_import_batch()
                print(f"Batch: {summary} | pending={_count_pending()}")
                if _count_pending() == 0:
                    job.status = "completed"
                    db.session.commit()
                    print("Import complete — no pending apps remain.")
                    break
        except KeyboardInterrupt:
            print("\nStopped by user. Progress is saved — run this command again to resume.")

    # ── Background scheduler (price sync + expired deal cleanup) ──────────────
    # Starts a daemon thread; safe to call multiple times (guarded internally).
    init_scheduler(app)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
