from datetime import datetime
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import Game, Platform, GamePlatform, Deal, User, Category, PriceHistory, Feedback, GameAlias

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def _save_aliases(game, raw_text):
    """Replaces this game's GameAlias rows with the comma-separated list
    from the admin form — this is what lets "GTAV", "CS2", "PUBG" etc.
    instantly resolve in search without relying on fuzzy matching alone."""
    GameAlias.query.filter_by(game_id=game.id).delete()
    seen = set()
    for raw in raw_text.split(","):
        alias = raw.strip()
        if alias and alias.lower() not in seen:
            seen.add(alias.lower())
            db.session.add(GameAlias(game_id=game.id, alias=alias))
    db.session.commit()


@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    stats = {
        "total_games": Game.query.count(),
        "total_users": User.query.count(),
        "total_deals": Deal.query.count(),
        "active_deals": Deal.query.filter(
            (Deal.expires_at.is_(None)) | (Deal.expires_at > datetime.utcnow())
        ).count(),
    }

    top_games = Game.query.order_by(Game.popularity_score.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()

    # simple 7-day-bucket signup trend for the analytics chart
    signup_trend = (
        db.session.query(db.func.date(User.created_at), db.func.count(User.id))
        .group_by(db.func.date(User.created_at))
        .order_by(db.func.date(User.created_at))
        .all()
    )

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        top_games=top_games,
        recent_users=recent_users,
        signup_trend=signup_trend,
    )


# --------------------------- GAMES ---------------------------

@admin_bp.route("/games")
@login_required
@admin_required
def games():
    all_games = Game.query.order_by(Game.created_at.desc()).all()
    return render_template("admin/games.html", games=all_games)


@admin_bp.route("/games/new", methods=["GET", "POST"])
@login_required
@admin_required
def game_new():
    categories = Category.query.all()
    platforms = Platform.query.all()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        slug = title.lower().replace(" ", "-").replace(":", "")
        steam_app_id = request.form.get("steam_app_id", type=int)

        if steam_app_id:
            existing = Game.query.filter_by(steam_app_id=steam_app_id).first()
            if existing:
                flash(f"Steam App ID {steam_app_id} is already in the catalog as "
                      f"\"{existing.title}\" — editing it instead of creating a duplicate.", "warning")
                return redirect(url_for("admin.game_edit", game_id=existing.id))

        from store_apis import resolve_game_image
        manual_cover = request.form.get("cover_image", "").strip()
        # Auto-fetch the official Steam image from the App ID unless the
        # admin explicitly pasted their own cover image URL.
        cover_image = manual_cover or resolve_game_image(steam_app_id=steam_app_id, verify=False)

        game = Game(
            title=title,
            slug=slug,
            description=request.form.get("description", ""),
            cover_image=cover_image,
            steam_app_id=steam_app_id,
            developer=request.form.get("developer", ""),
            publisher=request.form.get("publisher", ""),
            rating=request.form.get("rating", type=float) or 0,
            popularity_score=request.form.get("popularity_score", type=int) or 0,
            category_id=request.form.get("category_id", type=int),
            is_free_to_play=bool(request.form.get("is_free_to_play")),
        )
        db.session.add(game)
        db.session.commit()

        _save_aliases(game, request.form.get("aliases", ""))

        # Automation requirement: fetch prices/image from every supported
        # store API as soon as a game is added — no manual step needed.
        if steam_app_id:
            from store_apis import sync_game_from_apis
            try:
                sync_game_from_apis(game)
            except Exception as exc:
                flash(f"Game created, but the store sync hit an error: {exc}", "warning")

        flash("Game created.", "success")
        return redirect(url_for("admin.games"))

    return render_template("admin/game_form.html", categories=categories, platforms=platforms, game=None)


@admin_bp.route("/games/<int:game_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def game_edit(game_id):
    game = Game.query.get_or_404(game_id)
    categories = Category.query.all()
    platforms = Platform.query.all()

    if request.method == "POST":
        game.title = request.form.get("title", game.title)
        game.description = request.form.get("description", game.description)
        if manual_cover:
            game.cover_image = manual_cover
        elif not game.cover_image or game.cover_image.startswith("/static/img/placeholder"):
            game.cover_image = resolve_game_image(steam_app_id=game.steam_app_id, verify=False) or game.cover_image
        game.developer = request.form.get("developer", game.developer)
        game.publisher = request.form.get("publisher", game.publisher)
        game.rating = request.form.get("rating", type=float) or game.rating
        game.popularity_score = request.form.get("popularity_score", type=int) or game.popularity_score
        game.category_id = request.form.get("category_id", type=int)
        game.is_free_to_play = bool(request.form.get("is_free_to_play"))
        db.session.commit()

        _save_aliases(game, request.form.get("aliases", ""))

        flash("Game updated.", "success")
        return redirect(url_for("admin.games"))

    return render_template("admin/game_form.html", categories=categories, platforms=platforms, game=game)


@admin_bp.route("/games/<int:game_id>/sync", methods=["POST"])
@login_required
@admin_required
def game_sync(game_id):
    """Manually re-fetch this game's image + prices from every supported
    store API right now (Steam + CheapShark always; ITAD too if
    ITAD_API_KEY is configured)."""
    game = Game.query.get_or_404(game_id)

    if not game.steam_app_id:
        flash("Add a Steam App ID first — that's what drives the auto image + price sync.", "warning")
        return redirect(url_for("admin.game_edit", game_id=game.id))

    from store_apis import sync_game_from_apis
    try:
        summary = sync_game_from_apis(game)
        flash(f"Verified against official stores. Stores verified: {summary['stores_updated']}, "
              f"not verifiable: {summary['stores_failed']}.", "success")
    except Exception as exc:
        flash(f"Sync failed: {exc}", "danger")

    return redirect(url_for("admin.game_edit", game_id=game.id))


@admin_bp.route("/games/<int:game_id>/delete", methods=["POST"])
@login_required
@admin_required
def game_delete(game_id):
    game = Game.query.get_or_404(game_id)
    db.session.delete(game)
    db.session.commit()
    flash("Game deleted.", "info")
    return redirect(url_for("admin.games"))


@admin_bp.route("/games/<int:game_id>/set-price", methods=["POST"])
@login_required
@admin_required
def set_price(game_id):
    """Manual prices are disabled: every price must come from the official store."""
    flash("Manual prices are disabled. Prices are read from the official stores only - "
          "use 'Sync' or the add-official-product command.", "warning")
    return redirect(url_for("admin.game_edit", game_id=game_id))


# --------------------------- DEALS ---------------------------

@admin_bp.route("/deals")
@login_required
@admin_required
def deals():
    all_deals = Deal.query.order_by(Deal.created_at.desc()).all()
    return render_template("admin/deals.html", deals=all_deals)


@admin_bp.route("/deals/new", methods=["GET", "POST"])
@login_required
@admin_required
def deal_new():
    games_list = Game.query.all()
    platforms = Platform.query.all()

    if request.method == "POST":
        expires_raw = request.form.get("expires_at")
        expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None

        deal = Deal(
            game_id=request.form.get("game_id", type=int),
            platform_id=request.form.get("platform_id", type=int),
            deal_type=request.form.get("deal_type", "discount"),
            discount_percent=request.form.get("discount_percent", type=int) or 0,
            expires_at=expires_at,
            is_featured=bool(request.form.get("is_featured")),
        )
        db.session.add(deal)
        db.session.commit()
        flash("Deal created.", "success")
        return redirect(url_for("admin.deals"))

    return render_template("admin/deal_form.html", games=games_list, platforms=platforms)


@admin_bp.route("/deals/<int:deal_id>/delete", methods=["POST"])
@login_required
@admin_required
def deal_delete(deal_id):
    deal = Deal.query.get_or_404(deal_id)
    db.session.delete(deal)
    db.session.commit()
    flash("Deal deleted.", "info")
    return redirect(url_for("admin.deals"))


# --------------------------- USERS ---------------------------

@admin_bp.route("/users")
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
@login_required
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot change your own admin status.", "warning")
        return redirect(url_for("admin.users"))

    user.is_admin = not user.is_admin
    db.session.commit()
    flash(f"{user.username} admin status updated.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def user_delete(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete your own account here.", "warning")
        return redirect(url_for("admin.users"))

    db.session.delete(user)
    db.session.commit()
    flash("User deleted.", "info")
    return redirect(url_for("admin.users"))


# --------------------------- FEEDBACK ---------------------------

@admin_bp.route("/feedback")
@login_required
@admin_required
def feedback():
    all_feedback = Feedback.query.order_by(Feedback.created_at.desc()).all()
    return render_template("admin/feedback.html", feedback_list=all_feedback)


@admin_bp.route("/feedback/<int:feedback_id>/mark-reviewed", methods=["POST"])
@login_required
@admin_required
def feedback_mark_reviewed(feedback_id):
    fb = Feedback.query.get_or_404(feedback_id)
    fb.is_reviewed = True
    db.session.commit()
    flash("Marked as reviewed.", "success")
    return redirect(url_for("admin.feedback"))


# --------------------------- STEAM CATALOG IMPORT ---------------------------

@admin_bp.route("/steam-import")
@login_required
@admin_required
def steam_import():
    from models import ImportJob, SteamImportQueue
    job = ImportJob.query.first()
    recent_failures = (
        SteamImportQueue.query.filter_by(status="failed")
        .order_by(SteamImportQueue.last_attempted_at.desc())
        .limit(20)
        .all()
    )
    pending_count = SteamImportQueue.query.filter_by(status="pending").count()
    return render_template(
        "admin/steam_import.html",
        job=job,
        recent_failures=recent_failures,
        pending_count=pending_count,
    )


@admin_bp.route("/steam-import/status")
@login_required
@admin_required
def steam_import_status():
    """JSON endpoint the admin page polls every few seconds for a live
    progress bar, without a full page reload."""
    from models import ImportJob, SteamImportQueue
    job = ImportJob.query.first()
    if not job:
        return jsonify({"status": "idle", "processed": 0, "total": 0, "imported": 0,
                         "skipped": 0, "failed": 0, "pending": 0, "message": ""})
    return jsonify({
        "status": job.status,
        "processed": job.processed_count,
        "total": job.total_apps,
        "imported": job.imported_count,
        "skipped": job.skipped_count,
        "failed": job.failed_count,
        "pending": SteamImportQueue.query.filter_by(status="pending").count(),
        "message": job.last_message,
    })


@admin_bp.route("/steam-import/start", methods=["POST"])
@login_required
@admin_required
def steam_import_start():
    from steam_importer import start_background_import
    try:
        start_background_import()
        flash("Steam catalog import started — this runs in the background and can "
              "take a long time for the full catalog. Progress updates live below.", "success")
    except Exception as exc:
        flash(f"Could not start import: {exc}", "danger")
    return redirect(url_for("admin.steam_import"))


@admin_bp.route("/steam-import/pause", methods=["POST"])
@login_required
@admin_required
def steam_import_pause():
    from steam_importer import pause_background_import
    pause_background_import()
    flash("Import paused. Click Start/Resume to continue from exactly where it left off.", "info")
    return redirect(url_for("admin.steam_import"))


@admin_bp.route("/steam-import/retry-failed", methods=["POST"])
@login_required
@admin_required
def steam_import_retry_failed():
    from steam_importer import retry_failed
    count = retry_failed()
    flash(f"{count} failed import(s) reset to pending — they'll be retried on the next run.", "success")
    return redirect(url_for("admin.steam_import"))


@admin_bp.route("/steam-import/import-one", methods=["POST"])
@login_required
@admin_required
def steam_import_one():
    from steam_importer import import_single_app
    app_id = request.form.get("steam_app_id", type=int)
    if not app_id:
        flash("Enter a valid numeric Steam App ID.", "warning")
        return redirect(url_for("admin.steam_import"))

    status, message = import_single_app(app_id)
    category = {"imported": "success", "updated": "success",
                "skipped": "warning", "failed": "danger"}.get(status, "info")
    flash(f"App {app_id}: {status} — {message}", category)
    return redirect(url_for("admin.steam_import"))
