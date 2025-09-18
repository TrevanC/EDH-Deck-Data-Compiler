import logging
from typing import Dict, List, Optional, Any
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import time
from .base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class MoxfieldAdapter(BaseAdapter):
    """Adapter for Moxfield deck data with Cloudflare handling."""

    def __init__(self, config: Dict):
        super().__init__(config, 'moxfield')
        self.base_url = self.source_config['base_url']
        self.driver = None
        self.use_selenium = False

    def _init_selenium(self):
        """Initialize Selenium webdriver for Cloudflare bypass."""
        if self.driver is not None:
            return

        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--user-agent=' + self.http_config['user_agent'])

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("Selenium Chrome driver initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Selenium: {e}")
            raise

    def _selenium_request(self, url: str) -> Optional[str]:
        """Make request using Selenium to handle Cloudflare."""
        try:
            if self.driver is None:
                self._init_selenium()

            self.driver.get(url)

            # Wait for page to load and Cloudflare to clear
            wait = WebDriverWait(self.driver, 30)

            # Check if we got Cloudflare challenge
            if "cloudflare" in self.driver.page_source.lower():
                logger.info("Cloudflare challenge detected, waiting...")
                time.sleep(10)  # Give Cloudflare time to resolve

            # Wait for actual content to load
            wait.until(lambda driver: len(driver.page_source) > 1000)

            return self.driver.page_source

        except Exception as e:
            logger.error(f"Selenium request failed: {e}")
            return None

    def discover_decks(self, **kwargs) -> List[str]:
        """Discover public Moxfield deck IDs."""
        discovered_ids = []

        # Try popular commanders first
        popular_commanders = self.source_config['discovery']['popular_commanders']
        max_pages = self.source_config['discovery']['max_pages']

        for commander in popular_commanders[:3]:  # Limit to avoid long discovery
            try:
                deck_ids = self._discover_by_commander(commander, max_pages=3)
                discovered_ids.extend(deck_ids)

                if len(discovered_ids) >= 100:  # Reasonable limit
                    break

            except Exception as e:
                logger.warning(f"Failed to discover decks for commander {commander}: {e}")

        logger.info(f"Discovered {len(discovered_ids)} Moxfield deck IDs")
        return list(set(discovered_ids))  # Remove duplicates

    def _discover_by_commander(self, commander_name: str, max_pages: int = 3) -> List[str]:
        """Discover deck IDs by commander name."""
        deck_ids = []

        try:
            # Use Moxfield search/browse API if available
            search_url = f"{self.base_url}/v2/decks/search"
            params = {
                'format': 'commander',
                'commander': commander_name,
                'page': 1,
                'pageSize': 50
            }

            for page in range(1, max_pages + 1):
                params['page'] = page

                try:
                    response = self._make_request(search_url, params=params)
                    data = response.json()

                    decks = data.get('data', [])
                    if not decks:
                        break

                    for deck in decks:
                        deck_id = deck.get('publicId')
                        if deck_id and deck.get('visibility') == 'public':
                            deck_ids.append(deck_id)

                except Exception as e:
                    logger.warning(f"HTTP discovery failed, trying Selenium: {e}")
                    self.use_selenium = True
                    break

            if self.use_selenium and not deck_ids:
                # Fallback to Selenium-based discovery
                deck_ids = self._selenium_discover_by_commander(commander_name, max_pages)

        except Exception as e:
            logger.error(f"Discovery failed for {commander_name}: {e}")

        return deck_ids

    def _selenium_discover_by_commander(self, commander_name: str, max_pages: int) -> List[str]:
        """Discover deck IDs using Selenium (fallback)."""
        deck_ids = []

        try:
            search_url = f"https://www.moxfield.com/decks/browse/commander/{commander_name.replace(' ', '+')}"

            html_content = self._selenium_request(search_url)
            if not html_content:
                return deck_ids

            # Parse deck links from HTML
            # This is a simplified parser - in practice, you'd need more robust HTML parsing
            import re
            deck_pattern = r'/decks/([a-zA-Z0-9_-]+)'
            matches = re.findall(deck_pattern, html_content)

            for match in matches[:20]:  # Limit per commander
                if len(match) > 5:  # Basic validation of deck ID format
                    deck_ids.append(match)

        except Exception as e:
            logger.error(f"Selenium discovery failed: {e}")

        return deck_ids

    def fetch_deck(self, deck_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single Moxfield deck."""
        try:
            # Try API first
            api_url = f"{self.base_url}/v2/decks/all/{deck_id}"

            try:
                response = self._make_request(api_url)
                deck_data = response.json()
                return self.normalize_moxfield_deck(deck_data, deck_id)

            except Exception as e:
                logger.warning(f"API fetch failed for {deck_id}, trying Selenium: {e}")

                # Fallback to Selenium
                if not self.use_selenium:
                    self.use_selenium = True

                return self._selenium_fetch_deck(deck_id)

        except Exception as e:
            logger.error(f"Failed to fetch Moxfield deck {deck_id}: {e}")
            return None

    def _selenium_fetch_deck(self, deck_id: str) -> Optional[Dict[str, Any]]:
        """Fetch deck using Selenium."""
        try:
            deck_url = f"https://www.moxfield.com/decks/{deck_id}"
            html_content = self._selenium_request(deck_url)

            if not html_content:
                return None

            # Extract JSON data from the page
            # Moxfield embeds deck data in script tags
            import re
            json_pattern = r'window\.__INITIAL_STATE__\s*=\s*({.*?});'
            match = re.search(json_pattern, html_content, re.DOTALL)

            if match:
                json_data = json.loads(match.group(1))
                deck_data = json_data.get('deck', {}).get('deck', {})
                return self.normalize_moxfield_deck(deck_data, deck_id)

        except Exception as e:
            logger.error(f"Selenium fetch failed for {deck_id}: {e}")

        return None

    def normalize_moxfield_deck(self, raw_deck: Dict, deck_id: str) -> Optional[Dict[str, Any]]:
        """Normalize Moxfield-specific deck format."""
        try:
            deck_info = {
                'source_deck_id': deck_id,
                'title': raw_deck.get('name', ''),
                'author': raw_deck.get('createdByUser', {}).get('userName', ''),
                'url': f"https://www.moxfield.com/decks/{deck_id}",
                'format': raw_deck.get('format', 'commander'),
                'cards': [],
                'commanders': [],
                'extra': {
                    'moxfield_id': deck_id,
                    'description': raw_deck.get('description', ''),
                    'visibility': raw_deck.get('visibility', 'public'),
                    'likes': raw_deck.get('likeCount', 0),
                    'views': raw_deck.get('viewCount', 0),
                    'created_at': raw_deck.get('createdAtUtc'),
                    'updated_at': raw_deck.get('lastUpdatedAtUtc')
                }
            }

            # Parse commanders
            commanders = raw_deck.get('commanders', {})
            for cmd_data in commanders.values():
                card_data = cmd_data.get('card', {})
                commander_info = {
                    'name': card_data.get('name', ''),
                    'oracle_id': card_data.get('oracleId')
                }
                deck_info['commanders'].append(commander_info)

            # Parse main deck
            mainboard = raw_deck.get('mainboard', {})
            for card_data in mainboard.values():
                card_info = card_data.get('card', {})
                quantity = card_data.get('quantity', 1)

                card_entry = {
                    'name': card_info.get('name', ''),
                    'qty': quantity,
                    'zone': 'main',
                    'oracle_id': card_info.get('oracleId')
                }
                deck_info['cards'].append(card_entry)

            # Add commanders to cards list as well
            for cmd in deck_info['commanders']:
                cmd_entry = {
                    'name': cmd['name'],
                    'qty': 1,
                    'zone': 'command',
                    'oracle_id': cmd['oracle_id']
                }
                deck_info['cards'].append(cmd_entry)

            # Validate deck
            total_main = sum(c['qty'] for c in deck_info['cards'] if c['zone'] == 'main')
            if total_main < 80 or total_main > 120:
                logger.warning(f"Moxfield deck {deck_id} has unusual card count: {total_main}")

            return deck_info

        except Exception as e:
            logger.error(f"Failed to normalize Moxfield deck {deck_id}: {e}")
            return None

    def fetch_deck_bulk(self, page: int, page_size: int) -> List[Dict[str, Any]]:
        """Moxfield doesn't support bulk fetching - use discovery + individual fetches."""
        # This method is not optimal for Moxfield
        # Better to use discover_decks() followed by individual fetch_deck() calls
        return []

    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"Failed to cleanup Selenium driver: {e}")
            finally:
                self.driver = None