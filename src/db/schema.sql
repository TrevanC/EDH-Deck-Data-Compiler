-- EDH Deck Data Harvester Database Schema

-- Sources table
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Decks table
CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    source_deck_id TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT 'Commander',
    title TEXT,
    author TEXT,
    url TEXT,
    extra TEXT, -- JSON for source-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fetched_at TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources (id),
    UNIQUE(source_id, source_deck_id)
);

-- Deck cards table
CREATE TABLE IF NOT EXISTS deck_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    qty INTEGER NOT NULL DEFAULT 1,
    oracle_id TEXT, -- nullable until normalized
    zone TEXT DEFAULT 'main', -- main/side/command
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (deck_id) REFERENCES decks (id) ON DELETE CASCADE
);

-- Separate table for commanders (cleaner than zone flags)
CREATE TABLE IF NOT EXISTS deck_commanders (
    deck_id INTEGER NOT NULL,
    oracle_id TEXT NOT NULL,
    name TEXT NOT NULL, -- denormalized for convenience
    PRIMARY KEY (deck_id, oracle_id),
    FOREIGN KEY (deck_id) REFERENCES decks (id) ON DELETE CASCADE
);

-- Card normalization failures for review
CREATE TABLE IF NOT EXISTS unmapped_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    frequency INTEGER DEFAULT 1,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name)
);

-- Ingestion logs and metrics
CREATE TABLE IF NOT EXISTS ingestion_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    operation TEXT NOT NULL, -- 'discovery', 'export', 'normalize'
    status TEXT NOT NULL, -- 'success', 'error', 'partial'
    decks_processed INTEGER DEFAULT 0,
    cards_processed INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    http_429_count INTEGER DEFAULT 0,
    duration_seconds REAL,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_decks_format ON decks(format);
CREATE INDEX IF NOT EXISTS idx_decks_source_id ON decks(source_id);
CREATE INDEX IF NOT EXISTS idx_decks_updated_at ON decks(updated_at);
CREATE INDEX IF NOT EXISTS idx_deck_cards_deck_id ON deck_cards(deck_id);
CREATE INDEX IF NOT EXISTS idx_deck_cards_oracle_id ON deck_cards(oracle_id);
CREATE INDEX IF NOT EXISTS idx_deck_cards_name ON deck_cards(name);
CREATE INDEX IF NOT EXISTS idx_deck_commanders_oracle_id ON deck_commanders(oracle_id);
CREATE INDEX IF NOT EXISTS idx_unmapped_cards_frequency ON unmapped_cards(frequency DESC);

-- Initial source data
INSERT OR IGNORE INTO sources (name) VALUES ('archidekt');
INSERT OR IGNORE INTO sources (name) VALUES ('moxfield');