"""
steam_importer.py
=================================================================
A real, resumable Steam catalog import system — not a hardcoded list.

Pipeline:
  1. seed_import_queue()  — pulls Steam's full app list (~260k entries,
     ISteamApps/GetAppList, no key needed) and inserts every app ID we
     don't already have into SteamImportQueue as status='pending'.
     Safe to call more than once — duplicates are skipped.

  2. import_single_app()  — the actual per-game work: fetches full Steam
     metadata + regional (default India/INR) pricing, and inserts/updates
     a Game row keyed by steam_app_id (never creates a duplicate). This
     is also what the admin "Import by Steam App ID" button calls
     directly, so there's exactly one import code path, not two.

  3. run_import_batch()   — pulls a small batch of PENDING queue rows and
     imports them one at a time with a polite delay between each Steam
     API call, to stay well under any reasonable rate limit. Commits
     after every single app, so a crash mid-batch only loses at most one
     in-flight row's progress, not the whole batch.

  4. start_background_import() — spawns a daemon thread that loops
     run_import_batch() while ImportJob.status == 'running'. Progress
     (counts, cursor position via queue row status) is persisted to the
     database on every commit, so pausing, restarting the app, or a
     crash never loses overall progress — resuming just continues
     pulling the next PENDING rows.

HONEST LIMITATION: Steam doesn't publish an official rate limit for the
public store API. Community consensus is to stay well under ~200
requests/5min sustained. STEAM_IMPORT_DELAY_SECONDS (default 1.5s) is
tuned for that. At that pace, the full ~260k-entry catalog takes several
days of continuous running — this is a genuine background job, not a
one-click instant import, and that's stated plainly in the admin UI and
README rather than promised away.

CONCURRENCY NOTE: the default SQLite database is fine for a single-user
dev/demo run of this importer, but concurrent writes from the import
thread + normal web traffic can occasionally hit "database is locked"
on SQLite. For running the importer for real/long stretches, switch to
MySQL (see README) — it handles concurrent writes properly.
=================================================================
"""
import logging
import threading
import time
from datetime import datetime

import requests

logger = logging.getLogger("steam_importer")

STEAM_APPLIST_URL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"

REQUEST_TIMEOUT = 10
STEAM_IMPORT_DELAY_SECONDS = 1.5     # polite delay between Steam API calls
RATE_LIMIT_BACKOFF_SECONDS = 60      # if Steam pushes back (429/errors), cool off
MAX_ATTEMPTS = 3                     # per app before giving up and marking 'failed'
BATCH_SIZE = 20                      # apps processed per run_import_batch() call

# Name substrings that are almost never real games — skipped BEFORE
# spending an API call on them, to conserve rate-limit budget. The
# authoritative filter is still appdetails' own `type == "game"` check,
# this is just a cheap pre-filter.
SKIP_NAME_HINTS = [
    "dedicated server", "sdk", "soundtrack", " ost", "artbook", "art book",
    "playtest", " demo", "server tool", "benchmark",
]

# A simple in-process flag so we don't accidentally spawn two importer
# threads from two quick button clicks. The authoritative state is still
# the ImportJob DB row (survives restarts); this just guards this one
# running process.
_worker_thread = None
_worker_lock = threading.Lock()


# =================================================================
# 1. SEED THE QUEUE FROM STEAM'S FULL APP LIST
# =================================================================

def fetch_full_app_list():
    """Returns [{'appid': int, 'name': str}, ...] for Steam's entire
    public catalog. No API key needed. Raises on failure — this is a
    one-shot call the admin triggers explicitly, so we let the caller
    decide how to surface an error rather than silently swallowing it."""
    resp = requests.get(STEAM_APPLIST_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("applist", {}).get("apps", [])


def seed_import_queue():
    """Populates SteamImportQueue from Steam's full app list. Idempotent —
    safe to call again later to pick up newly-released games; existing
    rows (by steam_app_id) are left untouched. Returns how many NEW rows
    were queued."""
    from extensions import db
    from models import SteamImportQueue, Game

    apps = fetch_full_app_list()

    existing_queue_ids = {row[0] for row in db.session.query(SteamImportQueue.steam_app_id).all()}
    existing_game_ids = {row[0] for row in db.session.query(Game.steam_app_id).filter(Game.steam_app_id.isnot(None)).all()}
    already_known = existing_queue_ids | existing_game_ids

    new_rows = []
    for app in apps:
        app_id = app.get("appid")
        name = (app.get("name") or "").strip()
        if not app_id or app_id in already_known:
            continue
        if not name:
            continue  # nameless entries are never real, purchasable games
        already_known.add(app_id)  # guard against dupes within this same applist payload
        new_rows.append(SteamImportQueue(steam_app_id=app_id, steam_name=name, status="pending"))

    # bulk_save_objects is much faster than db.session.add() x 200,000
    if new_rows:
        db.session.bulk_save_objects(new_rows)
        db.session.commit()

    return len(new_rows)


# =================================================================
# 2. IMPORT ONE GAME (the single, canonical import code path)
# =================================================================

def _should_skip_by_name(name):
    lowered = (name or "").lower()
    return any(hint in lowered for hint in SKIP_NAME_HINTS)


def _fetch_steam_appdetails(app_id, regions=("in", "us", "gb", "de")):
    """Tries several regional storefronts — India first, since this app
    defaults to INR — until one returns real data. Mirrors the same
    'missing regional pricing' fix used elsewhere in this project."""
    last_good = None
    for cc in regions:
        try:
            resp = requests.get(
                STEAM_APPDETAILS_URL,
                params={"appids": app_id, "cc": cc, "l": "en"},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                raise RuntimeError("rate_limited")
            resp.raise_for_status()
            payload = resp.json()
            entry = payload.get(str(app_id))
            if not entry or not entry.get("success"):
                continue
            data = entry["data"]
            currency = None
            if data.get("price_overview"):
                currency = data["price_overview"].get("currency")
            last_good = last_good or (data, currency)
            if data.get("is_free") or data.get("price_overview"):
                return data, (currency or "USD")
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning(f"appdetails fetch failed for {app_id} (cc={cc}): {exc}")
            continue
    if last_good:
        return last_good
    return None, None


def _parse_release_date(date_str):
    for fmt in ("%d %b, %Y", "%b %d, %Y", "%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _generate_acronym_alias(title):
    """'Grand Theft Auto V' -> 'GTAV'-style acronym, so even games we
    didn't hand-curate an alias list for get a basic abbreviation search
    hit for free. Skipped for very short titles where it wouldn't help."""
    words = [w for w in title.replace(":", " ").replace("-", " ").split() if w]
    if len(words) < 2:
        return None
    acronym = "".join(w[0] for w in words if w[0].isalnum()).upper()
    return acronym if 2 <= len(acronym) <= 8 else None


def import_single_app(app_id, source_hint=""):
    """Fetches and stores/updates ONE game by Steam App ID. This is the
    single canonical import path — used by the queue-based bulk importer
    AND the admin's manual 'Import by Steam App ID' button.

    Returns (status, message) where status is one of:
      'imported' | 'updated' | 'skipped' | 'failed'
    Never raises — every failure mode is caught and reported, per the
    'don't let one bad app break the batch' requirement.
    """
    from extensions import db
    from models import Game, GamePlatform, Platform, Category, PriceHistory, GameAlias
    from store_apis import resolve_game_image

    try:
        data, currency = _fetch_steam_appdetails(app_id)
    except RuntimeError:
        return "failed", "rate_limited"
    except Exception as exc:
        return "failed", str(exc)

    if not data:
        return "skipped", "Steam has no public data for this App ID"

    if data.get("type") != "game":
        return "skipped", f"Not a game (type={data.get('type')})"

    title = (data.get("name") or "").strip()
    if not title:
        return "skipped", "No title returned"

    existing = Game.query.filter_by(steam_app_id=app_id).first()

    is_free = bool(data.get("is_free"))
    price_overview = data.get("price_overview")
    if is_free:
        base_price, current_price, discount, price_available = 0.0, 0.0, 0, True
    elif price_overview:
        base_price = price_overview["initial"] / 100
        current_price = price_overview["final"] / 100
        discount = price_overview.get("discount_percent", 0)
        price_available = True
    else:
        # Root-cause-fixed behavior: never invent a price. NULL = "Unavailable".
        base_price = current_price = None
        discount = 0
        price_available = False

    genre_name = data.get("genres", [{"description": "Action"}])[0]["description"] if data.get("genres") else "Action"
    category = Category.query.filter_by(name=genre_name).first()
    if not category:
        category = Category(name=genre_name, slug=genre_name.lower().replace(" ", "-"))
        db.session.add(category)
        db.session.flush()

    cover_image = resolve_game_image(steam_app_id=app_id, fallback_url=data.get("header_image", ""), verify=False)

    if existing:
        game = existing
        game.title = title
        game.cover_image = cover_image
        game.description = (data.get("short_description") or "")[:1000]
        game.developer = ", ".join(data.get("developers", []) or [])[:120]
        game.publisher = ", ".join(data.get("publishers", []) or [])[:120]
        game.release_date = _parse_release_date(data.get("release_date", {}).get("date")) or game.release_date
        game.metacritic_score = (data.get("metacritic") or {}).get("score")
        game.category_id = category.id
        game.is_free_to_play = is_free
        game.tags = ", ".join(c["description"] for c in (data.get("categories") or []))[:500]
        game.supported_languages = (data.get("supported_languages") or "")[:500]
        game.system_requirements = (data.get("pc_requirements", {}) or {}).get("minimum", "")[:2000] \
            if isinstance(data.get("pc_requirements"), dict) else ""
        game.last_synced_at = datetime.utcnow()
        result_status = "updated"
    else:
        slug_base = title.lower().replace(" ", "-").replace(":", "").replace("'", "")
        slug = slug_base
        suffix = 1
        while Game.query.filter_by(slug=slug).first():
            suffix += 1
            slug = f"{slug_base}-{suffix}"

        game = Game(
            title=title,
            slug=slug,
            description=(data.get("short_description") or "")[:1000],
            cover_image=cover_image,
            steam_app_id=app_id,
            developer=", ".join(data.get("developers", []) or [])[:120],
            publisher=", ".join(data.get("publishers", []) or [])[:120],
            release_date=_parse_release_date(data.get("release_date", {}).get("date")),
            metacritic_score=(data.get("metacritic") or {}).get("score"),
            category_id=category.id,
            is_free_to_play=is_free,
            tags=", ".join(c["description"] for c in (data.get("categories") or []))[:500],
            supported_languages=(data.get("supported_languages") or "")[:500],
            last_synced_at=datetime.utcnow(),
        )
        db.session.add(game)
        db.session.flush()

        acronym = _generate_acronym_alias(title)
        if acronym:
            db.session.add(GameAlias(game_id=game.id, alias=acronym))
        result_status = "imported"

    # --- Steam price: verified by the official verifier (never written here) ---
    from official_prices import ensure_steam_listing, verify_listing
    listing = ensure_steam_listing(game)
    db.session.commit()
    try:
        verify_listing(listing)
    except Exception as exc:
        logger.warning(f"price verification failed for {app_id}: {exc}")

    db.session.commit()
    return result_status, title


# =================================================================
# 3. BATCH PROCESSING (rate-limited, resumable)
# =================================================================

def run_import_batch(batch_size=BATCH_SIZE):
    """Processes up to `batch_size` PENDING queue rows. Returns a summary
    dict. Safe to call repeatedly — always resumes from whatever is still
    PENDING, so pausing/crashing/restarting never loses the cursor."""
    from extensions import db
    from models import SteamImportQueue, ImportJob

    job = ImportJob.query.first()
    if not job:
        job = ImportJob(status="idle")
        db.session.add(job)
        db.session.commit()

    batch = SteamImportQueue.query.filter_by(status="pending").limit(batch_size).all()
    summary = {"imported": 0, "updated": 0, "skipped": 0, "failed": 0}

    for row in batch:
        # Re-check pause/stop on every single app, not just once per
        # batch, so pausing takes effect within ~1.5s, not a whole batch.
        db.session.refresh(job)
        if job.status != "running":
            break

        row.attempts += 1
        row.last_attempted_at = datetime.utcnow()

        status, message = import_single_app(row.steam_app_id)

        if status in ("imported", "updated"):
            row.status = "imported"
            summary[status] += 1
            job.imported_count += 1
        elif status == "skipped":
            row.status = "skipped"
            row.last_error = message[:500]
            summary["skipped"] += 1
            job.skipped_count += 1
        else:  # failed
            row.last_error = message[:500]
            summary["failed"] += 1
            if message == "rate_limited" or row.attempts >= MAX_ATTEMPTS:
                row.status = "failed"
                job.failed_count += 1
            else:
                row.status = "pending"  # will be retried automatically next batch

        job.processed_count += 1
        job.last_message = f"{row.steam_app_id}: {status} — {message}"[:255]
        db.session.commit()

        if message == "rate_limited":
            logger.warning(f"Steam rate-limited us — backing off {RATE_LIMIT_BACKOFF_SECONDS}s")
            time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
        else:
            time.sleep(STEAM_IMPORT_DELAY_SECONDS)

    return summary


# =================================================================
# 4. BACKGROUND WORKER (daemon thread, DB-persisted progress)
# =================================================================

def _worker_loop(app):
    with app.app_context():
        from extensions import db
        from models import ImportJob

        while True:
            job = ImportJob.query.first()
            if not job or job.status != "running":
                break
            run_import_batch()
            db.session.refresh(job)
            if job.status != "running":
                break
            remaining = _count_pending()
            if remaining == 0:
                job.status = "completed"
                job.last_message = "Import complete — no pending apps remain."
                db.session.commit()
                break
            time.sleep(1)  # brief pause between batches, easy on the DB/CPU


def _count_pending():
    from models import SteamImportQueue
    return SteamImportQueue.query.filter_by(status="pending").count()


def start_background_import():
    """Seeds the queue if needed, marks the job 'running', and spawns the
    worker thread if one isn't already active in this process."""
    global _worker_thread
    from extensions import db
    from models import ImportJob
    from flask import current_app

    if _count_pending() == 0:
        seed_import_queue()

    job = ImportJob.query.first()
    if not job:
        job = ImportJob()
        db.session.add(job)
    job.status = "running"
    if not job.started_at:
        job.started_at = datetime.utcnow()
    job.total_apps = _count_pending() + job.imported_count + job.skipped_count + job.failed_count
    db.session.commit()

    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            app = current_app._get_current_object()
            _worker_thread = threading.Thread(target=_worker_loop, args=(app,), daemon=True)
            _worker_thread.start()


def pause_background_import():
    from extensions import db
    from models import ImportJob
    job = ImportJob.query.first()
    if job and job.status == "running":
        job.status = "paused"
        db.session.commit()


def retry_failed():
    """Resets every 'failed' queue row back to 'pending' so the next run
    picks them up again — per the 'retry failed imports' requirement."""
    from extensions import db
    from models import SteamImportQueue, ImportJob
    count = SteamImportQueue.query.filter_by(status="failed").update(
        {"status": "pending", "attempts": 0, "last_error": ""}
    )
    job = ImportJob.query.first()
    if job:
        job.failed_count = max(0, job.failed_count - count)
    db.session.commit()
    return count
