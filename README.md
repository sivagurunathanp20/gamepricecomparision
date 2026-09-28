# GameVault — Game Comparison & Deals Tracking System

A full-stack game price comparison and deals-tracking platform built for a
final-year college project.

**Stack:** Flask (Python) · SQLAlchemy ORM · MySQL (production) / SQLite (instant local run) · Bootstrap 5 · Vanilla JS · Chart.js

---

## 1. Features

- **Google Sign-In (OAuth 2.0)** — optional "Sign in with Google" button
  on Login/Register, alongside the existing email/password accounts. See
  §5a for setup.
- **Automatic periodic price refresh** — `sync_prices.bat` + Windows Task
  Scheduler re-fetches every game's prices on a schedule (e.g. every 6
  hours) with zero manual clicking. See §9.
- **Game comparison** — side-by-side prices across Steam, Epic Games Store, GOG,
  Humble Bundle, Fanatical, Green Man Gaming, Ubisoft Connect, EA App, and
  more, sorted cheapest-first, with search/filter by genre, platform, price
  and rating.
- **Smart search** — fuzzy matching, alias/abbreviation search, and typo
  tolerance. Searching `GTA`, `GTAV`, `CS2`, `PUBG`, `RDR2`, `COD`, `FC25`
  all instantly resolve to the right game. See §7.
- **Deals tracking** — biggest discounts, trending, newly added, limited-time
  offers, with live countdown timers.
- **Free games hub** — free-to-keep, giveaways, and free weekends, with expiry
  countdowns.
- **User accounts** — register/login (hashed passwords), profile, wishlist with
  per-game target-price alerts, recently viewed games, dark/light mode.
- **Admin panel** — manage games (with alias management + one-click API
  sync), platform prices, deals, users, and feedback; analytics dashboard
  with signup and popularity charts.
- **REST API** (`/api/v1/...`) — filterable/searchable game listings, price
  history, active deals — ready for a future mobile app.
- **Never a fake ₹0** — a store price that couldn't be confirmed is stored
  as `NULL` and shown as "Unavailable", never as zero. Zero is only ever
  shown for genuinely free-to-play games. See §8 for the root-cause fix.
- **Automatic Steam images** — every game with a Steam App ID gets its
  official Steam header/cover image automatically (no manual upload) via
  Steam's public CDN, with a placeholder fallback if unavailable.
- **Multi-store price sync** — Steam fetched directly, plus Epic/GOG/Humble/
  Fanatical/GMG/EA/Ubisoft via **CheapShark** (free, no API key needed) and
  optionally **IsThereAnyDeal** for extra coverage. Duplicate-safe (unique
  Steam App ID constraint) and highlights the lowest current price + shows
  each store's historical low. See §8.
- **Steam catalog import system** — a real, resumable background job that
  can grow the catalog to the entirety of Steam (~260k apps), not a
  hardcoded list. Batched, rate-limited, duplicate-safe, resumes after a
  restart, with live progress in the admin panel. See §9.
- **Multi-currency display** — Steam prices are fetched in real regional
  currency (INR by default), other stores' USD prices convert live via a
  free exchange-rate API (offline fallback table included) to whichever
  currency the visitor picks — USD, INR, EUR, GBP, JPY, AUD, CAD, SGD,
  AED, BRL.
- **Feedback system** — a public `/feedback` form (bug reports, feature
  requests, pricing issues, star rating) that admins can review and mark
  as handled from the admin panel.
- **Price alert emails** — `flask check-price-alerts` scans wishlists and
  emails users when a game hits their target price (logs to console if SMTP
  isn't configured).
- **Performance** — indexed lookup columns (title, aliases, steam_app_id,
  foreign keys), 30-minute in-memory API response caching, lazy-loaded
  images, and shimmer loading skeletons on game cards.

---

## 2. Project Structure

```
game_deals_tracker/
├── app.py                 # App factory, CLI commands, entry point
├── config.py               # Config (SQLite by default, MySQL via env var)
├── extensions.py            # db, login_manager, bcrypt, mail singletons
├── models.py                 # SQLAlchemy models (13 tables)
├── search.py                   # Fuzzy/alias/abbreviation search engine
├── currency.py                  # Live multi-currency conversion
├── store_apis.py                 # Steam images + CheapShark/ITAD price sync
├── steam_importer.py               # Resumable full-catalog Steam importer
├── seed.py                          # Fast demo-data seeder (~18 fake games)
├── seed_real_steam.py                # Fast real-Steam-data seeder (~26 games)
├── alerts.py                          # Price-alert email job
├── requirements.txt
├── .env.example
├── routes/
│   ├── main.py        # home, compare, game details, dashboard, AJAX search
│   ├── auth.py         # register/login/logout/profile
│   ├── deals.py         # deals & discounts, free games
│   ├── wishlist.py       # wishlist CRUD + price-alert targets
│   ├── admin.py           # admin CRUD, analytics, Steam catalog import UI
│   └── api.py               # REST API (JSON)
├── templates/           # Jinja2 + Bootstrap 5 templates
├── static/css/style.css   # Dark neon glassmorphism theme (+ light mode)
├── static/js/main.js       # theme toggle, live search, countdowns, wishlist AJAX
└── database/schema.sql       # Reference MySQL DDL (matches models.py)
```

---

## 3. Quick Start (SQLite — zero setup)

```bash
cd game_deals_tracker
python -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows

pip install -r requirements.txt

flask --app app init-db          # creates tables
flask --app app seed-db           # loads demo games, deals, users

flask --app app run --debug        # http://127.0.0.1:5000
```

Demo logins (created by `seed-db`):
- **Admin:** admin@gamevault.com / Admin@123
- **User:** demo@gamevault.com / Demo@123

### Want REAL game data instead of demo data?

Run this instead of (or after) `seed-db` — it pulls **real** titles, real
cover images, real descriptions and real live USD prices for ~20 popular
games straight from Steam's public store API (no API key needed, just
internet access):

```bash
flask --app app seed-steam
```

Only Steam's price is 100% real — Epic/GOG/Xbox/PlayStation don't have a
free public pricing API, so those rows are a randomized variation on the
real Steam price just to populate the comparison table. Re-run the command
any time to refresh with the latest live Steam prices. Want more/different
games? Edit `STEAM_APP_IDS` in `seed_real_steam.py` — any Steam store URL
like `store.steampowered.com/app/<id>` gives you the ID to add.

---

## 4. Switching to MySQL (production)

1. Install MySQL Server and create a user:
   ```sql
   CREATE DATABASE game_deals_db CHARACTER SET utf8mb4;
   CREATE USER 'gamevault_user'@'localhost' IDENTIFIED BY 'yourpassword';
   GRANT ALL PRIVILEGES ON game_deals_db.* TO 'gamevault_user'@'localhost';
   FLUSH PRIVILEGES;
   ```
2. Copy `.env.example` to `.env` and set:
   ```
   DATABASE_URL=mysql+pymysql://gamevault_user:yourpassword@localhost:3306/game_deals_db
   SECRET_KEY=some-long-random-string
   ```
3. Either let SQLAlchemy create the tables:
   ```bash
   flask --app app init-db
   flask --app app seed-db
   ```
   or run `database/schema.sql` directly in MySQL/phpMyAdmin if you prefer
   raw DDL, then adapt `seed.py` or insert your own data.

The same `models.py` / routes work unchanged against MySQL — only the
`DATABASE_URL` env var changes.

---

## 5. Enabling real price-alert emails

By default `MAIL_SUPPRESS_SEND=1`, so alert emails are computed and logged
to an in-app `Notification` row but not actually sent (safe for local dev).
To send real emails:

1. In `.env`, set `MAIL_USERNAME` / `MAIL_PASSWORD` (use an app password for
   Gmail, not your normal password) and `MAIL_SUPPRESS_SEND=0`.
2. Run the check periodically, e.g. via cron:
   ```
   */30 * * * * cd /path/to/game_deals_tracker && flask --app app check-price-alerts
   ```
   In a real deployment this would run right after whatever job re-scrapes
   current prices from each store (that scraping job is out of scope here —
   `admin.set_price` is the manual stand-in for it).

---

## 5a. Enabling Google Sign-In (OAuth 2.0)

Optional — the app works exactly as before with plain email/password
accounts if you skip this. Implemented with **Authlib** (a well-maintained
Flask OAuth client), kept deliberately simple: two routes, one User model
change, one button.

### Setup
1. Go to https://console.cloud.google.com/apis/credentials
2. **Create Credentials → OAuth client ID → Application type: Web application**
3. Under **Authorized redirect URIs**, add:
   ```
   http://127.0.0.1:5000/auth/google/callback
   ```
   (add your real domain's equivalent when you deploy, e.g.
   `https://yourdomain.com/auth/google/callback`)
4. Copy the generated **Client ID** and **Client Secret** into `.env`:
   ```
   GOOGLE_CLIENT_ID=your-google-client-id
   GOOGLE_CLIENT_SECRET=your-google-client-secret
   ```
5. Restart the app. A "Sign in with Google" button now appears on the
   Login and Register pages automatically — no code changes needed. If
   these two env vars are left blank, the button simply doesn't render
   and nothing else changes.

### How it works (kept simple on purpose)
- `GET /auth/google/login` — redirects to Google's consent screen.
- `GET /auth/google/callback` — Google redirects back here with an
  authorization code; Authlib exchanges it for tokens and verifies the
  signed ID token, giving us the user's verified email + name.
- **Account matching, in order:** (1) an existing user with this exact
  Google account signs straight in; (2) a first-time Google sign-in whose
  email matches an existing local email/password account gets **linked**
  (same account, now usable either way); (3) otherwise a brand-new
  account is created with no local password — that user signs in with
  Google going forward.
- **Session handling** — identical to normal login: `flask_login.login_user()`
  creates the same signed, secure session cookie either way, and
  `/auth/logout` works the same regardless of how the user signed in.
- OAuth's CSRF protection (the `state` parameter) is handled internally
  by Authlib using the Flask session — nothing extra to implement.

---

## 6. REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/games` | GET | Filterable/paginated game list (`q`, `genre`, `platform`, `min_rating`, `sort`, `page`) |
| `/api/v1/games/<id>/price-history` | GET | Price history points for the chart |
| `/api/v1/deals/active` | GET | All currently active deals |
| `/api/search` | GET | Lightweight live-search used by the navbar |

---

## 7. Search: Fuzzy Matching, Aliases & Abbreviations

Search (navbar box, `/compare`, and the REST API's `q` param) understands
far more than exact titles — this is what makes `GTAV`, `CS2`, `PUBG`,
`RDR2`, `COD`, `FC25`, `NFS`, `AC`, `Elden`, and `Witcher` all instantly
resolve to the right game:

1. **Direct/partial title match** — case-insensitive `LIKE` on the title.
2. **Alias match** — a `GameAlias` table holds abbreviations/nicknames per
   game (e.g. Grand Theft Auto V → `GTA`, `GTAV`, `GTA V`, `GTA 5`). The
   `seed-steam` command pre-populates these for ~25 well-known titles; add
   more anytime from the admin panel's "Aliases" field on any game, or in
   bulk by editing `GAME_ALIASES` in `seed_real_steam.py`.
3. **Typo-tolerant fuzzy fallback** — only kicks in when neither of the
   above found anything (e.g. "Elden Rign"), using Python's built-in
   `difflib` — no extra dependency needed.

This is implemented in `search.py`. At catalog sizes in the hundreds/low
thousands (realistic for this project) it's instant; at Steam's full
260,000+ game catalog scale you'd swap the fuzzy layer for a real search
engine (Postgres full-text search, Meilisearch, Elasticsearch) — noted
here as the production-scale upgrade path, not implemented in this
project.

---

## 8. Automatic Images & Multi-Store Price Sync

### How images work
Every game with a **Steam App ID** set (find it in the game's Steam URL —
`store.steampowered.com/app/<id>/...`) automatically gets its official
Steam header/cover image — no upload, no manual URL needed. This is done
via Steam's public CDN (`cdn.akamai.steamstatic.com/steam/apps/<id>/...`),
which needs no API key. If that image can't be reached, the app falls back
to whatever you typed in "Cover Image URL", and finally to a generic
placeholder — it never breaks the layout.

### How multi-store pricing works
There's no single free API that covers Epic, GOG, Humble Store, Fanatical,
Green Man Gaming, Ubisoft Store, EA App, and Xbox individually — most of
those storefronts simply don't expose public, keyless pricing APIs. Two
real aggregators fill that gap, used together:

1. **CheapShark** (https://apidocs.cheapshark.com) — completely free, **no
   signup, no API key**, works immediately. Covers Steam, GOG, Humble
   Store, Fanatical, Green Man Gaming, Epic Games Store, EA App (listed as
   "Origin"), and Ubisoft Connect. This is the default/primary source.
2. **IsThereAnyDeal (ITAD)** — also free, optional, needs a personal API
   key (one signup, no cost) for extra coverage on top of CheapShark:
   ```
   1. Get a free key: https://isthereanydeal.com/apps/
   2. Add it to .env: ITAD_API_KEY=your-key-here
   ```

Either way, run a sync:
```bash
flask --app app sync-all-prices        # every game with a Steam App ID
# or, per-game: the "Sync Image & Prices Now" button on
# /admin/games/<id>/edit
```

When both sources return a price for the same store, the app keeps the
**lower** one — this is a price-comparison site, so understating a price
briefly is a much smaller problem than overstating one. Steam itself is
always fetched directly (no key needed, most authoritative source for
that one store).

**New games auto-sync on creation** — set a Steam App ID when adding a game
in the admin panel and it immediately fetches its image + every store price
ITAD has, no extra click needed.

**Reliability:** every external call (Steam image check, ITAD lookup, ITAD
price fetch) is wrapped independently — one store being down or rate-limited
never blocks the others, and results are cached in memory for 30 minutes to
avoid hammering either API on repeated page loads. See `store_apis.py` for
the implementation — it's the module to extend if you get direct API access
to any individual store later.

---

## 9. Automatic Periodic Price Sync (Windows Task Scheduler)

Prices don't update in real time by themselves — nobody's price-comparison
site does, because Steam/Epic/GOG don't push change notifications to
anyone. What every site (including this one) actually does is **pull**
fresh prices on a schedule. `sync_prices.bat` + Windows Task Scheduler
gives you that: an automatic refresh every few hours, no manual clicking.

### Setup steps

1. **Edit `sync_prices.bat`** — open it in a text editor and fix this line
   to match wherever you actually extracted the project:
   ```bat
   cd /d "C:\Users\sivag\Downloads\game_deals_tracker"
   ```
2. **Open Task Scheduler** — Start menu → type "Task Scheduler" → open it.
3. **Create Task** (right panel → "Create Task...", not "Create Basic
   Task" — the full dialog gives more control):
   - **General tab:** Name it `GameVault Price Sync`. Select "Run whether
     user is logged on or not" if you want it to fire even when you're
     not actively at the computer.
   - **Triggers tab → New:** "On a schedule" → Daily → set "Repeat task
     every" to **6 hours** (or whatever you'd prefer) → "for a duration
     of" **Indefinitely**.
   - **Actions tab → New:** Action = "Start a program" → Program/script =
     the full path to `sync_prices.bat` (e.g.
     `C:\Users\sivag\Downloads\game_deals_tracker\sync_prices.bat`).
   - **Conditions tab:** uncheck "Start the task only if the computer is
     on AC power" if this is a laptop, so it still runs on battery.
4. **Save** — it'll ask for your Windows password if you chose "run
   whether logged on or not".
5. **Test it immediately:** right-click the task → "Run". Then check
   `sync_log.txt` inside the project folder — a new timestamped line
   confirms it actually fired.

### What it actually does when it fires
Runs `flask --app app sync-all-prices`, which — for every game that has a
Steam App ID — re-fetches Steam's current price directly and re-checks
CheapShark (+ ITAD if you added a key) for the other stores, then updates
`current_price`/`discount_percent`/`price_history` in the database. Your
website's data is only ever as fresh as the last time this ran — with the
6-hour schedule above, that's a maximum 6-hour delay behind the real
stores, which is the same lag every real price-tracking site has.

### Where the price data itself comes from
You don't provide or maintain any of it — it's fetched live from the
internet every time the script runs:
- **Steam** — `store.steampowered.com`'s public API, no key needed.
- **CheapShark** — `cheapshark.com`'s public API, no key needed, covers
  Epic/GOG/Humble/Fanatical/GMG/EA/Ubisoft too.
- **ITAD** — optional, only if you added a free key to `.env` (§8).

The only requirement is that the computer running the scheduled task has
an internet connection at the moment it fires.

---

## 10. Steam Catalog Import System (build the full Steam catalog)

This is a real, resumable background import system — not a hardcoded
game list. It's built from three pieces (`steam_importer.py`):

1. **`seed_import_queue()`** pulls Steam's full public app list — every
   App ID that exists, ~260,000 entries, via `ISteamApps/GetAppList` (no
   key needed) — into a `steam_import_queue` table, one row per app,
   status `pending`. Safe to re-run any time to pick up new releases;
   already-queued/imported apps are skipped.
2. **`import_single_app(app_id)`** does the real work for one game: fetches
   full Steam metadata + regional pricing (tries India first, so pricing
   is real INR by default, falling back to other regions only if needed),
   and creates or **updates** the matching `Game` row — `steam_app_id` is
   the unique key, so re-importing the same app always updates in place,
   never duplicates. Entries that turn out not to be an actual game
   (DLC, soundtracks, server tools, software) are marked `skipped`, not
   imported. This exact function is also what the admin's "Import by
   Steam App ID" button calls — one code path, not two.
3. **`run_import_batch()`** processes a small batch (20 apps) from the
   queue with a **1.5-second delay between every Steam API call** to stay
   well under any reasonable rate limit, and **commits after every single
   app** — so a crash mid-batch loses at most one in-flight row, never
   the whole batch. A background daemon thread loops this while the job
   status is `running`; pausing (or the app restarting) just stops the
   loop — the queue's `pending`/`imported`/`failed` status is the only
   state that matters, and it's in the database, not memory.

### Using it
Admin panel → **Steam Catalog** (sidebar): Start/Pause, a live progress
bar (polls every 4s), counts of imported/pending/skipped/failed, a
"Retry All Failed" button, and a one-off "Import by Steam App ID" field.

Or from the terminal:
```bash
flask --app app steam-seed-queue      # one-time: queue the full app list
flask --app app steam-import-run      # runs continuously until done/Ctrl+C
# or, for a cron job instead of a long-running terminal session:
flask --app app steam-import-batch    # imports one batch (20 apps) and exits
```

### The honest timing math
Steam doesn't publish an official rate limit, so `steam_importer.py` stays
conservative (1.5s/request ≈ 2,400 requests/hour ≈ ~57,600/day). At that
pace, the full ~260,000-entry catalog takes **roughly 4-5 days of
continuous running** — many of those entries are DLC/software/demos that
get skipped quickly, so real-world runs are often faster, but there's no
way to import "everything, instantly" without risking an IP block from
Steam. This is stated plainly in the admin UI too, not discovered later.
Leave `steam-import-run` going in a `screen`/`tmux` session (or as a
systemd service) for a full catalog, or just run it however long you like
— every batch that completes is permanent progress.

### Concurrency note (SQLite vs MySQL)
The bundled SQLite database works fine for short import runs, but SQLite
serializes writes — running the importer for hours *while* real users are
also browsing/buying can occasionally produce a "database is locked"
error on either side. For a real extended import run, switch to MySQL
first (§4) — it handles concurrent writes properly and is what you'd want
in production anyway.

---

## 11. Deployment Guide (production)

1. **Server:** any VPS (Ubuntu 22.04+) or PaaS (Render, Railway, PythonAnywhere).
2. **WSGI server:** don't use `flask run` in production — use gunicorn:
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:8000 "app:app"
   ```
3. **Reverse proxy:** put Nginx in front of gunicorn for TLS + static files.
4. **Database:** managed MySQL (RDS, PlanetScale, etc.) — set `DATABASE_URL`.
5. **Secrets:** never commit `.env`; set `SECRET_KEY`, `DATABASE_URL`,
   `MAIL_USERNAME`/`MAIL_PASSWORD`, `ITAD_API_KEY` as environment variables
   on the host.
6. **Static files:** served by Nginx directly from `static/` in production
   for best performance.
7. **Scheduled jobs:** cron (or Celery beat) for `check-price-alerts` and
   `sync-all-prices` so prices/images stay fresh automatically.

---

## 12. Notes / Known Scope Limits (student-project honesty)

- **Steam** prices/images are 100% real, live data — pulled directly from
  Steam's public API/CDN, no key needed.
- **Epic/GOG/Humble/Fanatical/GMG/EA/Ubisoft** prices are real via
  **CheapShark** (no key needed) whenever that game is in CheapShark's
  database, plus **ITAD** too if you add a free key — see §8.
- **Xbox Store/PlayStation Store** don't have a public pricing API through
  either aggregator for most titles — those rows stay manual/demo unless
  you have partner API access to wire in yourself.
- **The ₹0 bug, root cause:** the old seeder defaulted a missing Steam
  `price_overview` straight to `0.0`. Fixed at the database level —
  `current_price`/`original_price` are now nullable, `None` means
  "unavailable" everywhere in the code and templates, and the seeder tries
  4 regional Steam storefronts before giving up on a price. A real ₹0 is
  now only ever shown for a genuinely free-to-play game.
- **The catalog can now genuinely grow to all of Steam** via the importer
  in §9 — this isn't a hardcoded list anymore. The honest constraint is
  *time*, not scope: a safe, non-rate-limited pace means the full
  ~260,000-entry catalog takes several days of continuous background
  running, not minutes. `flask --app app seed-steam` still exists as a
  fast ~26-game starter catalog for quick local testing; the real importer
  (§9) is what you'd leave running for the actual "comprehensive catalog."
- **Fuzzy search is in-memory (`difflib`) and scans every game+alias on
  each query.** Fine up to a few thousand games; once the importer has
  pulled in tens of thousands of real games, this should be swapped for
  real full-text search (Postgres full-text, Meilisearch, Elasticsearch)
  for search speed — noted as the next upgrade, not implemented here.
- **OpenCritic score, official ESRB/PEGI ratings, and IGDB** all require
  paid or OAuth-gated API access this project doesn't have credentials
  for, so they're intentionally left out rather than faked. Steam's own
  Metacritic score and review percentage are used instead — both come
  free with the Steam API call already being made.
- Email sending is fully wired but **suppressed by default** so the project
  runs without any SMTP credentials.



---
## Official price verification (new)

Every price and Buy link on the site is read from the game's **own store** by `official_prices.py`.

| Store | Source | Editions |
|---|---|---|
| Steam | `appdetails` + `packagedetails` (automatic from `steam_app_id`) | each Steam package (Standard, Deluxe...) |
| Xbox Store | Microsoft display-catalog API, needs the 12-char product id per edition | one product id per edition |
| Epic Games Store | storefront GraphQL, needs the catalog *namespace* | every base-game/edition offer in the namespace |
| PlayStation / Nintendo | no public price API | link only, price shows "Unable to verify price" |

Rules: a price is stored only if the store returned it for that store's own product id and in the
currency of `STORE_COUNTRY`; Buy URLs must match an exact product-page pattern (no search/home pages);
prices older than `PRICE_MAX_AGE_MINUTES` are hidden; games with no verified price are hidden from Browse
(`SHOW_UNVERIFIED_GAMES=1` lists them as "Unable to verify price"). CheapShark/ITAD are no longer used for prices.

```
flask --app app verify-prices                       # verify everything now
flask --app app add-official-product --game elden-ring --store "Xbox Store" --product-id 9P9XBTMQQ2XZ
flask --app app add-official-product --game elden-ring --store "Epic Games Store" --product-id <namespace>
flask --app app add-official-product --game x --store "PlayStation Store" --url https://store.playstation.com/en-in/product/EP...
flask --app app purge-legacy-data --yes             # delete old seeded/fake rows (optional)
python -m unittest tests.test_official_prices -v    # offline tests
```
On first start the old (seeded/manual) prices are cleared automatically; Steam prices reappear after `verify-prices`.
