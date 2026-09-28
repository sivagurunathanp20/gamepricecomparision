from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, session, jsonify
from flask_login import current_user, login_required
from sqlalchemy import or_, func
from flask import current_app

from extensions import db
from models import Game, GamePlatform, Platform, Deal, Category, Review, Feedback, Edition

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    now = datetime.utcnow()
    # Only show deals that are active (no expiry or expiry in the future)
    active_deal_filter = or_(Deal.expires_at.is_(None), Deal.expires_at > now)

    featured_deal = (
        Deal.query
        .filter(Deal.deal_type == "discount", active_deal_filter)
        .order_by(Deal.discount_percent.desc())
        .first()
    )
    # Trending: only show games that have at least one officially-verified,
    # fresh price so every card shows a real number, not "Price not fetched yet".
    cutoff = datetime.utcnow() - timedelta(minutes=current_app.config.get("PRICE_MAX_AGE_MINUTES", 720))
    _verified_game_ids_q = (
        db.session.query(GamePlatform.game_id)
        .join(Edition, Edition.listing_id == GamePlatform.id)
        .filter(
            GamePlatform.verify_status == "verified",
            GamePlatform.last_verified_at >= cutoff,
            Edition.current_price.isnot(None),
            Edition.is_available.is_(True),
            Edition.url_verified_at.isnot(None),
        )
    )
    # Fall back to all games if no verified data exists yet (e.g. first run).
    _has_verified = db.session.query(GamePlatform.id).filter(
        GamePlatform.verify_status == "verified"
    ).limit(1).scalar() is not None
    _verified_ids = [r[0] for r in _verified_game_ids_q.all()] if _has_verified else None

    trending_q = Game.query.order_by(Game.popularity_score.desc())
    if _verified_ids is not None:
        # Also include free-to-play games even if not in the verified list
        trending_q = trending_q.filter(
            or_(Game.id.in_(_verified_ids), Game.is_free_to_play.is_(True))
        )
    trending = trending_q.limit(8).all()
    # Biggest discounts — one entry per game, showing its highest discount.
    # Deduplicated in Python so it works with SQLite (DISTINCT ON is PG-only).
    _all_discounts = (
        db.session.query(Game, GamePlatform)
        .join(GamePlatform, Game.id == GamePlatform.game_id)
        .filter(GamePlatform.discount_percent > 0, GamePlatform.current_price.isnot(None))
        .order_by(GamePlatform.discount_percent.desc())
        .all()
    )
    _seen_game_ids = set()
    biggest_discounts = []
    for _g, _l in _all_discounts:
        if _g.id not in _seen_game_ids:
            _seen_game_ids.add(_g.id)
            biggest_discounts.append((_g, _l))
            if len(biggest_discounts) == 8:
                break

    # Fill remaining slots from CheapShark (live, cross-store) when the
    # officially-verified list is short — same aggregator used on the game
    # detail page's "Compare Prices Across Stores" panel. This keeps the
    # section from sitting empty just because no Steam listing happens to
    # be on sale right now / hasn't been re-verified yet.
    # Bounded to a total wall-clock budget so a slow/unreachable CheapShark
    # never hangs the homepage — whatever hasn't answered in time is just
    # skipped for this load (results that DO come back are cached, so the
    # next load is fast).
    if len(biggest_discounts) < 8:
        try:
            import concurrent.futures
            from types import SimpleNamespace
            from store_apis import cheapshark_lookup_game_id, cheapshark_fetch_prices

            def _cs_best_discount(g):
                cs_id = cheapshark_lookup_game_id(title=g.title, steam_app_id=g.steam_app_id)
                prices, _ = cheapshark_fetch_prices(cs_id)
                best = max((p for p in prices if p.get("discount_percent")),
                           key=lambda p: p["discount_percent"], default=None)
                if not best:
                    return None
                return (g, SimpleNamespace(
                    discount_percent=best["discount_percent"],
                    original_price=best["original_price"],
                    current_price=best["current_price"],
                    price_currency="USD",
                    platform=SimpleNamespace(name=best["shop"]),
                ))

            candidates = (
                Game.query.filter(~Game.id.in_(_seen_game_ids))
                .order_by(Game.popularity_score.desc())
                .limit(12)
                .all()
            )
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
            futures = {pool.submit(_cs_best_discount, g): g for g in candidates}
            done, not_done = concurrent.futures.wait(futures, timeout=3)
            for f in not_done:
                f.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
            for f in done:
                try:
                    result = f.result()
                except Exception:
                    continue
                if result and result[0].id not in _seen_game_ids:
                    _seen_game_ids.add(result[0].id)
                    biggest_discounts.append(result)
            biggest_discounts.sort(key=lambda pair: pair[1].discount_percent, reverse=True)
            biggest_discounts = biggest_discounts[:8]
        except Exception:
            pass

    free_games = Game.query.filter_by(is_free_to_play=True).limit(6).all()
    # Top Rated: same verified-only filter as Trending.
    top_rated_q = Game.query.order_by(Game.rating.desc())
    if _verified_ids is not None:
        top_rated_q = top_rated_q.filter(
            or_(Game.id.in_(_verified_ids), Game.is_free_to_play.is_(True))
        )
    top_rated = top_rated_q.limit(8).all()

    return render_template(
        "index.html",
        featured_deal=featured_deal,
        trending=trending,
        biggest_discounts=biggest_discounts,
        free_games=free_games,
        top_rated=top_rated,
    )


@main_bp.route("/compare")
def compare():
    query = Game.query

    search = request.args.get("q", "").strip()
    genre = request.args.get("genre", "")
    platform = request.args.get("platform", "")
    sort = request.args.get("sort", "popularity")
    min_rating = request.args.get("min_rating", type=float)

    if search:
        from search import search_games
        matched_ids = [g.id for g in search_games(search, limit=200)]
        query = query.filter(Game.id.in_(matched_ids)) if matched_ids else query.filter(Game.id.is_(None))
    if genre:
        query = query.join(Category).filter(Category.slug == genre)
    if min_rating:
        query = query.filter(Game.rating >= min_rating)

    # Only OFFICIALLY VERIFIED, fresh offers take part in filtering/sorting.
    cutoff = datetime.utcnow() - timedelta(minutes=current_app.config["PRICE_MAX_AGE_MINUTES"])
    offer_q = (
        db.session.query(
            GamePlatform.game_id.label("gid"),
            func.min(Edition.current_price).label("min_price"),
            func.max(Edition.discount_percent).label("max_disc"),
        )
        .join(Edition, Edition.listing_id == GamePlatform.id)
        .filter(GamePlatform.verify_status == "verified",
                GamePlatform.last_verified_at >= cutoff,
                Edition.current_price.isnot(None),
                Edition.is_available.is_(True),
                Edition.url_verified_at.isnot(None))
    )
    if platform:
        offer_q = offer_q.join(Platform, Platform.id == GamePlatform.platform_id).filter(Platform.name == platform)
    offers = offer_q.group_by(GamePlatform.game_id).subquery()
    query = query.outerjoin(offers, offers.c.gid == Game.id)

    # Strict mode: hide games with no verified price — BUT fall back to showing
    # all games when NO verified data exists yet (e.g. before the price scraper
    # has run for the first time), so the page is never completely empty.
    from extensions import db as _db
    has_any_verified = _db.session.query(GamePlatform.id).filter(
        GamePlatform.verify_status == "verified"
    ).limit(1).scalar() is not None

    if platform or (has_any_verified and not current_app.config["SHOW_UNVERIFIED_GAMES"]):
        query = query.filter(offers.c.gid.isnot(None))


    if sort == "price_low":
        query = query.order_by(offers.c.min_price.is_(None), offers.c.min_price.asc())
    elif sort == "price_high":
        query = query.order_by(offers.c.min_price.is_(None), offers.c.min_price.desc())
    elif sort == "discount":
        query = query.order_by(offers.c.max_disc.is_(None), offers.c.max_disc.desc())
    elif sort == "rating":
        query = query.order_by(Game.rating.desc())
    else:
        query = query.order_by(Game.popularity_score.desc())

    page = request.args.get("page", 1, type=int)
    pagination = query.paginate(page=page, per_page=12, error_out=False)

    categories = Category.query.all()
    platforms = Platform.query.all()

    return render_template(
        "compare.html",
        games=pagination.items,
        pagination=pagination,
        categories=categories,
        platforms=platforms,
        search=search,
        selected_genre=genre,
        selected_platform=platform,
        sort=sort,
    )


@main_bp.route("/game/<slug>")
def game_details(slug):
    slug_clean = (slug or "").strip().lower()
    game = Game.query.filter_by(slug=slug_clean).first()
    if not game:
        game = Game.query.filter(func.lower(Game.slug) == slug_clean).first()
    if not game and slug_clean.isdigit():
        game = Game.query.get(int(slug_clean))
    if not game:
        game = Game.query.filter(func.lower(Game.title) == slug_clean.replace("-", " ")).first()
    if not game:
        game = Game.query.filter(Game.slug.ilike(f"%{slug_clean}%")).first()
    if not game:
        from flask import abort
        abort(404)

    # track "recently viewed" in session (last 8, most-recent first)
    recent = session.get("recently_viewed", [])
    recent = [g for g in recent if g != game.id]
    recent.insert(0, game.id)
    session["recently_viewed"] = recent[:8]

    # Re-verify against the official store(s) when the data is getting old.
    stale_after = timedelta(minutes=current_app.config["REFRESH_ON_VIEW_MINUTES"])
    if any(l.last_verified_at is None or datetime.utcnow() - l.last_verified_at > stale_after
           for l in game.platform_listings if l.store_product_id or l.editions) or \
            (game.steam_app_id and not game.platform_listings):
        try:
            from official_prices import verify_game, RateLimited
            verify_game(game)
        except RateLimited:
            db.session.rollback()  # Steam rate-limited; keep existing data, don't retry on this request
        except Exception:
            db.session.rollback()

    reviews = Review.query.filter_by(game_id=game.id).order_by(Review.created_at.desc()).all()

    price_points = sorted((p for p in game.price_history if p.verified), key=lambda p: p.recorded_at)
    chart_labels = [p.recorded_at.strftime("%b %d") for p in price_points]
    chart_prices = [round(p.price, 2) for p in price_points]  # official price, store currency
    chart_currency = next((l.price_currency for l in game.platform_listings if l.verify_status == "verified"), "")

    similar_games = (
        Game.query.filter(Game.category_id == game.category_id, Game.id != game.id)
        .limit(4)
        .all()
    )

    # Cross-store price comparison (CheapShark: free, no API key, covers
    # Steam/GOG/Humble/Fanatical/Green Man Gaming/Epic/Ubisoft/etc. at once).
    # Separate from the "Official Prices" block above: these are aggregator
    # numbers, not re-verified against each store directly, so they're
    # labelled as such in the template rather than mixed in as "verified".
    from store_apis import cheapshark_lookup_game_id, cheapshark_fetch_prices, PLATFORM_BRAND_COLORS
    store_comparisons = []
    try:
        cs_id = cheapshark_lookup_game_id(title=game.title, steam_app_id=game.steam_app_id)
        store_comparisons, _historical_low = cheapshark_fetch_prices(cs_id)
        for c in store_comparisons:
            c["color"] = PLATFORM_BRAND_COLORS.get(c["shop"], "#888888")
        store_comparisons.sort(key=lambda c: c["current_price"])
    except Exception:
        store_comparisons = []

    return render_template(
        "game_details.html",
        store_comparisons=store_comparisons,
        game=game,
        reviews=reviews,
        chart_labels=chart_labels,
        chart_prices=chart_prices,
        chart_currency=chart_currency,
        similar_games=similar_games,
    )


@main_bp.route("/dashboard")
@login_required
def dashboard():
    recent_ids = session.get("recently_viewed", [])
    recently_viewed = Game.query.filter(Game.id.in_(recent_ids)).all() if recent_ids else []
    # preserve session order
    recently_viewed.sort(key=lambda g: recent_ids.index(g.id))

    return render_template("dashboard.html", recently_viewed=recently_viewed)


@main_bp.route("/feedback", methods=["GET", "POST"])
def feedback():
    from flask import flash, redirect, url_for

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        category = request.form.get("category", "general")
        message = request.form.get("message", "").strip()
        rating = request.form.get("rating", type=int)

        if not name or not email or not message:
            flash("Please fill in your name, email, and message.", "danger")
            return redirect(url_for("main.feedback"))

        fb = Feedback(
            user_id=current_user.id if current_user.is_authenticated else None,
            name=name,
            email=email,
            category=category,
            message=message,
            rating=rating,
        )
        db.session.add(fb)
        db.session.commit()
        flash("Thanks for your feedback! Our team will take a look.", "success")
        return redirect(url_for("main.feedback"))

    return render_template("feedback.html")


@main_bp.route("/api/search")
def api_search():
    """AJAX live-search endpoint used by the navbar search box."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])

    from flask import current_app as _app
    official_price_text = lambda l: _app.jinja_env.filters["official_price"](l.current_price, l.price_currency)
    from search import autocomplete_suggestions
    display_currency = session.get("currency", "USD")
    results = autocomplete_suggestions(q, limit=8)

    def price_label(g):
        if g.is_free_to_play:
            return "Free"
        if g.best_price is not None:
            return official_price_text(g.best_price)
        return "Unable to verify price"

    return jsonify(
        [
            {
                "title": g.title,
                "slug": g.slug,
                "cover_image": g.cover_image,
                "price": price_label(g),
            }
            for g in results
        ]
    )


@main_bp.route("/games")
def all_games():
    """Browse every game in the catalogue using the same card style as
    Home / Deals / Free Games."""
    search          = request.args.get("q", "").strip()
    selected_genre  = request.args.get("genre", "")
    selected_platform = request.args.get("platform", "")
    selected_type   = request.args.get("type", "all")
    sort            = request.args.get("sort", "popularity")
    page            = request.args.get("page", 1, type=int)

    query = Game.query

    # ── Text search ───────────────────────────────────────────────
    if search:
        from search import search_games
        matched_ids = [g.id for g in search_games(search, limit=200)]
        query = query.filter(Game.id.in_(matched_ids)) if matched_ids else query.filter(Game.id.is_(None))

    # ── Genre filter ──────────────────────────────────────────────
    if selected_genre:
        query = query.join(Category).filter(Category.slug == selected_genre)

    # ── Platform filter ───────────────────────────────────────────
    if selected_platform:
        query = (query
                 .join(GamePlatform, GamePlatform.game_id == Game.id)
                 .join(Platform, Platform.id == GamePlatform.platform_id)
                 .filter(Platform.name == selected_platform)
                 .distinct())

    # ── Type filter ───────────────────────────────────────────────
    if selected_type == "free":
        query = query.filter(Game.is_free_to_play == True)   # noqa: E712
    elif selected_type == "paid":
        query = query.filter(Game.is_free_to_play == False)  # noqa: E712
    elif selected_type == "deals":
        now = datetime.utcnow()
        deal_game_ids = db.session.query(Deal.game_id).filter(
            or_(Deal.expires_at.is_(None), Deal.expires_at > now),
            Deal.deal_type == "discount",
        )
        query = query.filter(Game.id.in_(deal_game_ids))

    # ── Price subquery (for price-based sorting only) ─────────────
    # The All Games page shows every game in the catalogue regardless of
    # verification status — the verified-price restriction belongs on
    # /compare (price comparison), not here.
    all_cutoff = datetime.utcnow() - timedelta(minutes=current_app.config.get("PRICE_MAX_AGE_MINUTES", 720))
    all_offer_q = (
        db.session.query(
            GamePlatform.game_id.label("gid"),
            func.min(Edition.current_price).label("min_price"),
            func.max(Edition.discount_percent).label("max_disc"),
        )
        .join(Edition, Edition.listing_id == GamePlatform.id)
        .filter(
            GamePlatform.verify_status == "verified",
            GamePlatform.last_verified_at >= all_cutoff,
            Edition.current_price.isnot(None),
            Edition.is_available.is_(True),
            Edition.url_verified_at.isnot(None),
        )
    )
    if selected_platform:
        all_offer_q = (all_offer_q
                       .join(Platform, Platform.id == GamePlatform.platform_id)
                       .filter(Platform.name == selected_platform))
    all_offers = all_offer_q.group_by(GamePlatform.game_id).subquery()
    query = query.outerjoin(all_offers, all_offers.c.gid == Game.id)

    # ── Sorting ───────────────────────────────────────────────────
    if sort == "rating":
        query = query.order_by(Game.rating.desc())
    elif sort == "price_low":
        query = query.order_by(all_offers.c.min_price.is_(None), all_offers.c.min_price.asc())
    elif sort == "price_high":
        query = query.order_by(all_offers.c.min_price.is_(None), all_offers.c.min_price.desc())
    elif sort == "discount":
        query = query.order_by(all_offers.c.max_disc.is_(None), all_offers.c.max_disc.desc())
    elif sort == "newest":
        query = query.order_by(Game.created_at.desc())
    elif sort == "az":
        query = query.order_by(Game.title.asc())
    else:  # popularity (default)
        query = query.order_by(Game.popularity_score.desc())

    pagination = query.paginate(page=page, per_page=24, error_out=False)

    categories = Category.query.order_by(Category.name).all()
    platforms  = Platform.query.order_by(Platform.name).all()

    return render_template(
        "all_games.html",
        games=pagination.items,
        pagination=pagination,
        categories=categories,
        platforms=platforms,
        search=search,
        selected_genre=selected_genre,
        selected_platform=selected_platform,
        selected_type=selected_type,
        sort=sort,
    )

