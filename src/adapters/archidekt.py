import logging
import re
import requests
import time
import random
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
from .base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class ArchidektAdapter(BaseAdapter):
    """Adapter for Archidekt deck data."""

    def __init__(self, config: Dict):
        super().__init__(config, 'archidekt')
        self.base_url = self.source_config['base_url']

    def discover_decks(self, **kwargs) -> List[str]:
        """
        Discover deck IDs by browsing public decks.
        For Archidekt, we'll use bulk fetching instead.
        """
        # Archidekt discovery is better done through bulk fetching
        # since they have paginated APIs that return deck data directly
        return []

    def discover_deck_ids_by_commander(self, commander_name: str, order_by: str = "-viewCount", page: int = 1) -> List[str]:
        """
        Discover deck IDs by searching for a specific commander using the search endpoint.
        
        Args:
            commander_name: The name of the commander to search for (used as-is, no regex modification)
            order_by: Ordering parameter (default: "-viewCount")
            page: Page number to fetch (default: 1)
            
        Returns:
            List of deck IDs (as strings) found for this commander
        """
        try:
            # Use the search endpoint with GET parameters
            url = "https://archidekt.com/search/decks"
            
            # Set up query parameters
            params = {
                'commanderName': commander_name,  # Use commander name as-is
                'orderBy': order_by,
                'page': page
            }
            
            logger.info(f"Searching for commander '{commander_name}' with params: {params}")
            
            # Fetch the webpage with parameters
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # Parse the HTML content to find deck links
            deck_ids = self._extract_deck_ids_from_html(response.text)
            
            logger.info(f"Found {len(deck_ids)} deck IDs for commander '{commander_name}'")
            return deck_ids
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch commander search page for '{commander_name}': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error discovering decks for '{commander_name}': {e}")
            return []

    def discover_top_viewed_deck_ids_by_commander(self, commander_name: str, max_pages: int = 5, politeness_seconds: int = 5) -> List[str]:
        """
        Discover deck IDs by searching for a specific commander across multiple pages, ordered by view count.
        
        Args:
            commander_name: The name of the commander to search for
            max_pages: Maximum number of pages to fetch (default: 5)
            politeness_seconds: Base delay in seconds between requests (default: 2)
                              Actual delay will be random between politeness_seconds/2 and politeness_seconds
            
        Returns:
            List of all unique deck IDs found across all pages
        """
        all_deck_ids = []
        page = 1
        
        logger.info(f"Starting paginated search for commander '{commander_name}' (max {max_pages} pages)")
        
        while page <= max_pages:
            logger.info(f"Fetching page {page} for commander '{commander_name}'")
            
            try:
                # Fetch deck IDs for current page
                page_deck_ids = self.discover_deck_ids_by_commander(
                    commander_name=commander_name,
                    order_by="-viewCount",
                    page=page
                )
                
                # If no deck IDs found, stop pagination
                if not page_deck_ids:
                    logger.info(f"No deck IDs found on page {page}, stopping pagination")
                    break
                
                # Add new deck IDs to our collection
                all_deck_ids.extend(page_deck_ids)
                logger.info(f"Page {page}: Found {len(page_deck_ids)} deck IDs, total so far: {len(all_deck_ids)}")
                
                # If we've reached max pages, stop
                if page >= max_pages:
                    logger.info(f"Reached maximum pages ({max_pages}), stopping pagination")
                    break
                
                # Add politeness delay before next request (except for the last page)
                if page < max_pages:
                    delay = random.uniform(politeness_seconds / 2, politeness_seconds)
                    logger.debug(f"Sleeping for {delay:.2f} seconds before next request")
                    time.sleep(delay)
                
                page += 1
                
            except Exception as e:
                logger.error(f"Error fetching page {page} for commander '{commander_name}': {e}")
                break
        
        # Remove duplicates and return
        unique_deck_ids = list(set(all_deck_ids))
        logger.info(f"Completed paginated search for '{commander_name}': {len(unique_deck_ids)} unique deck IDs across {page-1} pages")
        
        return unique_deck_ids

    def discover_deck_ids_for_commanders(self, commander_names: List[str], max_pages: int = 5, politeness_seconds: int = 5) -> List[Dict[str, Any]]:
        """
        Discover deck IDs for multiple commanders and return structured data.
        
        Args:
            commander_names: List of commander names to search for
            max_pages: Maximum number of pages to fetch per commander (default: 5)
            politeness_seconds: Base delay in seconds between requests (default: 5)
            
        Returns:
            List of dictionaries with format:
            [
                {"commander": "Commander Name", "deck_ids": ["123", "456", "789"]},
                ...
            ]
        """
        results = []
        total_commanders = len(commander_names)
        
        logger.info(f"Starting batch discovery for {total_commanders} commanders")
        
        for i, commander_name in enumerate(commander_names, 1):
            logger.info(f"Processing commander {i}/{total_commanders}: '{commander_name}'")
            
            try:
                # Discover deck IDs for this commander
                deck_ids = self.discover_top_viewed_deck_ids_by_commander(
                    commander_name=commander_name,
                    max_pages=max_pages,
                    politeness_seconds=politeness_seconds
                )
                
                # Create result dictionary
                result = {
                    "commander": commander_name,
                    "deck_ids": deck_ids
                }
                
                results.append(result)
                logger.info(f"Commander '{commander_name}': Found {len(deck_ids)} deck IDs")
                
            except Exception as e:
                logger.error(f"Error processing commander '{commander_name}': {e}")
                # Still add the commander with empty deck_ids list
                result = {
                    "commander": commander_name,
                    "deck_ids": []
                }
                results.append(result)
        
        logger.info(f"Completed batch discovery: {len(results)} commanders processed")
        return results

    def _extract_deck_ids_from_html(self, html_content: str) -> List[str]:
        """
        Extract deck IDs from HTML content by finding href patterns like '/decks/1234/name'.
        
        Args:
            html_content: The HTML content to parse
            
        Returns:
            List of unique deck IDs found in the HTML
        """
        try:
            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find all links with href attributes
            links = soup.find_all('a', href=True)
            
            deck_ids = []
            for link in links:
                href = link.get('href', '')
                
                # Check if href matches the pattern /decks/1234/name
                if href.startswith('/decks/') and '/' in href[7:]:
                    # Extract the deck ID (numeric part after /decks/)
                    parts = href.split('/')
                    if len(parts) >= 3 and parts[2].isdigit():
                        deck_ids.append(parts[2])
            
            # Remove duplicates and return
            unique_deck_ids = list(set(deck_ids))
            
            logger.debug(f"Extracted {len(unique_deck_ids)} unique deck IDs from HTML")
            return unique_deck_ids
            
        except Exception as e:
            logger.error(f"Error parsing HTML with BeautifulSoup: {e}")
            # Fallback to regex method
            return self._extract_deck_ids_with_regex(html_content)
    
    def _extract_deck_ids_with_regex(self, html_content: str) -> List[str]:
        """
        Fallback method using regex to extract deck IDs from HTML content.
        
        Args:
            html_content: The HTML content to parse
            
        Returns:
            List of unique deck IDs found in the HTML
        """
        # Pattern to match href="/decks/1234/name" or similar patterns
        # This will capture the deck ID (numeric part) from the href
        deck_pattern = r'href=["\']/decks/(\d+)/[^"\']*["\']'
        
        # Find all matches
        matches = re.findall(deck_pattern, html_content)
        
        # Convert to list of unique strings and remove duplicates
        deck_ids = list(set(matches))
        
        logger.debug(f"Extracted {len(deck_ids)} unique deck IDs from HTML using regex")
        return deck_ids

    def fetch_deck(self, deck_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single deck by ID."""
        try:
            # Use the correct endpoint for individual deck fetching
            url = f"https://archidekt.com/api/decks/{deck_id}/"
            response = self._make_request(url)
            deck_data = response.json()

            # Check for error responses
            if 'error' in deck_data:
                logger.warning(f"Archidekt API error for deck {deck_id}: {deck_data['error']}")
                return None

            return self.normalize_archidekt_deck(deck_data)

        except Exception as e:
            logger.error(f"Failed to fetch Archidekt deck {deck_id}: {e}")
            return None

    def fetch_deck_bulk(self, page: int = 1, page_size: int = None) -> List[Dict[str, Any]]:
        """Fetch multiple decks using Archidekt's paginated API."""
        if page_size is None:
            page_size = self.source_config['page_size']

        try:
            # Try the newer API endpoint format
            url = "https://archidekt.com/api/decks/"

            params = {
                'page': page,
                'pageSize': page_size,
                'formats': self.source_config['format_filter'],  # Commander
                'orderBy': '-createdAt',  # Most recent first
                'owner__isnull': 'false',  # Only decks with owners
                'public': 'true'  # Public decks only
            }

            response = self._make_request(url, params=params)
            data = response.json()

            # Check for error responses
            if 'error' in data:
                logger.warning(f"Archidekt API error: {data['error']}")
                return []

            decks = []
            for deck_data in data.get('results', []):
                try:
                    normalized_deck = self.normalize_archidekt_deck(deck_data)
                    if normalized_deck:
                        decks.append(normalized_deck)
                except Exception as e:
                    logger.warning(f"Failed to normalize Archidekt deck: {e}")

            logger.info(f"Fetched {len(decks)} decks from Archidekt page {page}")
            return decks

        except Exception as e:
            logger.error(f"Failed to fetch Archidekt bulk page {page}: {e}")
            return []

    def normalize_archidekt_deck(self, raw_deck: Dict) -> Optional[Dict[str, Any]]:
        """Normalize Archidekt-specific deck format."""
        try:
            deck_id = raw_deck['id']

            # Extract basic info
            deck_info = {
                'source_deck_id': str(deck_id),
                'title': raw_deck.get('name', ''),
                'author': raw_deck.get('owner', {}).get('username', ''),
                'url': f"https://archidekt.com/decks/{deck_id}/",
                'format': 'Commander',  # We're filtering for Commander
                'cards': [],
                'commanders': [],
                'extra': {
                    'archidekt_id': deck_id,
                    'featured': raw_deck.get('featured', False),
                    'private': raw_deck.get('private', True),
                    'views': raw_deck.get('viewCount', 0),
                    'created_at': raw_deck.get('createdAt'),
                    'updated_at': raw_deck.get('updatedAt')
                }
            }

            # Parse cards
            cards_data = raw_deck.get('cards', [])
            for card_entry in cards_data:
                card_info = card_entry.get('card', {})
                quantity = card_entry.get('quantity', 1)

                # Determine if this is a commander
                categories = card_entry.get('categories') or []
                is_commander = 'Commander' in categories or 'commander' in categories

                card_data = {
                    'name': card_info.get('name', ''),
                    'qty': quantity,
                    'zone': 'command' if is_commander else 'main'
                }

                # Add oracle_id if available
                oracle_id = card_info.get('oracleId')
                if oracle_id:
                    card_data['oracle_id'] = oracle_id

                deck_info['cards'].append(card_data)

                # Add to commanders list if it's a commander
                if is_commander:
                    commander_data = {
                        'name': card_data['name'],
                        'oracle_id': oracle_id
                    }
                    deck_info['commanders'].append(commander_data)

            # Validate deck has reasonable card count for EDH
            total_cards = sum(card['qty'] for card in deck_info['cards'])
            if total_cards < 80 or total_cards > 120:
                logger.warning(
                    f"Archidekt deck {deck_id} has unusual card count: {total_cards}"
                )

            # Ensure we have at least one commander
            if not deck_info['commanders']:
                logger.warning(f"Archidekt deck {deck_id} has no identified commanders")

            return deck_info

        except Exception as e:
            logger.error(f"Failed to normalize Archidekt deck data: {e}")
            return None

    def get_total_pages(self, page_size: int = None) -> int:
        """Get the total number of pages available."""
        if page_size is None:
            page_size = self.source_config['page_size']

        try:
            # Make a request to get the total count
            url = "https://archidekt.com/api/decks/cards/"
            params = {
                'page': 1,
                'pageSize': 1,  # Minimal request just to get count
                'formats': self.source_config['format_filter'],
                'public': 'true'
            }

            response = self._make_request(url, params=params)
            data = response.json()

            total_count = data.get('count', 0)
            total_pages = (total_count + page_size - 1) // page_size

            logger.info(f"Archidekt has ~{total_count} total decks, {total_pages} pages")
            return total_pages

        except Exception as e:
            logger.error(f"Failed to get Archidekt total pages: {e}")
            return 0

    def fetch_incremental(self, since_hours: int = 24) -> List[Dict[str, Any]]:
        """Fetch decks updated since a specific time."""
        # Archidekt doesn't have great incremental support in their public API
        # For now, we'll just fetch the first few pages of recent decks
        max_pages = min(10, self.source_config.get('max_pages', 1000))

        all_decks = []
        for page in range(1, max_pages + 1):
            decks = self.fetch_deck_bulk(page)
            if not decks:
                break
            all_decks.extend(decks)

        logger.info(f"Fetched {len(all_decks)} recent decks from Archidekt")
        return all_decks