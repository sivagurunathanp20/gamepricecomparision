from datetime import datetime
from flask import Blueprint, render_template, request
from sqlalchemy import or_

from models import Deal, Game, GamePlatform


def _deal_is_verified(deal):
    """A deal is only shown when the official store currently confirms it."""
    listing = GamePlatform.query.filter_by(game_id=deal.game_id, platform_id=deal.platform_id).first()
    if not listing or not listing.price_is_trusted:
        return False
    if deal.deal_type in ("free", "giveaway", "weekend_ftp"):
        return listing.current_price == 0
    return (listing.discount_percent or 0) > 0

deals_bp = Blueprint("deals", __name__, url_prefix="/deals")


def _active_deals_query():
    """Base query that excludes expired deals.
    A deal is active when expires_at is NULL (permanent) or in the future."""
    now = datetime.utcnow()
    return Deal.query.filter(
        or_(Deal.expires_at.is_(None), Deal.expires_at > now)
    )


@deals_bp.route("/")
def index():
    filter_type = request.args.get("type", "all")

    query = _active_deals_query().filter(Deal.deal_type != "free")

    if filter_type == "biggest":
        query = query.order_by(Deal.discount_percent.desc())
    elif filter_type == "trending":
        query = query.join(Game).order_by(Game.popularity_score.desc())
    elif filter_type == "new":
        query = query.order_by(Deal.created_at.desc())
    elif filter_type == "limited":
        query = query.filter(Deal.expires_at.isnot(None)).order_by(Deal.expires_at.asc())
    else:
        query = query.order_by(Deal.discount_percent.desc())

    deals = [d for d in query.limit(100).all() if _deal_is_verified(d)][:30]

    return render_template("deals.html", deals=deals, filter_type=filter_type, now=datetime.utcnow())


@deals_bp.route("/free-games")
def free_games():
    now = datetime.utcnow()

    # Limited-time: active free/giveaway/free-weekend Deal rows
    free_deals = (
        _active_deals_query()
        .filter(Deal.deal_type.in_(["free", "giveaway", "weekend_ftp"]))
        .order_by(Deal.expires_at.asc())
        .all()
    )
    free_deals = [d for d in free_deals if _deal_is_verified(d)]

    # Permanently free: games marked is_free_to_play=True in the catalogue
    # Exclude any already shown via a Deal row to avoid duplicates
    deal_game_ids = {d.game_id for d in free_deals}
    always_free_games = (
        Game.query
        .filter(Game.is_free_to_play == True)  # noqa: E712
        .filter(Game.id.notin_(deal_game_ids) if deal_game_ids else True)
        .order_by(Game.popularity_score.desc())
        .all()
    )
    always_free_games = [g for g in always_free_games if g.best_price]

    return render_template(
        "free_games.html",
        free_deals=free_deals,
        always_free_games=always_free_games,
        now=now,
    )
