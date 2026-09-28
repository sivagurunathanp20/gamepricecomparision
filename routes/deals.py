from datetime import datetime
from flask import Blueprint, render_template, request
from sqlalchemy import or_

from models import Deal, Game, GamePlatform


def _deal_is_verified(deal):
    """A deal is only shown when the official store currently confirms it.

    For free/giveaway/weekend deals the listing just needs current_price == 0
    (the store really is offering it free).  We don't require the full
    price_is_trusted check here because free-to-play games are often never
    run through the official-price verifier — their price IS the fact that
    they are free.
    """
    listing = GamePlatform.query.filter_by(game_id=deal.game_id, platform_id=deal.platform_id).first()
    if not listing:
        return False
    if deal.deal_type in ("free", "giveaway", "weekend_ftp"):
        # Accept: price confirmed 0, OR the game is flagged free-to-play in the catalogue.
        return listing.current_price == 0 or deal.game.is_free_to_play
    # Paid discounts must be fully verified and fresh.
    return listing.price_is_trusted and (listing.discount_percent or 0) > 0

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

    # Show all active deals that have a discount — no official-verification gate
    # here so deals appear even before the price scraper has run.
    deals = query.limit(30).all()

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
    # Exclude any already shown via a Deal row to avoid duplicates.
    # NOTE: do NOT filter by g.best_price here — free-to-play games have
    # current_price=0 and are never run through the paid-price verifier, so
    # best_price is always None for them. The card template handles F2P
    # games without a listing just fine (shows "Free" + "Play Now").
    deal_game_ids = {d.game_id for d in free_deals}
    always_free_games = (
        Game.query
        .filter(Game.is_free_to_play == True)  # noqa: E712
        .filter(Game.id.notin_(deal_game_ids) if deal_game_ids else True)
        .order_by(Game.popularity_score.desc())
        .all()
    )

    return render_template(
        "free_games.html",
        free_deals=free_deals,
        always_free_games=always_free_games,
        now=now,
    )
