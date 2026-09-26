-- =====================================================================
-- GameVault — Game Comparison & Deals Tracking System
-- MySQL Schema (production reference)
--
-- The Flask app can auto-create these tables from models.py via:
--     flask --app app init-db
-- This file is provided so the schema can also be created directly in
-- MySQL / phpMyAdmin, or reviewed independently of the ORM.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS game_deals_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE game_deals_db;

-- ---------------------------------------------------------------
-- USERS
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NULL,          -- NULL for Google-only accounts
    google_id VARCHAR(64) NULL UNIQUE,
    auth_provider VARCHAR(20) DEFAULT 'local', -- 'local' or 'google'
    avatar VARCHAR(512) DEFAULT 'default_avatar.png',
    is_admin BOOLEAN DEFAULT FALSE,
    theme_preference VARCHAR(10) DEFAULT 'dark',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- CATEGORIES (genres)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    slug VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- PLATFORMS / STORES (Steam, Epic, GOG, Ubisoft Connect, Xbox, ...)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platforms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    logo VARCHAR(255) DEFAULT '',
    base_url VARCHAR(255) DEFAULT '',
    brand_color VARCHAR(7) DEFAULT '#00f5ff',
    cheapshark_store_id VARCHAR(10) NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- GAMES
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS games (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    slug VARCHAR(160) NOT NULL UNIQUE,
    description TEXT,
    cover_image VARCHAR(255) DEFAULT '',
    banner_image VARCHAR(255) DEFAULT '',
    trailer_url VARCHAR(255) DEFAULT '',
    steam_app_id INT NULL UNIQUE,          -- drives auto image + price sync; also the dedup key
    developer VARCHAR(120) DEFAULT '',
    publisher VARCHAR(120) DEFAULT '',
    release_date DATE,
    rating FLOAT DEFAULT 0,                 -- our own 0-5 aggregate
    metacritic_score INT NULL,              -- 0-100, from Steam
    steam_rating_percent INT NULL,          -- 0-100, Steam's own review score
    tags VARCHAR(500) DEFAULT '',           -- comma-separated
    supported_languages VARCHAR(500) DEFAULT '',
    system_requirements TEXT,               -- min spec, HTML snippet from Steam
    popularity_score INT DEFAULT 0,
    category_id INT,
    is_free_to_play BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_synced_at DATETIME NULL,           -- last successful API sync
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- GAME_ALIASES — abbreviations/nicknames so search finds a game by
-- "GTAV", "CS2", "PUBG", "RDR2", "COD", "FC25" etc.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS game_aliases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id INT NOT NULL,
    alias VARCHAR(100) NOT NULL,
    UNIQUE KEY uq_game_alias (game_id, alias),
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- SCREENSHOTS
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS screenshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id INT NOT NULL,
    image_url VARCHAR(255) NOT NULL,
    sort_order INT DEFAULT 0,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- GAME_PLATFORMS (price/availability per store)
-- NOTE: original_price/current_price are NULLABLE ON PURPOSE. NULL means
-- "we don't have a confirmed price from this store" and the UI shows
-- "Unavailable" — it is never the same thing as a real price of 0 (which
-- only happens for genuinely free games). This is the fix for the
-- "GTA V shows ₹0" bug: a missing price must never silently become 0.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS game_platforms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id INT NOT NULL,
    platform_id INT NOT NULL,
    original_price DECIMAL(10,2) NULL,
    current_price DECIMAL(10,2) NULL,
    price_currency VARCHAR(3) DEFAULT 'USD',   -- ISO code of the price columns above (e.g. real INR from Steam India)
    discount_percent INT DEFAULT 0,
    historical_low_price DECIMAL(10,2) NULL,
    store_url VARCHAR(255) DEFAULT '#',
    in_stock BOOLEAN DEFAULT TRUE,
    source VARCHAR(30) DEFAULT 'manual',   -- steam, cheapshark, itad, manual
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_game_platform (game_id, platform_id),
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- DEALS
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS deals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id INT NOT NULL,
    platform_id INT NOT NULL,
    deal_type VARCHAR(30) DEFAULT 'discount', -- discount, free, giveaway, weekend_ftp
    discount_percent INT DEFAULT 0,
    starts_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NULL,
    is_featured BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- PRICE_HISTORY
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS price_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id INT NOT NULL,
    platform_id INT NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- WISHLIST (also doubles as the price-alert table — target_price +
-- alert_sent cover "Price Alerts" without a separate, always-in-sync
-- duplicate table)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wishlist (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    game_id INT NOT NULL,
    target_price DECIMAL(10,2) NULL,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    alert_sent BOOLEAN DEFAULT FALSE,
    UNIQUE KEY uq_user_game (user_id, game_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- NOTIFICATIONS
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    message VARCHAR(255) NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- REVIEWS (per-game)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    game_id INT NOT NULL,
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- FEEDBACK (general site feedback, separate from per-game reviews)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL,
    category VARCHAR(30) DEFAULT 'general',
    message TEXT NOT NULL,
    rating INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_reviewed BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- STEAM_IMPORT_QUEUE — resumable work queue for the catalog importer.
-- Seeded once from Steam's full app list (~260k rows); the background
-- worker walks PENDING rows in small batches. Status persists here so
-- an import survives being paused or the app restarting.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS steam_import_queue (
    id INT AUTO_INCREMENT PRIMARY KEY,
    steam_app_id INT NOT NULL UNIQUE,
    steam_name VARCHAR(255) DEFAULT '',
    status VARCHAR(20) DEFAULT 'pending',   -- pending, imported, skipped, failed
    attempts INT DEFAULT 0,
    last_error VARCHAR(500) DEFAULT '',
    last_attempted_at DATETIME NULL,
    imported_game_id INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (imported_game_id) REFERENCES games(id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE INDEX idx_steamqueue_status ON steam_import_queue(status);

-- ---------------------------------------------------------------
-- IMPORT_JOBS — single-row job-state table so the admin panel can show
-- live progress and start/pause/resume the catalog import.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    status VARCHAR(20) DEFAULT 'idle',   -- idle, running, paused, completed, failed
    total_apps INT DEFAULT 0,
    processed_count INT DEFAULT 0,
    imported_count INT DEFAULT 0,
    skipped_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,
    started_at DATETIME NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_message VARCHAR(255) DEFAULT ''
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- Helpful indexes for common query patterns
-- ---------------------------------------------------------------
CREATE INDEX idx_games_category ON games(category_id);
CREATE INDEX idx_games_title ON games(title);
CREATE INDEX idx_gamealiases_alias ON game_aliases(alias);
CREATE INDEX idx_gameplatforms_game ON game_platforms(game_id);
CREATE INDEX idx_gameplatforms_platform ON game_platforms(platform_id);
CREATE INDEX idx_deals_expires ON deals(expires_at);
CREATE INDEX idx_pricehistory_game ON price_history(game_id, recorded_at);
CREATE INDEX idx_wishlist_user ON wishlist(user_id);
