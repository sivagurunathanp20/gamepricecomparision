from flask import Blueprint, jsonify, request

from models import Game, GamePlatform, Platform, Category, Deal, PriceHistory

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _serialize_game(game):
    # Cheapest-first, and stores with no confirmed price sort last rather
    # than showing as "$0" — an unavailable price is not a low price.
    sorted_listings = sorted(
        game.platform_listings,
        key=lambda gp: (gp.current_price is None, gp.current_price if gp.current_price is not None else 0),
    )
    listings = [
        {
            "platform": gp.platform.name,
            "current_price": gp.current_price,
            "original_price": gp.original_price,
            "discount_percent": gp.discount_percent,
            "historical_low_price": gp.historical_low_price,
            "available": gp.current_price is not None,
            "store_url": gp.store_url,
            "in_stock": gp.in_stock,
            "updated_at": gp.updated_at.isoformat() if gp.updated_at else None,
        }
        for gp in sorted_listings
    ]
    return {
        "id": game.id,
        "title": game.title,
        "slug": game.slug,
        "aliases": game.alias_list,
        "cover_image": game.cover_image,
        "rating": game.rating,
        "metacritic_score": game.metacritic_score,
        "popularity_score": game.popularity_score,
        "category": game.category.name if game.category else None,
        "is_free_to_play": game.is_free_to_play,
        "release_date": game.release_date.isoformat() if game.release_date else None,
        "historical_low": game.historical_low,
        "platforms": listings,
    }


@api_bp.route("/games")
def list_games():
    """Filterable/paginated REST endpoint. Query params: q, genre, platform,
    min_price, max_price, min_rating, sort, page.

    `q` supports fuzzy/alias/abbreviation matching — "GTAV", "CS2", "PUBG"
    etc. all resolve to the right game (see search.py)."""
    query = Game.query

    q = request.args.get("q", "").strip()
    genre = request.args.get("genre")
    platform = request.args.get("platform")
    min_rating = request.args.get("min_rating", type=float)
    sort = request.args.get("sort", "popularity")
    page = request.args.get("page", 1, type=int)

    if q:
        from search import search_games
        matched_ids = [g.id for g in search_games(q, limit=200)]
        query = query.filter(Game.id.in_(matched_ids)) if matched_ids else query.filter(Game.id.is_(None))
    if genre:
        query = query.join(Category).filter(Category.slug == genre)
    if platform:
        query = query.join(GamePlatform).join(Platform).filter(Platform.name == platform)
    if min_rating:
        query = query.filter(Game.rating >= min_rating)

    if sort == "rating":
        query = query.order_by(Game.rating.desc())
    elif sort == "newest":
        query = query.order_by(Game.created_at.desc())
    else:
        query = query.order_by(Game.popularity_score.desc())

    pagination = query.distinct().paginate(page=page, per_page=12, error_out=False)

    return jsonify(
        {
            "page": pagination.page,
            "pages": pagination.pages,
            "total": pagination.total,
            "results": [_serialize_game(g) for g in pagination.items],
        }
    )


@api_bp.route("/games/<int:game_id>/price-history")
def price_history(game_id):
    points = (
        PriceHistory.query.filter_by(game_id=game_id)
        .order_by(PriceHistory.recorded_at.asc())
        .all()
    )
    return jsonify(
        [
            {
                "date": p.recorded_at.isoformat(),
                "price": p.price,
                "platform": p.platform.name,
            }
            for p in points
        ]
    )


@api_bp.route("/deals/active")
def active_deals():
    from datetime import datetime

    deals = Deal.query.filter(
        (Deal.expires_at.is_(None)) | (Deal.expires_at > datetime.utcnow())
    ).all()

    return jsonify(
        [
            {
                "game": d.game.title,
                "platform": d.platform.name,
                "deal_type": d.deal_type,
                "discount_percent": d.discount_percent,
                "expires_at": d.expires_at.isoformat() if d.expires_at else None,
            }
            for d in deals
        ]
    )
