import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from ..db import DatabaseManager
from ..adapters import ArchidektAdapter, MoxfieldAdapter
from ..normalization import CardNormalizer

logger = logging.getLogger(__name__)


class IngestionJob:
    """Handles ingestion operations for deck sources."""

    def __init__(self, config: Dict, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.normalizer = CardNormalizer(config, db_manager)

        # Initialize adapters
        self.adapters = {}
        if config['sources']['archidekt']['enabled']:
            self.adapters['archidekt'] = ArchidektAdapter(config)

        if config['sources']['moxfield']['enabled']:
            self.adapters['moxfield'] = MoxfieldAdapter(config)

    def run_archidekt_incremental(self) -> Dict[str, Any]:
        """Run incremental Archidekt ingestion."""
        logger.info("Starting Archidekt incremental ingestion")
        start_time = datetime.utcnow()

        try:
            if 'archidekt' not in self.adapters:
                return {
                    'status': 'skipped',
                    'message': 'Archidekt adapter not enabled'
                }

            adapter = self.adapters['archidekt']
            max_pages = self.config['sources']['archidekt'].get('max_pages', 50)

            total_decks = 0
            total_cards = 0
            errors = 0

            # Fetch recent decks
            for page in range(1, min(max_pages, 10) + 1):  # Limit for incremental
                try:
                    decks = adapter.fetch_deck_bulk(page)

                    if not decks:
                        logger.info(f"No more decks found at page {page}, stopping")
                        break

                    for deck_data in decks:
                        try:
                            # Insert deck
                            deck_id = self.db.upsert_deck(
                                'archidekt',
                                deck_data['source_deck_id'],
                                deck_data
                            )

                            # Insert cards
                            self.db.insert_deck_cards(deck_id, deck_data['cards'])

                            # Insert commanders
                            if deck_data['commanders']:
                                self.db.insert_deck_commanders(deck_id, deck_data['commanders'])

                            total_decks += 1
                            total_cards += len(deck_data['cards'])

                        except Exception as e:
                            logger.error(f"Failed to process Archidekt deck: {e}")
                            errors += 1

                    logger.info(f"Processed Archidekt page {page}: {len(decks)} decks")

                except Exception as e:
                    logger.error(f"Failed to fetch Archidekt page {page}: {e}")
                    errors += 1

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Log the operation
            self.db.log_ingestion(
                'archidekt', 'incremental',
                'success' if errors == 0 else 'partial',
                total_decks, total_cards, errors, 0, duration
            )

            return {
                'status': 'success',
                'decks_processed': total_decks,
                'cards_processed': total_cards,
                'errors': errors,
                'duration_seconds': duration
            }

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Archidekt incremental ingestion failed: {e}")

            self.db.log_ingestion(
                'archidekt', 'incremental', 'error',
                0, 0, 1, 0, duration, str(e)
            )

            return {
                'status': 'error',
                'message': str(e),
                'duration_seconds': duration
            }

    def run_moxfield_discovery(self) -> Dict[str, Any]:
        """Run Moxfield deck discovery."""
        logger.info("Starting Moxfield discovery")
        start_time = datetime.utcnow()

        try:
            if 'moxfield' not in self.adapters:
                return {
                    'status': 'skipped',
                    'message': 'Moxfield adapter not enabled'
                }

            adapter = self.adapters['moxfield']
            discovered_ids = adapter.discover_decks()

            # Store discovered IDs in a simple queue table or file
            # For now, we'll just return them for the export job to process
            duration = (datetime.utcnow() - start_time).total_seconds()

            self.db.log_ingestion(
                'moxfield', 'discovery', 'success',
                len(discovered_ids), 0, 0, 0, duration
            )

            return {
                'status': 'success',
                'discovered_ids': discovered_ids,
                'duration_seconds': duration
            }

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Moxfield discovery failed: {e}")

            self.db.log_ingestion(
                'moxfield', 'discovery', 'error',
                0, 0, 1, 0, duration, str(e)
            )

            return {
                'status': 'error',
                'message': str(e),
                'duration_seconds': duration
            }

    def run_moxfield_export(self, deck_ids: List[str] = None, max_decks: int = 50) -> Dict[str, Any]:
        """Run Moxfield deck export for discovered IDs."""
        logger.info("Starting Moxfield export")
        start_time = datetime.utcnow()

        try:
            if 'moxfield' not in self.adapters:
                return {
                    'status': 'skipped',
                    'message': 'Moxfield adapter not enabled'
                }

            if not deck_ids:
                # If no IDs provided, run discovery first
                discovery_result = self.run_moxfield_discovery()
                if discovery_result['status'] != 'success':
                    return discovery_result
                deck_ids = discovery_result['discovered_ids']

            adapter = self.adapters['moxfield']
            processed_ids = deck_ids[:max_decks]  # Limit for time-boxing

            total_decks = 0
            total_cards = 0
            errors = 0

            for deck_id in processed_ids:
                try:
                    deck_data = adapter.fetch_deck(deck_id)

                    if deck_data:
                        # Insert deck
                        db_deck_id = self.db.upsert_deck(
                            'moxfield',
                            deck_data['source_deck_id'],
                            deck_data
                        )

                        # Insert cards
                        self.db.insert_deck_cards(db_deck_id, deck_data['cards'])

                        # Insert commanders
                        if deck_data['commanders']:
                            self.db.insert_deck_commanders(db_deck_id, deck_data['commanders'])

                        total_decks += 1
                        total_cards += len(deck_data['cards'])

                    else:
                        errors += 1

                    # Respect rate limits
                    time.sleep(self.config['sources']['moxfield']['export']['inter_request_sleep'])

                except Exception as e:
                    logger.error(f"Failed to export Moxfield deck {deck_id}: {e}")
                    errors += 1

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Cleanup Selenium resources
            if hasattr(adapter, 'cleanup'):
                adapter.cleanup()

            self.db.log_ingestion(
                'moxfield', 'export',
                'success' if errors == 0 else 'partial',
                total_decks, total_cards, errors, 0, duration
            )

            return {
                'status': 'success',
                'decks_processed': total_decks,
                'cards_processed': total_cards,
                'errors': errors,
                'duration_seconds': duration
            }

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Moxfield export failed: {e}")

            self.db.log_ingestion(
                'moxfield', 'export', 'error',
                0, 0, 1, 0, duration, str(e)
            )

            return {
                'status': 'error',
                'message': str(e),
                'duration_seconds': duration
            }

    def run_normalization(self) -> Dict[str, Any]:
        """Run card normalization."""
        logger.info("Starting card normalization")
        start_time = datetime.utcnow()

        try:
            result = self.normalizer.normalize_all_pending(limit=5000)
            duration = (datetime.utcnow() - start_time).total_seconds()
            result['duration_seconds'] = duration

            status = 'success' if result['status'] == 'success' else 'error'
            self.db.log_ingestion(
                'scryfall', 'normalize', status,
                result.get('unique_decks_processed', 0),
                result.get('normalized', 0) + result.get('failed', 0),
                result.get('failed', 0), 0, duration,
                result.get('message', '')
            )

            return result

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Card normalization failed: {e}")

            self.db.log_ingestion(
                'scryfall', 'normalize', 'error',
                0, 0, 1, 0, duration, str(e)
            )

            return {
                'status': 'error',
                'message': str(e),
                'duration_seconds': duration
            }

    def cleanup(self):
        """Cleanup resources."""
        for adapter in self.adapters.values():
            if hasattr(adapter, 'cleanup'):
                try:
                    adapter.cleanup()
                except Exception as e:
                    logger.warning(f"Failed to cleanup adapter: {e}")