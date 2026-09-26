"""
GameVault Assistant — "Vault", now powered by the Claude API.

POST /api/chat  { "message": "<user text>", "history": [{"role":"user"|"bot","text":"..."}, ...] }
                → { "reply": "<bot response>", "links": [{"label":..., "url":...}, ...] }

Vault is grounded in LIVE site data (current deals, free games, trending
titles, and — if logged in — the user's own wishlist) that's pulled fresh
from the database on every request and handed to Claude as context. It's
told to only ever mention games/prices that appear in that context, so it
can't invent a title or a price that isn't real.

If ANTHROPIC_API_KEY isn't set (e.g. running the project without a key),
this quietly falls back to the original keyword-matching bot below, so
the app still works out of the box with zero setup.

Setup: pip install anthropic, then set ANTHROPIC_API_KEY in .env
(get a key at https://console.anthropic.com/).
"""

import json
import os
import re

from flask import Blueprint, request, jsonify, url_for
from flask_login import current_user

from models import Game, GamePlatform, Deal, Wishlist
from extensions import db

assistant_bp = Blueprint("assistant", __name__)

try:
    import anthropic
except ImportError:
    anthropic = None

AI_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
_client = anthropic.Anthropic(api_key=_api_key) if (anthropic and _api_key) else None

MAX_HISTORY_TURNS = 6  # past user/bot exchanges fed to the model for context


# ─── grounding: pull real, current data out of the database ─────────────────

def _format_price(price):
    return "N/A" if price is None else f"${price:.2f}"


def _game_line(game, listing=None):
    """One plain-text line describing a game + its price, for the model's context block."""
    if game.is_free_to_play:
        price_bit = "Free-to-play"
    elif listing is not None and listing.current_price is not None:
        disc = f", -{listing.discount_percent}%" if listing.discount_percent else ""
        store = listing.platform.name if listing.platform else "store"
        price_bit = f"{_format_price(listing.current_price)} on {store}{disc}"
    elif game.best_price:
        bp = game.best_price
        disc = f", -{bp.discount_percent}%" if bp.discount_percent else ""
        store = bp.platform.name if bp.platform else "store"
        price_bit = f"{_format_price(bp.current_price)} on {store}{disc}"
    else:
        price_bit = "no live price"
    return f"- {game.title} (slug: {game.slug}) — {price_bit}, rating {game.rating:.1f}/5"


def _build_context():
    top_deals = (
        GamePlatform.query
        .filter(GamePlatform.discount_percent > 0, GamePlatform.current_price.isnot(None))
        .order_by(GamePlatform.discount_percent.desc())
        .limit(8)
        .all()
    )
    deal_lines = []
    for gp in top_deals:
        game = Game.query.get(gp.game_id)
        if game:
            deal_lines.append(_game_line(game, gp))

    free_games = Game.query.filter_by(is_free_to_play=True).limit(6).all()
    free_deals = (
        Deal.query.filter(Deal.deal_type.in_(["free", "giveaway", "weekend_ftp"]))
        .order_by(Deal.created_at.desc()).limit(6).all()
    )
    free_lines = [_game_line(g) for g in free_games]
    for d in free_deals:
        g = Game.query.get(d.game_id)
        if g:
            free_lines.append(_game_line(g))

    trending = Game.query.order_by(Game.popularity_score.desc()).limit(8).all()
    trending_lines = [_game_line(g) for g in trending]

    parts = [
        "TOP DISCOUNTS RIGHT NOW:\n" + ("\n".join(deal_lines) or "none tracked right now"),
        "FREE GAMES RIGHT NOW:\n" + ("\n".join(free_lines) or "none tracked right now"),
        "TRENDING GAMES:\n" + ("\n".join(trending_lines) or "none tracked right now"),
    ]

    if current_user.is_authenticated:
        items = Wishlist.query.filter_by(user_id=current_user.id).limit(10).all()
        wishlist_lines = []
        for w in items:
            g = Game.query.get(w.game_id)
            if g:
                wishlist_lines.append(_game_line(g))
        parts.append(
            f"LOGGED-IN USER: {current_user.username}\nTHEIR WISHLIST:\n"
            + ("\n".join(wishlist_lines) or "empty")
        )
    else:
        parts.append("USER IS NOT LOGGED IN (no wishlist to reference; suggest logging in for price alerts).")

    return "\n\n".join(parts)


SYSTEM_PROMPT = """You are Vault, the friendly in-site assistant for GameVault, a game price \
comparison and deal-tracking website covering Steam, Epic, GOG, Xbox, PlayStation and more.

Ground every price, title and discount you mention ONLY in the SITE DATA block you're given \
each turn — never invent a game, price or percentage that isn't listed there. If someone asks \
about a game that isn't in SITE DATA, say plainly that you don't have live data on it right now \
and point them at the search bar or the Compare page instead of guessing.

Keep replies short and conversational (2-4 sentences, markdown **bold** is fine, emoji sparingly). \
When your reply specifically names a game that appears in SITE DATA with a "slug: ...", include \
that slug in game_slugs so the app can turn it into a clickable link.

Site features you can point people to when relevant: the Deals page, the Free Games page, \
Compare (side-by-side prices across stores + price history charts), and Wishlist (save games, \
get emailed when the price drops to a target — requires login).

Respond with ONLY a JSON object, no other text before or after it:
{"reply": "<your conversational reply>", "game_slugs": ["slug-of-a-game-you-named", ...]}
game_slugs lists, in the order they matter, the slugs of games your reply specifically names \
that appear in SITE DATA. Use [] if you didn't name any."""


def _slugs_to_links(slugs):
    links = []
    for slug in (slugs or [])[:5]:
        game = Game.query.filter_by(slug=slug).first()
        if game:
            links.append({"label": game.title, "url": url_for("main.game_details", slug=game.slug)})
    return links


def _ai_reply(user_msg, history):
    context = _build_context()

    messages = []
    for turn in (history or [])[-MAX_HISTORY_TURNS * 2:]:
        role = "assistant" if turn.get("role") == "bot" else "user"
        text = (turn.get("text") or "").strip()
        if text:
            messages.append({"role": role, "content": text})

    messages.append({
        "role": "user",
        "content": f"SITE DATA (fresh from the database, use only this for facts/prices):\n{context}\n\nUSER MESSAGE: {user_msg}",
    })
    # Claude requires the message list to start with a "user" turn.
    if messages and messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": "(conversation continues)"})

    resp = _client.messages.create(
        model=AI_MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    raw = "".join(
        block.text for block in resp.content if getattr(block, "type", "") == "text"
    ).strip()

    cleaned = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
        reply = parsed.get("reply") or "Hmm, I didn't quite catch that — could you rephrase?"
        links = _slugs_to_links(parsed.get("game_slugs"))
    except (json.JSONDecodeError, AttributeError, TypeError):
        # Model didn't return clean JSON — still show whatever text it gave, just with no links.
        reply = raw or "Hmm, I didn't quite catch that — could you rephrase?"
        links = []

    return reply, links


# ─── rule-based fallback — used only when no ANTHROPIC_API_KEY is configured ─
# (Kept so the project still runs with zero setup / no API key.)

def _fb_game_link(game):
    try:
        url = url_for("main.game_details", slug=game.slug)
    except Exception:
        url = "#"
    return {"label": game.title, "url": url}


def _fb_greeting():
    reply = (
        "👋 Hey there! I'm **Vault**. Ask me about deals, free games, trending titles, "
        "or type a game name to look it up!"
    )
    links = [
        {"label": "🔥 Browse Deals", "url": url_for("deals.index")},
        {"label": "🆓 Free Games", "url": url_for("deals.free_games")},
    ]
    return reply, links


def _fb_deals():
    top = (
        GamePlatform.query
        .filter(GamePlatform.discount_percent > 0, GamePlatform.current_price.isnot(None))
        .order_by(GamePlatform.discount_percent.desc())
        .limit(5)
        .all()
    )
    if not top:
        return (
            "I couldn't find any live discount data right now — try the Deals page!",
            [{"label": "Deals page", "url": url_for("deals.index")}],
        )
    lines = ["🔥 **Hottest deals right now:**\n"]
    link_list = []
    for gp in top:
        game = Game.query.get(gp.game_id)
        if not game:
            continue
        lines.append(
            f"• **{game.title}** — ~~{_format_price(gp.original_price)}~~ → "
            f"**{_format_price(gp.current_price)}** (-{gp.discount_percent}%)"
        )
        link_list.append(_fb_game_link(game))
    link_list.append({"label": "All Deals →", "url": url_for("deals.index")})
    return "\n".join(lines), link_list


def _fb_free():
    f2p = Game.query.filter_by(is_free_to_play=True).order_by(Game.popularity_score.desc()).limit(5).all()
    if not f2p:
        return (
            "No free games tracked right now — check the Free Games page, it updates regularly!",
            [{"label": "🆓 Free Games", "url": url_for("deals.free_games")}],
        )
    lines = ["🆓 **Free games you can grab right now:**\n"] + [f"• **{g.title}**" for g in f2p]
    link_list = [_fb_game_link(g) for g in f2p]
    return "\n".join(lines), link_list


def _fb_trending():
    games = Game.query.order_by(Game.popularity_score.desc()).limit(5).all()
    lines = ["📈 **Trending on GameVault:**\n"] + [f"{i}. **{g.title}**" for i, g in enumerate(games, 1)]
    return "\n".join(lines), [_fb_game_link(g) for g in games]


def _fb_search(query):
    results = Game.query.filter(Game.title.ilike(f"%{query}%")).limit(5).all()
    if not results:
        return f"I couldn't find any game matching **\"{query}\"**.", []
    lines = [f"🔍 **Results for \"{query}\":**\n"] + [f"• **{g.title}**" for g in results]
    return "\n".join(lines), [_fb_game_link(g) for g in results]


def _fb_fallback():
    reply = (
        "🤖 Not sure I understood — try **deals**, **free**, **trending**, "
        "**find `<game name>`**, or **help**."
    )
    return reply, [{"label": "🏠 Home", "url": url_for("main.home")}]


def _fallback_reply(user_msg):
    low = user_msg.lower().strip()
    if any(w in low for w in ("hi", "hello", "hey", "help")):
        return _fb_greeting()
    if any(w in low for w in ("deal", "discount", "sale", "cheap")):
        return _fb_deals()
    if any(w in low for w in ("free", "giveaway", "f2p")):
        return _fb_free()
    if any(w in low for w in ("trend", "popular", "top")):
        return _fb_trending()
    if low.startswith(("find ", "search ", "look up ", "show me ")):
        for prefix in ("find ", "search ", "look up ", "show me "):
            if low.startswith(prefix):
                return _fb_search(low[len(prefix):].strip())
    if len(low.split()) <= 6 and not any(c in low for c in "?!.,"):
        return _fb_search(low)
    return _fb_fallback()


# ─── main endpoint ────────────────────────────────────────────────────────────

@assistant_bp.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    history = data.get("history") or []

    if not user_msg:
        return jsonify({"reply": "Please type a message!", "links": []})

    try:
        if _client is not None:
            reply, links = _ai_reply(user_msg, history)
        else:
            reply, links = _fallback_reply(user_msg)
    except Exception:
        # AI call failed (bad key, network, rate limit, etc.) — degrade gracefully
        # instead of showing the user an error.
        try:
            reply, links = _fallback_reply(user_msg)
        except Exception:
            reply, links = (
                "⚠️ Something went wrong on my end — sorry! Try browsing the site directly.",
                [],
            )

    return jsonify({"reply": reply, "links": links})
