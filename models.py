from datetime import datetime, timedelta
from flask_login import UserMixin
from extensions import db, bcrypt


def _is_fresh(verified_at):
    """A verification is only trusted for PRICE_MAX_AGE_MINUTES (default 12h)."""
    if verified_at is None:
        return False
    try:
        from flask import current_app
        minutes = current_app.config.get("PRICE_MAX_AGE_MINUTES", 720)
    except RuntimeError:
        minutes = 720
    return datetime.utcnow() - verified_at <= timedelta(minutes=minutes)


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # Nullable: a user who only ever signs in with Google has no local
    # password at all — that's expected, not a bug.
    password_hash = db.Column(db.String(255), nullable=True)
    google_id = db.Column(db.String(64), unique=True, nullable=True, index=True)
    auth_provider = db.Column(db.String(20), default="local")  # 'local' or 'google'
    avatar = db.Column(db.String(512), default="default_avatar.png")
    is_admin = db.Column(db.Boolean, default=False)
    theme_preference = db.Column(db.String(10), default="dark")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    wishlist_items = db.relationship("Wishlist", backref="user", lazy=True, cascade="all, delete-orphan")
    notifications = db.relationship("Notification", backref="user", lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship("Review", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, raw_password):
        self.password_hash = bcrypt.generate_password_hash(raw_password).decode("utf-8")

    def check_password(self, raw_password):
        if not self.password_hash:
            return False  # Google-only account — no local password to check
        return bcrypt.check_password_hash(self.password_hash, raw_password)


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)

    games = db.relationship("Game", backref="category", lazy=True)


class Platform(db.Model):
    __tablename__ = "platforms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # Steam, Epic, GOG...
    logo = db.Column(db.String(255), default="")
    base_url = db.Column(db.String(255), default="")
    brand_color = db.Column(db.String(7), default="#00f5ff")  # hex, for the store badge
    cheapshark_store_id = db.Column(db.String(10), nullable=True)  # maps to CheapShark's storeID


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False, index=True)
    slug = db.Column(db.String(160), unique=True, nullable=False)
    description = db.Column(db.Text, default="")
    cover_image = db.Column(db.String(255), default="")
    banner_image = db.Column(db.String(255), default="")
    trailer_url = db.Column(db.String(255), default="")
    steam_app_id = db.Column(db.Integer, nullable=True, unique=True, index=True)  # drives auto image + price sync; dedup key
    developer = db.Column(db.String(120), default="")
    publisher = db.Column(db.String(120), default="")
    release_date = db.Column(db.Date, nullable=True)
    rating = db.Column(db.Float, default=0.0)          # 0-5, our own aggregate
    metacritic_score = db.Column(db.Integer, nullable=True)  # 0-100, from Steam
    steam_rating_percent = db.Column(db.Integer, nullable=True)  # 0-100, Steam's own review score
    tags = db.Column(db.String(500), default="")  # comma-separated
    supported_languages = db.Column(db.String(500), default="")
    system_requirements = db.Column(db.Text, default="")  # HTML snippet from Steam, min spec
    popularity_score = db.Column(db.Integer, default=0)  # for trending sort
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    is_free_to_play = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_synced_at = db.Column(db.DateTime, nullable=True)  # last successful API sync

    platform_listings = db.relationship("GamePlatform", backref="game", lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship("Review", backref="game", lazy=True, cascade="all, delete-orphan")
    price_history = db.relationship("PriceHistory", backref="game", lazy=True, cascade="all, delete-orphan")
    screenshots = db.relationship("Screenshot", backref="game", lazy=True, cascade="all, delete-orphan")
    aliases = db.relationship("GameAlias", backref="game", lazy=True, cascade="all, delete-orphan")

    @property
    def best_price(self):
        """The store listing with the lowest OFFICIALLY VERIFIED, FRESH price.
        A listing whose price could not be verified (or has gone stale) is
        never considered, so "unavailable" can never masquerade as "cheapest"."""
        active = [p for p in self.platform_listings if p.price_is_trusted]
        return min(active, key=lambda p: p.current_price) if active else None

    @property
    def verified_offers(self):
        """Every (listing, edition) pair with a trusted price, cheapest first.
        This is what the game cards / Buy buttons are built from."""
        offers = []
        for listing in self.platform_listings:
            for ed in listing.editions:
                if ed.price_is_trusted:
                    offers.append((listing, ed))
        offers.sort(key=lambda pair: (pair[1].current_price, pair[0].platform.name))
        return offers

    @property
    def best_offer(self):
        """(listing, edition) with the lowest verified price, or None."""
        offers = self.verified_offers
        return offers[0] if offers else None

    @property
    def verified_store_count(self):
        return len({listing.id for listing, _ in self.verified_offers})

    @property
    def best_discount(self):
        active = [p for p in self.platform_listings if p.price_is_trusted and p.discount_percent]
        return max(active, key=lambda p: p.discount_percent) if active else None

    @property
    def historical_low(self):
        """Lowest OFFICIALLY VERIFIED price ever recorded (rows written by the
        verifier only - legacy/seeded rows are ignored)."""
        prices = [p.price for p in self.price_history if p.price is not None and p.verified]
        return min(prices) if prices else None

    @property
    def alias_list(self):
        return [a.alias for a in self.aliases]

    @property
    def sorted_listings(self):
        """Platform listings sorted cheapest-first; stores with no
        confirmed price (current_price is None) always sort last —
        'Unavailable' is never mistaken for a low price."""
        return sorted(
            self.platform_listings,
            key=lambda p: (p.current_price is None, p.current_price if p.current_price is not None else 0),
        )


class GamePlatform(db.Model):
    """Price/availability of a Game on a specific Platform (many-to-many with price data)."""
    __tablename__ = "game_platforms"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False, index=True)
    platform_id = db.Column(db.Integer, db.ForeignKey("platforms.id"), nullable=False, index=True)
    # NULL means "we don't have a confirmed price from this store" — shown
    # as "Unavailable" in the UI. It is NEVER the same as a real price of 0
    # (which only happens for genuinely free games).
    original_price = db.Column(db.Float, nullable=True, default=None)
    current_price = db.Column(db.Float, nullable=True, default=None)
    price_currency = db.Column(db.String(3), default="USD")  # ISO code of the STORED price above
    discount_percent = db.Column(db.Integer, default=0)
    historical_low_price = db.Column(db.Float, nullable=True)  # cheapest ever seen, this store
    store_url = db.Column(db.String(255), default="#")
    in_stock = db.Column(db.Boolean, default=True)
    source = db.Column(db.String(30), default="manual")  # steam, cheapshark, itad, manual
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ---- official-price verification (see official_prices.py) ----
    # The store's OWN identifier for this game: Steam app id, Xbox product
    # (Big) id(s), Epic catalog namespace. This - never a title search - is
    # what guarantees the price/URL belong to exactly this game.
    store_product_id = db.Column(db.String(128), nullable=True)
    last_verified_at = db.Column(db.DateTime, nullable=True, index=True)
    # unverified | verified | stale | failed
    verify_status = db.Column(db.String(12), default="unverified", index=True)
    verify_error = db.Column(db.String(255), default="")

    platform = db.relationship("Platform")
    editions = db.relationship(
        "Edition", backref="listing", lazy=True,
        cascade="all, delete-orphan", order_by="Edition.sort_order",
    )

    __table_args__ = (db.UniqueConstraint("game_id", "platform_id", name="uq_game_platform"),)

    @property
    def price_is_trusted(self):
        """True only when the price came from the official store and is
        recent enough to show. Everything user-facing keys off this."""
        return (
            self.current_price is not None
            and self.verify_status == "verified"
            and _is_fresh(self.last_verified_at)
        )


class Edition(db.Model):
    """One purchasable edition (Standard / Deluxe / Ultimate ...) of a game
    on ONE official store, with its own official price and its own exact
    purchase URL. Rows are written only by official_prices.py."""
    __tablename__ = "game_editions"

    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("game_platforms.id"), nullable=False, index=True)
    # The store's own id for this edition (Steam package id, Xbox product id,
    # Epic offer id) - the dedup key, and what the purchase URL is built from.
    edition_key = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    original_price = db.Column(db.Float, nullable=True)
    current_price = db.Column(db.Float, nullable=True)   # NULL = "Unable to verify price"
    currency = db.Column(db.String(3), default="USD")
    discount_percent = db.Column(db.Integer, default=0)
    purchase_url = db.Column(db.String(500), nullable=True)
    url_verified_at = db.Column(db.DateTime, nullable=True)
    is_available = db.Column(db.Boolean, default=True)
    last_verified_at = db.Column(db.DateTime, nullable=True)
    sort_order = db.Column(db.Integer, default=0)

    __table_args__ = (db.UniqueConstraint("listing_id", "edition_key", name="uq_listing_edition"),)

    @property
    def price_is_trusted(self):
        return (
            self.current_price is not None
            and bool(self.is_available)
            and self.listing.verify_status == "verified"
            and _is_fresh(self.last_verified_at)
            and _is_fresh(self.listing.last_verified_at)
            and self.link_is_verified
        )

    @property
    def link_is_verified(self):
        return bool(self.purchase_url) and self.url_verified_at is not None


class Deal(db.Model):
    __tablename__ = "deals"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    platform_id = db.Column(db.Integer, db.ForeignKey("platforms.id"), nullable=False)
    deal_type = db.Column(db.String(30), default="discount")  # discount, free, giveaway, weekend_ftp
    discount_percent = db.Column(db.Integer, default=0)
    starts_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    game = db.relationship("Game")
    platform = db.relationship("Platform")


class PriceHistory(db.Model):
    __tablename__ = "price_history"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    platform_id = db.Column(db.Integer, db.ForeignKey("platforms.id"), nullable=False)
    price = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)
    # True only for rows written by the official-price verifier. Older
    # (seeded / manually entered / aggregator) rows stay False and are never
    # charted or used for "all-time low".
    verified = db.Column(db.Boolean, default=False, index=True)

    platform = db.relationship("Platform")


class Wishlist(db.Model):
    __tablename__ = "wishlist"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    target_price = db.Column(db.Float, nullable=True)  # alert when price drops to/below this
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    alert_sent = db.Column(db.Boolean, default=False)

    game = db.relationship("Game")

    __table_args__ = (db.UniqueConstraint("user_id", "game_id", name="uq_user_game"),)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Feedback(db.Model):
    """General site feedback — separate from per-game Reviews. Anyone can
    submit (logged in or not); admins can view it all in the admin panel."""
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(30), default="general")  # general, bug, feature, pricing
    message = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=True)  # optional 1-5 site rating
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_reviewed = db.Column(db.Boolean, default=False)

    user = db.relationship("User")


class GameAlias(db.Model):
    """Alternate names/short names/abbreviations for a game so search finds
    it by nickname — e.g. "GTA V" has aliases "GTAV", "GTA 5", "GTA".
    This is what makes abbreviation search actually work, rather than
    relying on fuzzy string matching alone."""
    __tablename__ = "game_aliases"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False, index=True)
    alias = db.Column(db.String(100), nullable=False, index=True)

    __table_args__ = (db.UniqueConstraint("game_id", "alias", name="uq_game_alias"),)


class Screenshot(db.Model):
    __tablename__ = "screenshots"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False, index=True)
    image_url = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, default=0)


class SteamImportQueue(db.Model):
    """One row per Steam App ID from Steam's master app list. This is the
    resumable work queue for the catalog importer: seeded once (~260k rows)
    from GetAppList, then the background worker walks through PENDING rows
    in batches. Status is persisted here — not just in memory — so an
    import can be paused, the server restarted, and resumed exactly where
    it left off, per the "resume if the process stops" requirement."""
    __tablename__ = "steam_import_queue"

    id = db.Column(db.Integer, primary_key=True)
    steam_app_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    steam_name = db.Column(db.String(255), default="")  # raw name from GetAppList (pre-import)
    status = db.Column(db.String(20), default="pending", index=True)
    # pending -> imported | skipped | failed
    attempts = db.Column(db.Integer, default=0)
    last_error = db.Column(db.String(500), default="")
    last_attempted_at = db.Column(db.DateTime, nullable=True)
    imported_game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ImportJob(db.Model):
    """Tracks the state of the (single, singleton) catalog-wide import run
    so the admin panel can show live progress and start/pause/resume it.
    Only one row is ever needed in practice, but modeled as a table (not a
    single in-memory flag) so state survives app restarts."""
    __tablename__ = "import_jobs"

    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default="idle")  # idle, running, paused, completed, failed
    total_apps = db.Column(db.Integer, default=0)
    processed_count = db.Column(db.Integer, default=0)
    imported_count = db.Column(db.Integer, default=0)
    skipped_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message = db.Column(db.String(255), default="")
