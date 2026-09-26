"""
search.py
=================================================================
Powers every search box in the app (navbar live search, /compare filters,
the REST API). Combines three layers, cheapest-first:

1. EXACT / PARTIAL match on Game.title or GameAlias.alias (case-insensitive,
   SQL LIKE — fast, uses the DB index).
2. ABBREVIATION normalization — strips spaces/punctuation so "GTA V",
   "GTAV" and "gta-v" all normalize to "gtav" and match the same alias.
3. FUZZY / typo-tolerant fallback (pure Python, stdlib difflib — no extra
   dependency needed) — only runs if steps 1-2 found nothing, and only
   scores the (small, in-memory) list of game titles+aliases, which is
   fine for a catalog of hundreds/low-thousands of games. It would need
   a real search engine (Postgres full-text, Elasticsearch, Meilisearch)
   at Steam-catalog scale — noted in the README as the production-scale
   upgrade path.

This is what makes "GTAV" instantly find "Grand Theft Auto V" even though
that exact string never appears anywhere in the database.
=================================================================
"""
import difflib
import re

from models import Game, GameAlias

_PUNCT_RE = re.compile(r"[^a-z0-9]")


def normalize(text):
    """'GTA V' -> 'gtav', 'Counter-Strike 2' -> 'counterstrike2'."""
    return _PUNCT_RE.sub("", (text or "").lower())


def search_games(query, limit=10):
    """Returns a list of Game objects matching `query`, best match first.
    Handles exact/partial title match, alias match (abbreviations like
    GTA/CS2/PUBG/RDR2), and — only as a fallback — typo-tolerant fuzzy
    matching."""
    query = (query or "").strip()
    if not query:
        return []

    like = f"%{query}%"

    # --- Layer 1: direct title match ---
    title_matches = (
        Game.query.filter(Game.title.ilike(like))
        .order_by(Game.popularity_score.desc())
        .limit(limit)
        .all()
    )

    # --- Layer 2: alias match (handles GTA, GTAV, CS2, CSGO, PUBG, RDR2, COD, FC25...) ---
    normalized_query = normalize(query)
    alias_matches = []
    if normalized_query:
        candidate_aliases = GameAlias.query.filter(
            GameAlias.alias.ilike(f"%{query}%")
        ).all()
        # also check normalized form, so "gta v" / "gta-v" / "GTAV" all hit
        # the same alias row even if punctuation/spacing differs
        all_aliases = GameAlias.query.all()
        normalized_hits = [a for a in all_aliases if normalize(a.alias) == normalized_query
                            or normalized_query in normalize(a.alias)]
        for a in candidate_aliases + normalized_hits:
            if a.game and a.game not in alias_matches:
                alias_matches.append(a.game)

    combined = list(title_matches)
    for g in alias_matches:
        if g not in combined:
            combined.append(g)

    if combined:
        return combined[:limit]

    # --- Layer 3: fuzzy fallback (typo tolerance) ---
    # Only reached when nothing matched directly — e.g. "Elden Rign" (typo).
    all_games = Game.query.all()
    pool = {}
    for g in all_games:
        pool[g.title] = g
        for alias in g.alias_list:
            pool.setdefault(alias, g)

    close = difflib.get_close_matches(query, pool.keys(), n=limit, cutoff=0.6)
    fuzzy_games = []
    for name in close:
        game = pool[name]
        if game not in fuzzy_games:
            fuzzy_games.append(game)

    return fuzzy_games[:limit]


def autocomplete_suggestions(query, limit=8):
    """Lightweight version of search_games for the instant-suggestions
    dropdown — same matching logic, trimmed result set."""
    return search_games(query, limit=limit)
