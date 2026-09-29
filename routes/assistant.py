"""
GameVault Assistant — "Vault" 2.0
Next-generation AI & NLP assistant for game price comparisons, deals, and recommendations.

Supports:
1. Multi-LLM API Providers (Google Gemini, Claude Anthropic, OpenAI) with automatic fallback.
2. Intelligent Offline NLP Engine (Price filters, Genre/Tag searches, Game Comparisons, Wishlists, Store deals, Top Rated, Recommendations).
3. Rich Interactive Game Cards payload with verified live store prices, discounts, ratings, and instant store links.
"""

import json
import os
import re
import random
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify, url_for, session
from flask_login import current_user
from sqlalchemy import or_, func

from models import Game, GamePlatform, Platform, Category, Deal, Wishlist, GameAlias, PriceHistory
from extensions import db

assistant_bp = Blueprint("assistant", __name__)

# Try Anthropic SDK if installed
try:
    import anthropic
except ImportError:
    anthropic = None

# API Keys & model configuration
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", "")).strip()
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "").strip()

AI_MODEL_CLAUDE = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
AI_MODEL_GEMINI = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
AI_MODEL_OPENAI = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

_anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if (anthropic and ANTHROPIC_KEY) else None
MAX_HISTORY_TURNS = 6


# ─── Game Card Serialization Helpers ──────────────────────────────────────────

def _format_price(price):
    if price is None:
        return "N/A"
    if price == 0:
        return "FREE"
    return f"${price:.2f}"


def _get_game_card_data(game, specific_listing=None):
    """Serialize game into a rich interactive card object for the frontend."""
    if not game:
        return None

    listing = specific_listing or game.best_price
    current_price = None
    original_price = None
    discount = 0
    store_name = "Official Store"
    store_url = url_for("main.game_details", slug=game.slug)
    store_color = "#00f5ff"

    if game.is_free_to_play:
        current_price = 0.0
        original_price = 0.0
        discount = 100
        store_name = "Free-to-Play"
    elif listing:
        current_price = listing.current_price
        original_price = listing.original_price
        discount = listing.discount_percent or 0
        if listing.platform:
            store_name = listing.platform.name
            store_color = getattr(listing.platform, "brand_color", "#00f5ff") or "#00f5ff"
            if listing.store_url and listing.store_url != "#":
                store_url = listing.store_url

    # Check verified best edition offer
    best_off = game.best_offer
    if best_off and not game.is_free_to_play:
        b_list, b_ed = best_off
        if b_ed.current_price is not None:
            current_price = b_ed.current_price
            original_price = b_ed.original_price
            discount = b_ed.discount_percent or 0
            if b_list.platform:
                store_name = b_list.platform.name
                store_color = getattr(b_list.platform, "brand_color", "#00f5ff") or "#00f5ff"
            if b_ed.purchase_url:
                store_url = b_ed.purchase_url

    # Calculate savings if discounted
    savings = None
    if original_price and current_price is not None and original_price > current_price:
        savings = round(original_price - current_price, 2)

    tags = [t.strip() for t in (game.tags or "").split(",") if t.strip()][:3]

    return {
        "id": game.id,
        "title": game.title,
        "slug": game.slug,
        "image": game.display_image,
        "current_price": current_price,
        "original_price": original_price,
        "formatted_price": _format_price(current_price),
        "formatted_original_price": _format_price(original_price) if original_price else None,
        "discount_percent": discount,
        "savings": savings,
        "store": store_name,
        "store_color": store_color,
        "store_url": store_url,
        "details_url": url_for("main.game_details", slug=game.slug),
        "rating": round(game.rating, 1) if game.rating else None,
        "metacritic": game.metacritic_score,
        "is_free": bool(game.is_free_to_play or current_price == 0),
        "tags": tags,
    }


def _game_text_summary(game, listing=None):
    """Plain text description for grounding LLM prompts."""
    card = _get_game_card_data(game, listing)
    if not card:
        return ""
    p_str = "Free-to-play" if card["is_free"] else f"{card['formatted_price']} on {card['store']}"
    if card["discount_percent"]:
        p_str += f" (-{card['discount_percent']}%)"
    meta = f", Metacritic: {game.metacritic_score}" if game.metacritic_score else ""
    return f"- {game.title} (slug: {game.slug}) — {p_str}, rating {game.rating:.1f}/5{meta}"


# ─── Dynamic Live Grounding Context ──────────────────────────────────────────

def _build_context(user_query=""):
    """Fetch live deals, free games, user wishlist, and any game matching user query."""
    top_deals = (
        GamePlatform.query
        .filter(GamePlatform.discount_percent > 0, GamePlatform.current_price.isnot(None))
        .order_by(GamePlatform.discount_percent.desc())
        .limit(10)
        .all()
    )
    deal_lines = []
    for gp in top_deals:
        g = Game.query.get(gp.game_id)
        if g:
            deal_lines.append(_game_text_summary(g, gp))

    free_games = Game.query.filter_by(is_free_to_play=True).limit(6).all()
    free_deals = (
        Deal.query.filter(Deal.deal_type.in_(["free", "giveaway", "weekend_ftp"]))
        .order_by(Deal.created_at.desc()).limit(6).all()
    )
    free_lines = [_game_text_summary(g) for g in free_games]
    for d in free_deals:
        g = Game.query.get(d.game_id)
        if g and _game_text_summary(g) not in free_lines:
            free_lines.append(_game_text_summary(g))

    trending = Game.query.order_by(Game.popularity_score.desc()).limit(8).all()
    trending_lines = [_game_text_summary(g) for g in trending]

    # Dynamically search DB for games matching query tokens
    query_matches = []
    if user_query:
        tokens = [t.strip() for t in re.findall(r"[a-zA-Z0-9]{3,}", user_query)]
        if tokens:
            filters = []
            for tok in tokens[:4]:
                filters.append(Game.title.ilike(f"%{tok}%"))
                filters.append(Game.tags.ilike(f"%{tok}%"))
            matched_games = Game.query.filter(or_(*filters)).limit(6).all()
            for g in matched_games:
                query_matches.append(_game_text_summary(g))

    parts = [
        "TOP DISCOUNTS RIGHT NOW:\n" + ("\n".join(deal_lines) or "none tracked right now"),
        "FREE GAMES RIGHT NOW:\n" + ("\n".join(free_lines) or "none tracked right now"),
        "TRENDING GAMES:\n" + ("\n".join(trending_lines) or "none tracked right now"),
    ]

    if query_matches:
        parts.append("RELEVANT GAMES SEARCHED FROM DATABASE:\n" + "\n".join(query_matches))

    if current_user.is_authenticated:
        items = Wishlist.query.filter_by(user_id=current_user.id).limit(10).all()
        wishlist_lines = []
        for w in items:
            g = Game.query.get(w.game_id)
            if g:
                wishlist_lines.append(_game_text_summary(g))
        parts.append(
            f"LOGGED-IN USER: {current_user.username}\nTHEIR WISHLIST:\n"
            + ("\n".join(wishlist_lines) or "empty wishlist")
        )
    else:
        parts.append("USER IS NOT LOGGED IN (no wishlist).")

    return "\n\n".join(parts)


SYSTEM_PROMPT = """You are Vault, the witty, knowledgeable and super-helpful assistant for GameVault, a modern game price tracker and deal aggregator (covering Steam, Epic Games, GOG, Xbox, PlayStation, and more).

Ground every price, game title, and discount ONLY in the SITE DATA provided each turn. Never invent or hallucinate games, prices, or store links that do not exist in SITE DATA. If a game is not found, state that politely and suggest browsing the Deals or Compare pages.

Guidelines:
1. Provide concise, friendly answers (2-4 sentences max).
2. Use markdown formatting (**bold** for emphasis, lists where appropriate).
3. If you mention or recommend games that appear in SITE DATA with 'slug: <slug>', put those exact slugs into the `game_slugs` JSON array.
4. Include 2-4 helpful follow-up suggestion chips in `suggested_prompts`.

Respond with ONLY a valid JSON object matching this schema:
{
  "reply": "<your friendly markdown response>",
  "game_slugs": ["slug1", "slug2"],
  "suggested_prompts": ["🔥 More Deals", "💰 Games Under $10", "⭐ Top Rated"]
}"""


# ─── LLM Providers Integration ───────────────────────────────────────────────

def _call_claude(user_msg, history, context):
    messages = []
    for turn in (history or [])[-MAX_HISTORY_TURNS * 2:]:
        role = "assistant" if turn.get("role") == "bot" else "user"
        text = (turn.get("text") or "").strip()
        if text:
            messages.append({"role": role, "content": text})

    messages.append({
        "role": "user",
        "content": f"SITE DATA:\n{context}\n\nUSER MESSAGE: {user_msg}",
    })
    if messages and messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": "Let's explore game deals."})

    resp = _anthropic_client.messages.create(
        model=AI_MODEL_CLAUDE,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    raw = "".join(
        block.text for block in resp.content if getattr(block, "type", "") == "text"
    ).strip()
    return raw


def _call_gemini(user_msg, history, context):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{AI_MODEL_GEMINI}:generateContent?key={GEMINI_KEY}"
    
    contents = []
    for turn in (history or [])[-MAX_HISTORY_TURNS * 2:]:
        role = "model" if turn.get("role") == "bot" else "user"
        text = (turn.get("text") or "").strip()
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})

    prompt_text = f"{SYSTEM_PROMPT}\n\nSITE DATA:\n{context}\n\nUSER MESSAGE: {user_msg}"
    contents.append({"role": "user", "parts": [{"text": prompt_text}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 600,
            "responseMimeType": "application/json"
        }
    }
    res = requests.post(url, json=payload, timeout=8)
    if res.status_code != 200:
        raise RuntimeError(f"Gemini API error ({res.status_code}): {res.text}")
    data = res.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Empty response from Gemini")
    text = candidates[0]["content"]["parts"][0]["text"]
    return text.strip()


def _call_openai(user_msg, history, context):
    url = "https://api.openai.com/v1/chat/completions"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-MAX_HISTORY_TURNS * 2:]:
        role = "assistant" if turn.get("role") == "bot" else "user"
        text = (turn.get("text") or "").strip()
        if text:
            messages.append({"role": role, "content": text})

    messages.append({
        "role": "user",
        "content": f"SITE DATA:\n{context}\n\nUSER MESSAGE: {user_msg}",
    })

    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": AI_MODEL_OPENAI,
        "messages": messages,
        "max_tokens": 600,
        "response_format": {"type": "json_object"}
    }
    res = requests.post(url, json=payload, headers=headers, timeout=8)
    if res.status_code != 200:
        raise RuntimeError(f"OpenAI API error ({res.status_code}): {res.text}")
    data = res.json()
    return data["choices"][0]["message"]["content"].strip()


def _ai_reply(user_msg, history):
    context = _build_context(user_msg)
    raw = None

    # Try Gemini first if key available, then Claude, then OpenAI
    if GEMINI_KEY:
        try:
            raw = _call_gemini(user_msg, history, context)
        except Exception:
            raw = None

    if not raw and _anthropic_client:
        try:
            raw = _call_claude(user_msg, history, context)
        except Exception:
            raw = None

    if not raw and OPENAI_KEY:
        try:
            raw = _call_openai(user_msg, history, context)
        except Exception:
            raw = None

    if not raw:
        # Fall back to smart offline parser
        return _smart_nlp_reply(user_msg)

    cleaned = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
        reply = parsed.get("reply") or "Here is what I found for you on GameVault:"
        slugs = parsed.get("game_slugs") or []
        prompts = parsed.get("suggested_prompts") or ["🔥 Top Deals", "🆓 Free Games", "💰 Under $10", "⭐ Top Rated"]
        
        games_data = []
        links = []
        for slug in slugs[:6]:
            g = Game.query.filter_by(slug=slug).first()
            if g:
                cdata = _get_game_card_data(g)
                if cdata:
                    games_data.append(cdata)
                links.append({"label": g.title, "url": url_for("main.game_details", slug=g.slug)})

        return {
            "reply": reply,
            "games": games_data,
            "links": links,
            "suggested_prompts": prompts,
            "source": "ai"
        }
    except Exception:
        # Parsing failed, return raw or fallback
        return {
            "reply": raw,
            "games": [],
            "links": [],
            "suggested_prompts": ["🔥 Top Deals", "🆓 Free Games", "💰 Under $10"],
            "source": "ai_raw"
        }


# ─── Intelligent Offline NLP & Query Engine ───────────────────────────────────

def _smart_nlp_reply(user_msg):
    """High-intelligence rule-based + database query engine.
    Handles price thresholds, game comparisons, genre searches, wishlists, store filters, and recommendations with zero external API calls.
    """
    raw = user_msg.strip()
    low = raw.lower()

    # 1. Price budget filter (e.g. "under $10", "games below 5", "less than 20 dollars", "budget games under 15")
    price_match = re.search(r"(?:under|below|less than|within|budget of)\s+\$?(\d+(?:\.\d+)?)", low)
    if not price_match and ("cheap" in low or "budget" in low or "under" in low or "below" in low):
        price_match = re.search(r"\$?(\d+(?:\.\d+)?)", low)

    is_budget_query = (
        price_match is not None
        or ("cheap" in low and not any(w in low for w in ["store", "compare", "vs"]))
        or (any(w in low for w in ["under", "below"]) and not any(w in low for w in ["compare", "vs"]))
    )

    if is_budget_query:
        max_price = float(price_match.group(1)) if (price_match and price_match.group(1)) else 10.0
        listings = (
            GamePlatform.query
            .filter(GamePlatform.current_price.isnot(None), GamePlatform.current_price <= max_price, GamePlatform.current_price > 0)
            .order_by(GamePlatform.discount_percent.desc(), GamePlatform.current_price.asc())
            .limit(6)
            .all()
        )
        if listings:
            games_data = []
            links = []
            lines = [f"💰 **Top games & deals under {_format_price(max_price)}:**\n"]
            for gp in listings:
                g = Game.query.get(gp.game_id)
                if g and g.id not in [x["id"] for x in games_data]:
                    cdata = _get_game_card_data(g, gp)
                    games_data.append(cdata)
                    links.append({"label": g.title, "url": cdata["details_url"]})
                    lines.append(f"• **{g.title}** — **{cdata['formatted_price']}** on {cdata['store']} (-{cdata['discount_percent']}%)")
            
            lines.append(f"\nFound {len(games_data)} hot titles in your budget!")
            return {
                "reply": "\n".join(lines),
                "games": games_data,
                "links": links,
                "suggested_prompts": ["💰 Under $10", "🔥 Top Deals", "🆓 Free Games", "⭐ Top Rated"],
                "source": "nlp_budget"
            }
        else:
            cheapest = (
                GamePlatform.query
                .filter(GamePlatform.current_price.isnot(None), GamePlatform.current_price > 0)
                .order_by(GamePlatform.current_price.asc())
                .limit(4)
                .all()
            )
            games_data = []
            links = []
            lines = [f"💰 No deals strictly under {_format_price(max_price)} right now, but here are our cheapest available games:\n"]
            for gp in cheapest:
                g = Game.query.get(gp.game_id)
                if g and g.id not in [x["id"] for x in games_data]:
                    cdata = _get_game_card_data(g, gp)
                    games_data.append(cdata)
                    links.append({"label": g.title, "url": cdata["details_url"]})
                    lines.append(f"• **{g.title}** — **{cdata['formatted_price']}** on {cdata['store']}")
            return {
                "reply": "\n".join(lines),
                "games": games_data,
                "links": links,
                "suggested_prompts": ["🔥 Top Deals", "🆓 Free Games", "💰 Under $10"],
                "source": "nlp_budget_fallback"
            }

    # 2. Game Comparison (e.g. "compare Cyberpunk and Witcher 3", "Elden Ring vs Sekiro")
    comp_match = re.search(r"(?:compare\s+)?(.+?)\s+(?:vs\.?|and|versus|with)\s+(.+)", low)
    if comp_match and ("compare" in low or " vs " in low or " vs. " in low or " versus " in low):
        g1_str = comp_match.group(1).replace("compare", "").strip()
        g2_str = comp_match.group(2).strip()

        # Search both games
        g1 = Game.query.filter(Game.title.ilike(f"%{g1_str}%")).first()
        g2 = Game.query.filter(Game.title.ilike(f"%{g2_str}%")).first()

        if g1 and g2:
            c1 = _get_game_card_data(g1)
            c2 = _get_game_card_data(g2)
            
            lines = [f"⚔️ **Comparison: {g1.title} vs {g2.title}**\n"]
            lines.append(f"• **{g1.title}**: {c1['formatted_price']} ({c1['store']}) | Rating: ⭐ {g1.rating:.1f}/5 | Metacritic: {g1.metacritic_score or 'N/A'}")
            lines.append(f"• **{g2.title}**: {c2['formatted_price']} ({c2['store']}) | Rating: ⭐ {g2.rating:.1f}/5 | Metacritic: {g2.metacritic_score or 'N/A'}")
            
            # Winner assessment
            if c1["current_price"] is not None and c2["current_price"] is not None:
                if c1["current_price"] < c2["current_price"]:
                    lines.append(f"\n💡 **Value Pick**: **{g1.title}** is currently ${_format_price(c2['current_price'] - c1['current_price'])} cheaper!")
                elif c2["current_price"] < c1["current_price"]:
                    lines.append(f"\n💡 **Value Pick**: **{g2.title}** is currently ${_format_price(c1['current_price'] - c2['current_price'])} cheaper!")
                else:
                    lines.append("\n💡 Both games are priced identically right now!")

            return {
                "reply": "\n".join(lines),
                "games": [c1, c2],
                "links": [
                    {"label": f"Compare {g1.title} & {g2.title}", "url": f"/compare?g1={g1.id}&g2={g2.id}"},
                    {"label": g1.title, "url": c1["details_url"]},
                    {"label": g2.title, "url": c2["details_url"]}
                ],
                "suggested_prompts": ["🔥 Top Deals", "⭐ Top Rated", "🎲 Surprise Me"],
                "source": "nlp_compare"
            }

    # 3. Store-specific deals (e.g. "Steam deals", "Epic deals", "GOG sales", "PlayStation discounts", "Xbox")
    store_keywords = {
        "steam": "Steam",
        "epic": "Epic Games",
        "gog": "GOG",
        "xbox": "Xbox Store",
        "playstation": "PlayStation Store",
        "ps5": "PlayStation Store",
        "ps4": "PlayStation Store",
        "nintendo": "Nintendo eShop"
    }
    for key, store_name in store_keywords.items():
        if key in low and any(w in low for w in ["deal", "sale", "discount", "price", "store", "game"]):
            platform = Platform.query.filter(Platform.name.ilike(f"%{key}%")).first()
            if platform:
                listings = (
                    GamePlatform.query
                    .filter_by(platform_id=platform.id)
                    .filter(GamePlatform.discount_percent > 0, GamePlatform.current_price.isnot(None))
                    .order_by(GamePlatform.discount_percent.desc())
                    .limit(5)
                    .all()
                )
                if listings:
                    games_data = []
                    links = []
                    lines = [f"🏷️ **Top Deals on {platform.name}:**\n"]
                    for gp in listings:
                        g = Game.query.get(gp.game_id)
                        if g:
                            cdata = _get_game_card_data(g, gp)
                            games_data.append(cdata)
                            links.append({"label": g.title, "url": cdata["details_url"]})
                            lines.append(f"• **{g.title}** — **{cdata['formatted_price']}** (-{cdata['discount_percent']}%)")
                    return {
                        "reply": "\n".join(lines),
                        "games": games_data,
                        "links": links,
                        "suggested_prompts": ["🔥 All Deals", "🆓 Free Games", "💰 Under $10"],
                        "source": "nlp_store"
                    }

    # 4. Genre / Category exploration (e.g. "RPG games", "action games", "horror", "multiplayer", "open world", "indie", "strategy")
    genre_keywords = [
        "rpg", "action", "horror", "racing", "strategy", "adventure", "shooter",
        "fps", "open world", "indie", "co-op", "multiplayer", "sports", "simulation",
        "survival", "soulslike", "anime", "stealth", "puzzle"
    ]
    for genre in genre_keywords:
        if genre in low:
            matched_games = (
                Game.query
                .filter(or_(Game.tags.ilike(f"%{genre}%"), Game.description.ilike(f"%{genre}%")))
                .order_by(Game.popularity_score.desc())
                .limit(5)
                .all()
            )
            if matched_games:
                games_data = [_get_game_card_data(g) for g in matched_games if _get_game_card_data(g)]
                links = [{"label": g.title, "url": url_for("main.game_details", slug=g.slug)} for g in matched_games]
                lines = [f"🎮 **Top {genre.upper()} games on GameVault:**\n"]
                for g, cdata in zip(matched_games, games_data):
                    lines.append(f"• **{g.title}** — {cdata['formatted_price']} (⭐ {g.rating:.1f}/5)")
                return {
                    "reply": "\n".join(lines),
                    "games": games_data,
                    "links": links,
                    "suggested_prompts": [f"🔥 Top {genre.title()} Deals", "💰 Under $15", "⭐ Top Rated", "🎲 Surprise Me"],
                    "source": "nlp_genre"
                }

    # 5. User Wishlist queries (e.g. "what is on my wishlist", "my wishlist", "check wishlist")
    if any(w in low for w in ["wishlist", "my list", "saved games", "watch list"]):
        if not current_user.is_authenticated:
            return {
                "reply": "🔒 **You're not logged in!**\nLog in or create a GameVault account to save games to your wishlist and receive automated price drop alerts directly to your inbox.",
                "games": [],
                "links": [
                    {"label": "🔑 Log In", "url": url_for("auth.login")},
                    {"label": "✨ Sign Up", "url": url_for("auth.register")},
                ],
                "suggested_prompts": ["🔥 Top Deals", "🆓 Free Games", "⭐ Top Rated"],
                "source": "nlp_wishlist_unauth"
            }
        
        items = Wishlist.query.filter_by(user_id=current_user.id).all()
        if not items:
            return {
                "reply": f"📋 Hey **{current_user.username}**, your wishlist is currently empty! Click the bookmark icon on any game page to track prices.",
                "games": [],
                "links": [{"label": "🔥 Explore Top Deals", "url": url_for("deals.index")}],
                "suggested_prompts": ["🔥 Top Deals", "🆓 Free Games", "💰 Under $10"],
                "source": "nlp_wishlist_empty"
            }

        wishlist_games = []
        on_sale_count = 0
        lines = [f"🎯 **Your Wishlist ({len(items)} games tracked):**\n"]
        for w in items[:5]:
            g = Game.query.get(w.game_id)
            if g:
                cdata = _get_game_card_data(g)
                wishlist_games.append(cdata)
                if cdata["discount_percent"] > 0:
                    on_sale_count += 1
                    lines.append(f"• **{g.title}** — 🔥 **ON SALE**: {cdata['formatted_price']} (-{cdata['discount_percent']}%) on {cdata['store']}")
                else:
                    lines.append(f"• **{g.title}** — {cdata['formatted_price']} on {cdata['store']}")

        if on_sale_count > 0:
            lines.append(f"\n🎉 **Great news!** {on_sale_count} title(s) on your wishlist have active discounts right now.")

        return {
            "reply": "\n".join(lines),
            "games": wishlist_games,
            "links": [{"label": "View Full Wishlist", "url": url_for("wishlist.index")}],
            "suggested_prompts": ["🔥 Top Deals", "🆓 Free Games", "⭐ Top Rated"],
            "source": "nlp_wishlist"
        }

    # 6. Top Rated / Metacritic high scores (e.g. "top rated", "highest rating", "best games", "metacritic 90")
    if any(w in low for w in ["top rated", "highest rated", "best rated", "metacritic", "critics", "hall of fame", "masterpiece"]):
        top_rated = (
            Game.query
            .filter(or_(Game.metacritic_score >= 85, Game.rating >= 4.5))
            .order_by(Game.rating.desc(), Game.metacritic_score.desc())
            .limit(5)
            .all()
        )
        if top_rated:
            games_data = [_get_game_card_data(g) for g in top_rated]
            lines = ["⭐ **Highest-Rated Masterpieces on GameVault:**\n"]
            for g, cdata in zip(top_rated, games_data):
                meta_str = f" | Metacritic: {g.metacritic_score}" if g.metacritic_score else ""
                lines.append(f"• **{g.title}** — ⭐ {g.rating:.1f}/5{meta_str} — {cdata['formatted_price']}")
            return {
                "reply": "\n".join(lines),
                "games": games_data,
                "links": [{"label": g.title, "url": cdata["details_url"]} for g, cdata in zip(top_rated, games_data)],
                "suggested_prompts": ["🔥 Top Deals", "💰 Under $10", "🎲 Surprise Me"],
                "source": "nlp_top_rated"
            }

    # 7. Free games / Giveaways (e.g. "free games", "freebies", "giveaways", "f2p", "free")
    if any(w in low for w in ["free", "giveaway", "f2p", "zero cost", "100% off"]):
        f2p_games = Game.query.filter_by(is_free_to_play=True).order_by(Game.popularity_score.desc()).limit(5).all()
        giveaway_deals = (
            Deal.query.filter(Deal.deal_type.in_(["free", "giveaway", "weekend_ftp"]))
            .order_by(Deal.created_at.desc()).limit(4).all()
        )
        combined_games = list(f2p_games)
        for d in giveaway_deals:
            g = Game.query.get(d.game_id)
            if g and g not in combined_games:
                combined_games.append(g)

        if combined_games:
            games_data = [_get_game_card_data(g) for g in combined_games[:5]]
            lines = ["🆓 **Free games and giveaways you can claim right now:**\n"]
            for g, cdata in zip(combined_games[:5], games_data):
                lines.append(f"• **{g.title}** — 🎁 {cdata['formatted_price']} ({cdata['store']})")
            return {
                "reply": "\n".join(lines),
                "games": games_data,
                "links": [
                    {"label": "🆓 Free Games Hub", "url": url_for("deals.free_games")},
                    {"label": "🔥 All Deals", "url": url_for("deals.index")}
                ],
                "suggested_prompts": ["🔥 Best Deals", "💰 Under $10", "⭐ Top Rated"],
                "source": "nlp_free"
            }

    # 8. Random recommendation / Surprise me
    if any(w in low for w in ["recommend", "surprise me", "random", "what should i play", "suggest a game", "pick a game"]):
        candidates = (
            Game.query
            .filter(Game.rating >= 4.0)
            .order_by(func.random())
            .limit(3)
            .all()
        )
        if candidates:
            games_data = [_get_game_card_data(g) for g in candidates]
            pick = candidates[0]
            cdata = games_data[0]
            reply = (
                f"🎲 **Vault's Hand-Picked Recommendation:**\n\n"
                f"You should check out **{pick.title}**! Rated ⭐ **{pick.rating:.1f}/5** "
                f"and currently priced at **{cdata['formatted_price']}** on {cdata['store']}."
            )
            return {
                "reply": reply,
                "games": games_data[:2],
                "links": [{"label": f"View {pick.title}", "url": cdata["details_url"]}],
                "suggested_prompts": ["🎲 Another Recommendation", "🔥 Top Deals", "💰 Under $10", "⭐ Top Rated"],
                "source": "nlp_recommend"
            }

    # 9. Top Deals / General Discounts
    if any(w in low for w in ["deal", "discount", "sale", "save", "offer", "bargain", "promo"]):
        top = (
            GamePlatform.query
            .filter(GamePlatform.discount_percent > 0, GamePlatform.current_price.isnot(None))
            .order_by(GamePlatform.discount_percent.desc())
            .limit(5)
            .all()
        )
        if top:
            games_data = []
            links = []
            lines = ["🔥 **Hottest verified discounts right now:**\n"]
            for gp in top:
                g = Game.query.get(gp.game_id)
                if g and g.id not in [x["id"] for x in games_data]:
                    cdata = _get_game_card_data(g, gp)
                    games_data.append(cdata)
                    links.append({"label": g.title, "url": cdata["details_url"]})
                    lines.append(f"• **{g.title}** — ~~{cdata['formatted_original_price']}~~ → **{cdata['formatted_price']}** (-{cdata['discount_percent']}%)")
            
            return {
                "reply": "\n".join(lines),
                "games": games_data,
                "links": links + [{"label": "All Deals →", "url": url_for("deals.index")}],
                "suggested_prompts": ["💰 Under $10", "🆓 Free Games", "⭐ Top Rated", "🎲 Surprise Me"],
                "source": "nlp_deals"
            }

    # 10. Trending / Popular
    if any(w in low for w in ["trend", "popular", "hot", "what is everyone playing"]):
        trending = Game.query.order_by(Game.popularity_score.desc()).limit(5).all()
        games_data = [_get_game_card_data(g) for g in trending]
        lines = ["📈 **Trending on GameVault:**\n"]
        for i, (g, cdata) in enumerate(zip(trending, games_data), 1):
            lines.append(f"{i}. **{g.title}** — {cdata['formatted_price']} (⭐ {g.rating:.1f}/5)")
        return {
            "reply": "\n".join(lines),
            "games": games_data,
            "links": [{"label": g.title, "url": cdata["details_url"]} for g, cdata in zip(trending, games_data)],
            "suggested_prompts": ["🔥 Top Deals", "🆓 Free Games", "💰 Under $10"],
            "source": "nlp_trending"
        }

    # 11. Search for specific game title / alias
    search_term = low
    for prefix in ["find ", "search ", "look up ", "show me ", "price of ", "how much is ", "is "]:
        if search_term.startswith(prefix):
            search_term = search_term[len(prefix):].strip()
            break
    search_term = search_term.rstrip("?!.,")

    if search_term and len(search_term) >= 2:
        # Check title or aliases
        results = Game.query.filter(Game.title.ilike(f"%{search_term}%")).limit(4).all()
        if not results:
            alias = GameAlias.query.filter(GameAlias.alias.ilike(f"%{search_term}%")).first()
            if alias and alias.game:
                results = [alias.game]

        if results:
            games_data = [_get_game_card_data(g) for g in results]
            lines = [f"🔍 **Found {len(results)} title(s) matching \"{search_term}\":**\n"]
            for g, cdata in zip(results, games_data):
                disc = f" (-{cdata['discount_percent']}%)" if cdata['discount_percent'] else ""
                lines.append(f"• **{g.title}** — **{cdata['formatted_price']}** on {cdata['store']}{disc}")
            return {
                "reply": "\n".join(lines),
                "games": games_data,
                "links": [{"label": g.title, "url": cdata["details_url"]} for g, cdata in zip(results, games_data)],
                "suggested_prompts": ["🔥 Top Deals", "🆓 Free Games", "💰 Under $10"],
                "source": "nlp_search"
            }

    # 12. General Greetings / Help / Capabilities
    if any(w in low for w in ["hi", "hello", "hey", "help", "who are you", "what can you do", "commands"]):
        reply = (
            "👋 **Hello! I'm Vault**, your intelligent GameVault assistant.\n\n"
            "I can help you track prices, find verified game deals, and discover new titles. Here is what you can ask me:\n"
            "• **Deals**: *\"Show me top deals\"*, *\"Steam deals\"*, *\"Free games\"*\n"
            "• **Budgets**: *\"Games under $10\"*, *\"Deals below $5\"*\n"
            "• **Genres**: *\"Best RPG games\"*, *\"Action deals\"*, *\"Horror\"*\n"
            "• **Comparisons**: *\"Compare Cyberpunk and Witcher 3\"*\n"
            "• **Wishlist**: *\"What's on my wishlist?\"*\n"
            "• **Search**: *\"How much is Elden Ring?\"*"
        )
        return {
            "reply": reply,
            "games": [],
            "links": [
                {"label": "🔥 Browse Deals", "url": url_for("deals.index")},
                {"label": "🆓 Free Games", "url": url_for("deals.free_games")},
                {"label": "📊 Compare Prices", "url": url_for("main.compare")},
            ],
            "suggested_prompts": ["🔥 Top Deals", "🆓 Free Games", "💰 Under $10", "⭐ Top Rated", "🎯 My Wishlist", "🎲 Surprise Me"],
            "source": "nlp_greeting"
        }

    # Fallback response with helpful prompt suggestions
    return {
        "reply": (
            f"🤔 I couldn't find an exact match for *\"{raw}\"*. Try asking for **deals**, **free games**, "
            f"**games under $10**, **compare two games**, or search by title!"
        ),
        "games": [],
        "links": [
            {"label": "🔥 Best Deals", "url": url_for("deals.index")},
            {"label": "🔍 Search Catalog", "url": url_for("main.search")}
        ],
        "suggested_prompts": ["🔥 Top Deals", "🆓 Free Games", "💰 Under $10", "⭐ Top Rated", "🎲 Surprise Me"],
        "source": "nlp_fallback"
    }


# ─── Main Chat Endpoint ───────────────────────────────────────────────────────

@assistant_bp.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    history = data.get("history") or []

    if not user_msg:
        return jsonify({
            "reply": "Please type a message or choose one of the quick suggestions below!",
            "games": [],
            "links": [],
            "suggested_prompts": ["🔥 Top Deals", "🆓 Free Games", "💰 Under $10", "⭐ Top Rated"]
        })

    try:
        # If any AI API key is configured, use AI with grounding context, else smart NLP
        if _anthropic_client or GEMINI_KEY or OPENAI_KEY:
            res = _ai_reply(user_msg, history)
        else:
            res = _smart_nlp_reply(user_msg)
    except Exception as e:
        # Graceful fallback to offline smart engine on any exception
        try:
            res = _smart_nlp_reply(user_msg)
        except Exception:
            res = {
                "reply": "⚠️ I ran into a minor issue, but you can explore our live deals and catalog directly!",
                "games": [],
                "links": [{"label": "🔥 Deals Page", "url": url_for("deals.index")}],
                "suggested_prompts": ["🔥 Top Deals", "🆓 Free Games"],
                "source": "error_fallback"
            }

    return jsonify(res)
