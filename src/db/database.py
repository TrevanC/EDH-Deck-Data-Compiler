import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from contextlib import contextmanager


class DatabaseManager:
    def __init__(self, db_path: str, wal_mode: bool = True):
        self.db_path = db_path
        self.wal_mode = wal_mode
        self._init_db()

    def _init_db(self):
        """Initialize database with schema."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with self.get_connection() as conn:
            if self.wal_mode:
                conn.execute("PRAGMA journal_mode=WAL")

            # Read and execute schema
            schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
            with open(schema_path, 'r') as f:
                schema = f.read()

            conn.executescript(schema)

    @contextmanager
    def get_connection(self):
        """Get database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def get_source_id(self, source_name: str) -> int:
        """Get or create source ID."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id FROM sources WHERE name = ?",
                (source_name,)
            )
            row = cursor.fetchone()
            if row:
                return row['id']

            cursor = conn.execute(
                "INSERT INTO sources (name) VALUES (?)",
                (source_name,)
            )
            conn.commit()
            return cursor.lastrowid

    def upsert_deck(self, source_name: str, source_deck_id: str,
                   deck_data: Dict[str, Any]) -> int:
        """Insert or update deck record."""
        source_id = self.get_source_id(source_name)

        with self.get_connection() as conn:
            now = datetime.utcnow()

            # Try to get existing deck
            cursor = conn.execute(
                "SELECT id FROM decks WHERE source_id = ? AND source_deck_id = ?",
                (source_id, source_deck_id)
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing deck
                conn.execute("""
                    UPDATE decks
                    SET title = ?, author = ?, url = ?, extra = ?,
                        updated_at = ?, last_seen_at = ?, fetched_at = ?
                    WHERE id = ?
                """, (
                    deck_data.get('title'),
                    deck_data.get('author'),
                    deck_data.get('url'),
                    json.dumps(deck_data.get('extra', {})),
                    now, now, now,
                    existing['id']
                ))
                deck_id = existing['id']
            else:
                # Insert new deck
                cursor = conn.execute("""
                    INSERT INTO decks
                    (source_id, source_deck_id, format, title, author, url, extra, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    source_id, source_deck_id,
                    deck_data.get('format', 'Commander'),
                    deck_data.get('title'),
                    deck_data.get('author'),
                    deck_data.get('url'),
                    json.dumps(deck_data.get('extra', {})),
                    now
                ))
                deck_id = cursor.lastrowid

            conn.commit()
            return deck_id

    def insert_deck_cards(self, deck_id: int, cards: List[Dict[str, Any]],
                         clear_existing: bool = True):
        """Insert cards for a deck."""
        with self.get_connection() as conn:
            if clear_existing:
                conn.execute("DELETE FROM deck_cards WHERE deck_id = ?", (deck_id,))

            card_rows = []
            for card in cards:
                card_rows.append((
                    deck_id,
                    card['name'],
                    card.get('qty', 1),
                    card.get('oracle_id'),
                    card.get('zone', 'main')
                ))

            conn.executemany("""
                INSERT INTO deck_cards (deck_id, name, qty, oracle_id, zone)
                VALUES (?, ?, ?, ?, ?)
            """, card_rows)

            conn.commit()

    def insert_deck_commanders(self, deck_id: int, commanders: List[Dict[str, Any]]):
        """Insert commanders for a deck."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM deck_commanders WHERE deck_id = ?", (deck_id,))

            if commanders:
                commander_rows = []
                for cmd in commanders:
                    commander_rows.append((
                        deck_id,
                        cmd.get('oracle_id'),
                        cmd['name']
                    ))

                conn.executemany("""
                    INSERT INTO deck_commanders (deck_id, oracle_id, name)
                    VALUES (?, ?, ?)
                """, commander_rows)

            conn.commit()

    def log_unmapped_card(self, card_name: str):
        """Log a card that couldn't be normalized."""
        with self.get_connection() as conn:
            now = datetime.utcnow()
            conn.execute("""
                INSERT INTO unmapped_cards (name, frequency, first_seen, last_seen)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                frequency = frequency + 1,
                last_seen = ?
            """, (card_name, now, now, now))
            conn.commit()

    def log_ingestion(self, source_name: str, operation: str, status: str,
                     decks_processed: int = 0, cards_processed: int = 0,
                     errors_count: int = 0, http_429_count: int = 0,
                     duration_seconds: float = 0, message: str = None):
        """Log ingestion operation."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO ingestion_logs
                (source_name, operation, status, decks_processed, cards_processed,
                 errors_count, http_429_count, duration_seconds, message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_name, operation, status, decks_processed, cards_processed,
                errors_count, http_429_count, duration_seconds, message
            ))
            conn.commit()

    def get_decks_needing_normalization(self, limit: int = 1000) -> List[Dict]:
        """Get decks with cards that need oracle_id normalization."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT DISTINCT dc.deck_id, dc.name, dc.qty, dc.zone
                FROM deck_cards dc
                WHERE dc.oracle_id IS NULL
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def update_card_oracle_id(self, deck_id: int, card_name: str, oracle_id: str):
        """Update oracle_id for specific card in deck."""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE deck_cards
                SET oracle_id = ?
                WHERE deck_id = ? AND name = ?
            """, (oracle_id, deck_id, card_name))
            conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self.get_connection() as conn:
            stats = {}

            # Basic counts
            cursor = conn.execute("SELECT COUNT(*) as count FROM decks")
            stats['total_decks'] = cursor.fetchone()['count']

            cursor = conn.execute("SELECT COUNT(*) as count FROM deck_cards")
            stats['total_cards'] = cursor.fetchone()['count']

            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM deck_cards WHERE oracle_id IS NOT NULL
            """)
            stats['normalized_cards'] = cursor.fetchone()['count']

            cursor = conn.execute("SELECT COUNT(*) as count FROM unmapped_cards")
            stats['unmapped_unique_names'] = cursor.fetchone()['count']

            # Calculate normalization percentage
            if stats['total_cards'] > 0:
                stats['normalization_percentage'] = (
                    stats['normalized_cards'] / stats['total_cards'] * 100
                )
            else:
                stats['normalization_percentage'] = 0

            return stats