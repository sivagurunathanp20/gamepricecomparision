from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db, oauth
from models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _google_client():
    return oauth.create_client("google")


def _google_redirect_uri():
    configured = current_app.config.get("GOOGLE_REDIRECT_URI")
    if configured:
        return configured
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    return f"{scheme}://{host}/auth/google/callback"


def _safe_next(target):
    if not target:
        return url_for("main.home")
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme:
        return url_for("main.home")
    return target


def _unique_username(seed):
    base = (seed or "player").strip().replace(" ", "_")[:60] or "player"
    username = base
    suffix = 1
    while User.query.filter_by(username=username).first():
        suffix += 1
        username = f"{base}{suffix}"
    return username


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("auth.register"))

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(username=username).first():
            flash("That username is taken.", "danger")
            return redirect(url_for("auth.register"))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Account created! You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(email=email).first()
        if user and not user.password_hash:
            flash("This account uses Google Sign-In. Use the Google button below.", "warning")
            return redirect(url_for("auth.login", next=request.args.get("next")))

        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(_safe_next(request.args.get("next")))

        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))


@auth_bp.route("/google/login")
def google_login():
    """Start Google OAuth 2.0 — redirect to Google's consent screen."""
    google = _google_client()
    if not google:
        flash(
            "Google Sign-In isn't configured. Add GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET to your .env file (see .env.example).",
            "warning",
        )
        return redirect(url_for("auth.login"))

    session["oauth_next"] = request.args.get("next")
    return google.authorize_redirect(_google_redirect_uri())


@auth_bp.route("/google/callback")
def google_callback():
    """Exchange the OAuth 2.0 auth code for tokens and sign the user in."""
    google = _google_client()
    if not google:
        flash("Google Sign-In isn't configured on this server.", "warning")
        return redirect(url_for("auth.login"))

    try:
        token = google.authorize_access_token()
        user_info = token.get("userinfo") or google.userinfo(token=token)
    except Exception:
        flash("Google Sign-In failed or was cancelled. Please try again.", "danger")
        return redirect(url_for("auth.login"))

    google_id = user_info.get("sub")
    email = (user_info.get("email") or "").strip().lower()
    picture = (user_info.get("picture") or "").strip()
    if not google_id or not email:
        flash("Google didn't share the info we need (email). Please try again.", "danger")
        return redirect(url_for("auth.login"))

    destination = _safe_next(session.pop("oauth_next", None))

    # Logged-in user connecting Google from their profile.
    if current_user.is_authenticated:
        taken = User.query.filter_by(google_id=google_id).first()
        if taken and taken.id != current_user.id:
            flash("That Google account is already linked to a different GameVault user.", "danger")
            return redirect(url_for("auth.profile"))
        if current_user.email.lower() != email:
            flash("The Google account email must match your GameVault email.", "danger")
            return redirect(url_for("auth.profile"))
        current_user.google_id = google_id
        if picture:
            current_user.avatar = picture[:512]
        db.session.commit()
        flash("Google account connected.", "success")
        return redirect(url_for("auth.profile"))

    user = User.query.filter_by(google_id=google_id).first()

    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.google_id = google_id

    if not user:
        user = User(
            username=_unique_username(user_info.get("name") or email.split("@")[0]),
            email=email,
            google_id=google_id,
            auth_provider="google",
        )
        db.session.add(user)

    if picture:
        user.avatar = picture[:512]

    db.session.commit()
    login_user(user, remember=True)
    flash(f"Welcome, {user.username}!", "success")
    return redirect(destination)


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.username = request.form.get("username", current_user.username).strip()
        theme = request.form.get("theme_preference")
        if theme in ("dark", "light"):
            current_user.theme_preference = theme
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html")
