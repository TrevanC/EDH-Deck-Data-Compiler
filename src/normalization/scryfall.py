import json
import os
import re
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
import logging

logger = logging.getLogger(__name__)


class ScryfallNormalizer:
    def __init__(self, config: Dict):
        self.config = config['scryfall']
        self.http_config = config['http']
        self.oracle_cache = {}  # name -> oracle_id mapping
        self.last_updated = None

    def download_oracle_bulk(self) -> bool:
        """Download the latest Scryfall Oracle bulk data."""
        try:
            logger.info("Fetching Scryfall bulk data info")

            # Get bulk data info
            response = requests.get(
                self.config['oracle_bulk_url'],
                headers={'User-Agent': self.http_config['user_agent']},
                timeout=self.http_config['timeout']
            )
            response.raise_for_status()

            bulk_info = response.json()
            download_url = bulk_info['download_uri']

            # Check if we need to update
            local_path = self.config['local_bulk_path']
            if os.path.exists(local_path):
                local_mtime = datetime.fromtimestamp(os.path.getmtime(local_path))
                remote_updated = datetime.fromisoformat(
                    bulk_info['updated_at'].replace('Z', '+00:00')
                )

                if local_mtime >= remote_updated.replace(tzinfo=None):
                    logger.info("Local Oracle bulk data is up to date")
                    return True

            # Download the bulk data
            logger.info(f"Downloading Oracle bulk data from {download_url}")
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            response = requests.get(
                download_url,
                headers={'User-Agent': self.http_config['user_agent']},
                timeout=300,  # 5 minute timeout for large file
                stream=True
            )
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info("Oracle bulk data downloaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to download Oracle bulk data: {e}")
            return False

    def build_name_resolver(self) -> bool:
        """Build the card name -> oracle_id resolver from bulk data."""
        try:
            local_path = self.config['local_bulk_path']

            if not os.path.exists(local_path):
                logger.error("Oracle bulk data not found, downloading...")
                if not self.download_oracle_bulk():
                    return False

            logger.info("Building card name resolver")

            self.oracle_cache.clear()
            with open(local_path, 'r', encoding='utf-8') as f:
                cards = json.load(f)

            for card in cards:
                oracle_id = card['oracle_id']

                # Add the main name
                name = card['name']
                self.oracle_cache[self._normalize_name(name)] = oracle_id

                # Handle double-faced cards (DFC)
                if 'card_faces' in card:
                    for face in card['card_faces']:
                        face_name = face.get('name')
                        if face_name:
                            self.oracle_cache[self._normalize_name(face_name)] = oracle_id

                # Handle split cards and other special cases
                if '//' in name:
                    # Split card - add both sides
                    parts = [p.strip() for p in name.split('//')]
                    for part in parts:
                        self.oracle_cache[self._normalize_name(part)] = oracle_id

                # Add alternative names if present
                if 'printed_name' in card and card['printed_name']:
                    printed_name = card['printed_name']
                    self.oracle_cache[self._normalize_name(printed_name)] = oracle_id

            self.last_updated = datetime.utcnow()
            logger.info(f"Built resolver with {len(self.oracle_cache)} name mappings")
            return True

        except Exception as e:
            logger.error(f"Failed to build name resolver: {e}")
            return False

    def _normalize_name(self, name: str) -> str:
        """Normalize card name for consistent lookup."""
        if not name:
            return ""

        # Convert to lowercase
        normalized = name.lower()

        # Remove extra whitespace
        normalized = ' '.join(normalized.split())

        # Handle common variations
        normalized = normalized.replace('æ', 'ae')
        normalized = normalized.replace('é', 'e')
        normalized = normalized.replace('', "'")

        # Remove punctuation that doesn't affect card identity
        normalized = re.sub(r'["""]', '"', normalized)

        return normalized

    def resolve_card_name(self, name: str) -> Optional[str]:
        """Resolve a card name to its oracle_id."""
        if not self.oracle_cache:
            if not self.build_name_resolver():
                return None

        normalized = self._normalize_name(name)

        # Direct lookup
        if normalized in self.oracle_cache:
            return self.oracle_cache[normalized]

        # Try some common variations
        variations = [
            # Remove quotes
            normalized.replace('"', ''),
            # Try without apostrophes
            normalized.replace("'", ''),
            # Try with different apostrophes
            normalized.replace("'", "'"),
            # Remove commas
            normalized.replace(',', ''),
        ]

        for variation in variations:
            if variation in self.oracle_cache:
                # Cache the successful lookup for future use
                self.oracle_cache[normalized] = self.oracle_cache[variation]
                return self.oracle_cache[variation]

        # Special handling for basic lands
        basic_lands = {
            'plains': 'bc71ebf6-2056-41f7-be35-b2e5c34afa99',
            'island': '8cff7b58-bd58-4911-a6a3-bdd1dbf71a72',
            'swamp': 'a3fb7228-e76b-4e96-a40e-20b5fed75685',
            'mountain': '8cf3dce3-01e4-4fe2-ac44-b13b6fe8799e',
            'forest': 'b34bb2dc-c1af-4d77-b0b3-a0fb342a5fc6'
        }

        if normalized in basic_lands:
            oracle_id = basic_lands[normalized]
            self.oracle_cache[normalized] = oracle_id
            return oracle_id

        return None

    def needs_refresh(self) -> bool:
        """Check if the oracle data needs to be refreshed."""
        if not self.last_updated:
            return True

        refresh_hours = self.config['refresh_cadence_hours']
        return (datetime.utcnow() - self.last_updated) > timedelta(hours=refresh_hours)

    def get_cache_stats(self) -> Dict:
        """Get statistics about the name resolver cache."""
        return {
            'total_mappings': len(self.oracle_cache),
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'needs_refresh': self.needs_refresh()
        }