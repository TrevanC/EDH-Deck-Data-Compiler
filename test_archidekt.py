#!/usr/bin/env python3
"""
Test script to test Archidekt API endpoints and deck discovery functionality
"""

import sys
import os
import argparse
from typing import List
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.config import load_config
from src.adapters.archidekt import ArchidektAdapter

def test_archidekt():
    """Test Archidekt API endpoints."""
    
    # Load config
    config = load_config('config/config.yaml')
    
    # Create adapter
    adapter = ArchidektAdapter(config)
    
    # Test individual deck fetching with different IDs
    test_deck_ids = ['1', '10', '100', '1000', '10000']
    
    print("Testing individual deck fetching...")
    for deck_id in test_deck_ids:
        print(f"\nTesting deck ID: {deck_id}")
        try:
            deck_data = adapter.fetch_deck(deck_id)
            if deck_data:
                print(f"✅ Successfully fetched deck: {deck_data.get('title', 'Unknown')}")
                print(f"   Author: {deck_data.get('author', 'Unknown')}")
                print(f"   Cards: {len(deck_data.get('cards', []))}")
            else:
                print(f"❌ Failed to fetch deck {deck_id}")
        except Exception as e:
            print(f"❌ Error fetching deck {deck_id}: {e}")
    
    # Test bulk fetching
    print(f"\n\nTesting bulk deck fetching...")
    try:
        decks = adapter.fetch_deck_bulk(page=1, page_size=5)
        print(f"✅ Bulk fetch returned {len(decks)} decks")
        for deck in decks[:3]:  # Show first 3
            print(f"   - {deck.get('title', 'Unknown')} by {deck.get('author', 'Unknown')}")
    except Exception as e:
        print(f"❌ Bulk fetch error: {e}")


def test_deck_discovery(commander_name: str, order_by: str = "-viewCount", page: int = 1):
    """Test deck discovery by commander name."""
    
    # Load config
    config = load_config('config/config.yaml')
    
    # Create adapter
    adapter = ArchidektAdapter(config)
    
    print(f"Testing deck discovery for commander: '{commander_name}'")
    print(f"Order by: {order_by}, Page: {page}")
    print("=" * 60)
    
    try:
        # Discover deck IDs
        deck_ids = adapter.discover_deck_ids_by_commander(commander_name, order_by, page)
        
        if deck_ids:
            print(f"✅ Found {len(deck_ids)} deck IDs:")
            for i, deck_id in enumerate(deck_ids, 1):
                print(f"   {i:3d}. Deck ID: {deck_id}")
        else:
            print(f"❌ No deck IDs found for commander '{commander_name}'")
            
    except Exception as e:
        print(f"❌ Error discovering decks for '{commander_name}': {e}")


def test_top_viewed_deck_discovery(commander_name: str, max_pages: int = 3, politeness_seconds: int = 1):
    """Test top viewed deck discovery by commander name across multiple pages."""
    
    # Load config
    config = load_config('config/config.yaml')
    
    # Create adapter
    adapter = ArchidektAdapter(config)
    
    print(f"Testing top viewed deck discovery for commander: '{commander_name}'")
    print(f"Max pages: {max_pages}, Politeness: {politeness_seconds}s")
    print("=" * 60)
    
    try:
        # Discover deck IDs across multiple pages
        deck_ids = adapter.discover_top_viewed_deck_ids_by_commander(commander_name, max_pages, politeness_seconds)
        
        if deck_ids:
            print(f"✅ Found {len(deck_ids)} unique deck IDs across all pages:")
            for i, deck_id in enumerate(deck_ids, 1):
                print(f"   {i:3d}. Deck ID: {deck_id}")
        else:
            print(f"❌ No deck IDs found for commander '{commander_name}'")
            
    except Exception as e:
        print(f"❌ Error discovering top viewed decks for '{commander_name}': {e}")


def test_batch_commander_discovery(commander_names: List[str], max_pages: int = 2, politeness_seconds: int = 1):
    """Test batch commander discovery."""
    
    # Load config
    config = load_config('config/config.yaml')
    
    # Create adapter
    adapter = ArchidektAdapter(config)
    
    print(f"Testing batch commander discovery for {len(commander_names)} commanders:")
    for i, name in enumerate(commander_names, 1):
        print(f"  {i}. {name}")
    print(f"Max pages: {max_pages}, Politeness: {politeness_seconds}s")
    print("=" * 60)
    
    try:
        # Discover deck IDs for all commanders
        results = adapter.discover_deck_ids_for_commanders(commander_names, max_pages, politeness_seconds)
        
        print(f"✅ Batch discovery completed!")
        print(f"Results for {len(results)} commanders:")
        
        for result in results:
            commander = result["commander"]
            deck_ids = result["deck_ids"]
            print(f"\n📋 {commander}:")
            print(f"   Found {len(deck_ids)} deck IDs")
            if deck_ids:
                # Show first 5 deck IDs
                for i, deck_id in enumerate(deck_ids[:5], 1):
                    print(f"   {i:2d}. {deck_id}")
                if len(deck_ids) > 5:
                    print(f"   ... and {len(deck_ids) - 5} more")
            else:
                print("   No deck IDs found")
                
    except Exception as e:
        print(f"❌ Error in batch commander discovery: {e}")


def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(description='Test Archidekt adapter functionality')
    parser.add_argument('--commander', '-c', type=str, 
                       help='Commander name to search for deck IDs')
    parser.add_argument('--order-by', type=str, default='-viewCount',
                       help='Order by parameter (default: -viewCount)')
    parser.add_argument('--page', type=int, default=1,
                       help='Page number to fetch (default: 1)')
    parser.add_argument('--max-pages', type=int, default=3,
                       help='Maximum pages to fetch for top viewed search (default: 3)')
    parser.add_argument('--politeness', type=int, default=10,
                       help='Politeness delay in seconds between requests (default: 10)')
    parser.add_argument('--top-viewed', action='store_true',
                       help='Use top viewed deck discovery across multiple pages')
    parser.add_argument('--batch', action='store_true',
                       help='Test batch commander discovery with sample commanders')
    parser.add_argument('--test-api', action='store_true',
                       help='Run API endpoint tests')
    
    args = parser.parse_args()
    
    if args.commander:
        if args.top_viewed:
            test_top_viewed_deck_discovery(args.commander, args.max_pages, args.politeness)
        else:
            test_deck_discovery(args.commander, args.order_by, args.page)
    elif args.batch:
        # Test batch discovery with sample commanders
        sample_commanders = [
            "Ezuri, Claw of Progress",
            "Hearthhull, the Worldseed",
            "Atraxa, Praetors' Voice"
        ]
        test_batch_commander_discovery(sample_commanders, args.max_pages, args.politeness)
    elif args.test_api:
        test_archidekt()
    else:
        # Default behavior - test both
        print("Running all tests...")
        print("=" * 60)
        test_archidekt()
        print("\n" + "=" * 60)
        test_deck_discovery("Hearthhull, the Worldseed")
        print("\n" + "=" * 60)
        test_top_viewed_deck_discovery("Ezuri, Claw of Progress", 2, 1)
        print("\n" + "=" * 60)
        test_batch_commander_discovery(["Ezuri, Claw of Progress", "Hearthhull, the Worldseed"], 1, 1)


if __name__ == '__main__':
    main()
