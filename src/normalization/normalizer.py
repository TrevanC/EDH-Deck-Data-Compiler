import logging
from typing import Dict, List, Tuple
from ..db import DatabaseManager
from .scryfall import ScryfallNormalizer

logger = logging.getLogger(__name__)


class CardNormalizer:
    def __init__(self, config: Dict, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.scryfall = ScryfallNormalizer(config)

    def normalize_deck_cards(self, deck_id: int, cards: List[Dict]) -> Tuple[int, int]:
        """
        Normalize cards for a specific deck.
        Returns (normalized_count, failed_count).
        """
        normalized_count = 0
        failed_count = 0

        for card in cards:
            card_name = card['name']
            oracle_id = self.scryfall.resolve_card_name(card_name)

            if oracle_id:
                self.db.update_card_oracle_id(deck_id, card_name, oracle_id)
                normalized_count += 1
            else:
                self.db.log_unmapped_card(card_name)
                failed_count += 1

        return normalized_count, failed_count

    def normalize_all_pending(self, limit: int = 1000) -> Dict:
        """
        Normalize all cards that don't have oracle_ids yet.
        Returns statistics about the normalization process.
        """
        logger.info("Starting normalization of pending cards")

        # Ensure we have the latest Scryfall data
        if self.scryfall.needs_refresh():
            logger.info("Refreshing Scryfall Oracle data")
            if not self.scryfall.download_oracle_bulk():
                return {
                    'status': 'error',
                    'message': 'Failed to download Scryfall data'
                }

        if not self.scryfall.build_name_resolver():
            return {
                'status': 'error',
                'message': 'Failed to build name resolver'
            }

        # Get cards that need normalization
        pending_cards = self.db.get_decks_needing_normalization(limit)

        total_normalized = 0
        total_failed = 0
        processed_decks = set()

        for card_data in pending_cards:
            deck_id = card_data['deck_id']
            card_name = card_data['name']

            # Skip if we've already processed this deck in this run
            if deck_id in processed_decks:
                continue

            oracle_id = self.scryfall.resolve_card_name(card_name)

            if oracle_id:
                self.db.update_card_oracle_id(deck_id, card_name, oracle_id)
                total_normalized += 1
            else:
                self.db.log_unmapped_card(card_name)
                total_failed += 1

            processed_decks.add(deck_id)

        logger.info(
            f"Normalization complete: {total_normalized} normalized, "
            f"{total_failed} failed"
        )

        return {
            'status': 'success',
            'normalized': total_normalized,
            'failed': total_failed,
            'unique_decks_processed': len(processed_decks),
            'scryfall_cache_stats': self.scryfall.get_cache_stats()
        }

    def normalize_batch(self, card_names: List[str]) -> Dict[str, str]:
        """
        Normalize a batch of card names.
        Returns dict mapping name -> oracle_id (or None if failed).
        """
        if self.scryfall.needs_refresh():
            if not self.scryfall.download_oracle_bulk():
                return {}

        if not self.scryfall.build_name_resolver():
            return {}

        results = {}
        for name in card_names:
            oracle_id = self.scryfall.resolve_card_name(name)
            results[name] = oracle_id

        return results

    def get_normalization_stats(self) -> Dict:
        """Get current normalization statistics."""
        db_stats = self.db.get_stats()
        scryfall_stats = self.scryfall.get_cache_stats()

        return {
            'database': db_stats,
            'scryfall_cache': scryfall_stats,
            'needs_refresh': self.scryfall.needs_refresh()
        }