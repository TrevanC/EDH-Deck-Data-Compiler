import time
import random
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """Base class for deck source adapters."""

    def __init__(self, config: Dict, source_name: str):
        self.config = config
        self.source_name = source_name
        self.source_config = config['sources'][source_name]
        self.http_config = config['http']

        # Rate limiting
        self.rate_limit = self.source_config['rate_limit']  # requests per second
        self.last_request_time = 0

        # Session for connection reuse
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.http_config['user_agent']
        })

    def _rate_limit(self):
        """Apply rate limiting between requests."""
        if self.rate_limit <= 0:
            return

        elapsed = time.time() - self.last_request_time
        min_interval = 1.0 / self.rate_limit

        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            # Add small random jitter to avoid thundering herd
            sleep_time += random.uniform(0, min_interval * 0.1)
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def _make_request(self, url: str, **kwargs) -> requests.Response:
        """Make a rate-limited HTTP request with retries."""
        self._rate_limit()

        max_retries = self.http_config['max_retries']
        backoff_base = self.http_config['backoff_base']
        timeout = kwargs.get('timeout', self.http_config['timeout'])

        for attempt in range(max_retries + 1):
            try:
                response = self.session.get(url, timeout=timeout, **kwargs)

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited by {self.source_name}, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response

            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    wait_time = (backoff_base ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{max_retries + 1}): {e}, "
                        f"retrying in {wait_time:.1f}s"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {max_retries + 1} attempts: {e}")
                    raise

    @abstractmethod
    def discover_decks(self, **kwargs) -> List[str]:
        """
        Discover deck IDs from the source.
        Returns list of source-specific deck IDs.
        """
        pass

    @abstractmethod
    def fetch_deck(self, deck_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single deck by ID.
        Returns normalized deck data or None if failed.
        """
        pass

    @abstractmethod
    def fetch_deck_bulk(self, page: int, page_size: int) -> List[Dict[str, Any]]:
        """
        Fetch multiple decks in bulk (if supported).
        Returns list of normalized deck data.
        """
        pass

    def normalize_deck_data(self, raw_deck: Dict) -> Dict[str, Any]:
        """
        Normalize raw deck data to standard format.
        Override in subclasses for source-specific normalization.
        """
        return {
            'title': raw_deck.get('title', raw_deck.get('name', '')),
            'author': raw_deck.get('author', raw_deck.get('user', '')),
            'url': raw_deck.get('url', ''),
            'format': raw_deck.get('format', 'Commander'),
            'cards': raw_deck.get('cards', []),
            'commanders': raw_deck.get('commanders', []),
            'extra': {k: v for k, v in raw_deck.items()
                     if k not in ['title', 'author', 'url', 'format', 'cards', 'commanders']}
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics."""
        return {
            'source_name': self.source_name,
            'rate_limit': self.rate_limit,
            'enabled': self.source_config.get('enabled', True)
        }