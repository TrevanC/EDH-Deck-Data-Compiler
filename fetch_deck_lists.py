#!/usr/bin/env python3
"""
Deck List Fetcher

A command line tool to fetch individual deck lists from consolidated deck IDs
using the Archidekt API and save each deck list to a separate JSON file.
"""

import sys
import os
import argparse
import json
import time
import random
import requests
from pathlib import Path
from typing import List, Dict, Any


def load_consolidated_deck_ids(file_path: str) -> List[str]:
    """
    Load deck IDs from consolidated JSON file.
    
    Args:
        file_path: Path to consolidated_deck_ids.json
        
    Returns:
        List of deck IDs
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        deck_ids = data.get('unique_deck_ids', [])
        print(f"✅ Loaded {len(deck_ids)} deck IDs from {file_path}")
        return deck_ids
        
    except FileNotFoundError:
        print(f"❌ Error: File '{file_path}' not found")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading file '{file_path}': {e}")
        sys.exit(1)


def fetch_deck_data(deck_id: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Fetch deck data from Archidekt API.
    
    Args:
        deck_id: Deck ID to fetch
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary containing deck data or error info
    """
    url = f"https://archidekt.com/api/decks/{deck_id}/"
    
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        
        deck_data = response.json()
        
        # Check for API error responses
        if 'error' in deck_data:
            return {
                'deck_id': deck_id,
                'error': deck_data['error'],
                'success': False
            }
        
        return {
            'deck_id': deck_id,
            'deck_data': deck_data,
            'success': True
        }
        
    except requests.RequestException as e:
        return {
            'deck_id': deck_id,
            'error': f"Request failed: {str(e)}",
            'success': False
        }
    except json.JSONDecodeError as e:
        return {
            'deck_id': deck_id,
            'error': f"JSON decode error: {str(e)}",
            'success': False
        }
    except Exception as e:
        return {
            'deck_id': deck_id,
            'error': f"Unexpected error: {str(e)}",
            'success': False
        }


def save_deck_data(deck_data: Dict[str, Any], output_dir: Path, deck_id: str):
    """
    Save deck data to JSON file.
    
    Args:
        deck_data: Dictionary containing deck data
        output_dir: Directory to save the file
        deck_id: Deck ID for filename
    """
    filename = f"deck_{deck_id}.json"
    file_path = output_dir / filename
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(deck_data, f, indent=2, ensure_ascii=False)
        
        return str(file_path)
        
    except Exception as e:
        print(f"❌ Error saving deck {deck_id}: {e}")
        return None


def fetch_all_deck_lists(deck_ids: List[str], output_dir: str, politeness_seconds: int = 2, 
                        max_decks: int = None, start_from: int = 0):
    """
    Fetch all deck lists and save to individual JSON files.
    
    Args:
        deck_ids: List of deck IDs to fetch
        output_dir: Directory to save JSON files
        politeness_seconds: Base delay between requests
        max_decks: Maximum number of decks to fetch (None for all)
        start_from: Index to start from (for resuming)
    """
    print("🔄 Deck List Fetcher")
    print("=" * 50)
    
    # Create output directory
    output_path = Path(output_dir)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 Output directory: {output_path.absolute()}")
    except Exception as e:
        print(f"❌ Error creating output directory '{output_dir}': {e}")
        return
    
    # Determine how many decks to process
    total_decks = len(deck_ids)
    if max_decks:
        decks_to_process = min(max_decks, total_decks - start_from)
    else:
        decks_to_process = total_decks - start_from
    
    print(f"📊 Total deck IDs: {total_decks}")
    print(f"🚀 Processing {decks_to_process} decks (starting from index {start_from})")
    print(f"⏱️  Politeness delay: {politeness_seconds}s")
    print("-" * 50)
    
    successful_fetches = 0
    failed_fetches = 0
    skipped_existing = 0
    
    for i, deck_id in enumerate(deck_ids[start_from:start_from + decks_to_process], start_from + 1):
        # Check if file already exists
        filename = f"deck_{deck_id}.json"
        file_path = output_path / filename
        
        if file_path.exists():
            print(f"[{i}/{total_decks}] ⏭️  Skipping {deck_id} (file exists)")
            skipped_existing += 1
            continue
        
        print(f"[{i}/{total_decks}] 🔍 Fetching deck {deck_id}...")
        
        # Fetch deck data
        result = fetch_deck_data(deck_id)
        
        if result['success']:
            # Save successful fetch
            saved_file = save_deck_data(result, output_path, deck_id)
            if saved_file:
                successful_fetches += 1
                print(f"✅ Saved deck {deck_id} to {saved_file}")
            else:
                failed_fetches += 1
                print(f"❌ Failed to save deck {deck_id}")
        else:
            # Save error data
            error_data = {
                'deck_id': deck_id,
                'error': result['error'],
                'success': False,
                'fetch_timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            }
            saved_file = save_deck_data(error_data, output_path, deck_id)
            if saved_file:
                failed_fetches += 1
                print(f"❌ Deck {deck_id} failed: {result['error']}")
            else:
                print(f"❌ Failed to save error data for deck {deck_id}")
        
        # Add politeness delay (except for the last request)
        if i < start_from + decks_to_process:
            delay = random.uniform(politeness_seconds / 2, politeness_seconds)
            print(f"⏳ Sleeping for {delay:.2f} seconds...")
            time.sleep(delay)
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 FETCH SUMMARY")
    print("=" * 50)
    print(f"Total decks processed: {decks_to_process}")
    print(f"Successful fetches: {successful_fetches}")
    print(f"Failed fetches: {failed_fetches}")
    print(f"Skipped existing: {skipped_existing}")
    print(f"Output directory: {output_path.absolute()}")
    print("✅ Fetch completed!")


def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Fetch individual deck lists from consolidated deck IDs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fetch_deck_lists.py consolidated_deck_ids.json deck_lists/
  python fetch_deck_lists.py consolidated_deck_ids.json deck_lists/ --politeness 3
  python fetch_deck_lists.py consolidated_deck_ids.json deck_lists/ --max-decks 100
  python fetch_deck_lists.py consolidated_deck_ids.json deck_lists/ --start-from 50 --max-decks 50

API Endpoint:
  https://archidekt.com/api/decks/{deck_id}/
        """
    )
    
    parser.add_argument('input_file', 
                       help='Consolidated deck IDs JSON file')
    parser.add_argument('output_dir', 
                       help='Output directory for individual deck JSON files')
    parser.add_argument('--politeness', type=int, default=2,
                       help='Politeness delay in seconds between requests (default: 2)')
    parser.add_argument('--max-decks', type=int, default=None,
                       help='Maximum number of decks to fetch (default: all)')
    parser.add_argument('--start-from', type=int, default=0,
                       help='Index to start from (for resuming, default: 0)')
    
    args = parser.parse_args()
    
    # Validate input file
    if not os.path.exists(args.input_file):
        print(f"❌ Error: Input file '{args.input_file}' does not exist")
        sys.exit(1)
    
    # Load deck IDs
    deck_ids = load_consolidated_deck_ids(args.input_file)
    
    if not deck_ids:
        print("❌ No deck IDs found in input file")
        sys.exit(1)
    
    # Fetch all deck lists
    fetch_all_deck_lists(
        deck_ids=deck_ids,
        output_dir=args.output_dir,
        politeness_seconds=args.politeness,
        max_decks=args.max_decks,
        start_from=args.start_from
    )


if __name__ == '__main__':
    main()
