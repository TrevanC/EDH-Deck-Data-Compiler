#!/usr/bin/env python3
"""
Archidekt Commander Crawler

A command line tool to crawl deck data for multiple commanders from Archidekt.
Reads commander names from an input file and saves each commander's deck data to separate JSON files.
"""

import sys
import os
import argparse
import json
import time
from pathlib import Path
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.config import load_config
from src.adapters.archidekt import ArchidektAdapter


def read_commanders_from_file(file_path: str) -> List[str]:
    """
    Read commander names from a text file, one per line.
    
    Args:
        file_path: Path to the input file
        
    Returns:
        List of commander names (stripped of whitespace)
    """
    commanders = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                commander = line.strip()
                if commander and not commander.startswith('#'):  # Skip empty lines and comments
                    commanders.append(commander)
        
        print(f"✅ Read {len(commanders)} commanders from {file_path}")
        return commanders
        
    except FileNotFoundError:
        print(f"❌ Error: Input file '{file_path}' not found")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading file '{file_path}': {e}")
        sys.exit(1)


def save_commander_data(commander_data: Dict[str, Any], output_dir: Path, commander_name: str) -> str:
    """
    Save commander data to a JSON file.
    
    Args:
        commander_data: Dictionary containing commander and deck_ids
        output_dir: Directory to save the file
        commander_name: Commander name for filename
        
    Returns:
        Path to the saved file
    """
    # Create safe filename from commander name
    safe_filename = "".join(c for c in commander_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_filename = safe_filename.replace(' ', '_').lower()
    filename = f"{safe_filename}.json"
    
    file_path = output_dir / filename
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(commander_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved data for '{commander_name}' to {file_path}")
        return str(file_path)
        
    except Exception as e:
        print(f"❌ Error saving data for '{commander_name}': {e}")
        return ""


def crawl_commanders(input_file: str, output_dir: str, max_pages: int = 2, politeness_seconds: int = 5):
    """
    Main crawler function.
    
    Args:
        input_file: Path to file containing commander names
        output_dir: Directory to save JSON files
        max_pages: Maximum pages to fetch per commander
        politeness_seconds: Delay between requests
    """
    print("🕷️  Archidekt Commander Crawler")
    print("=" * 50)
    
    # Read commanders from file
    commanders = read_commanders_from_file(input_file)
    
    if not commanders:
        print("❌ No commanders found in input file")
        return
    
    # Create output directory
    output_path = Path(output_dir)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 Output directory: {output_path.absolute()}")
    except Exception as e:
        print(f"❌ Error creating output directory '{output_dir}': {e}")
        return
    
    # Load config and create adapter
    try:
        config = load_config('config/config.yaml')
        adapter = ArchidektAdapter(config)
        print("🔧 Archidekt adapter initialized")
    except Exception as e:
        print(f"❌ Error initializing adapter: {e}")
        return
    
    # Process each commander
    total_commanders = len(commanders)
    successful_saves = 0
    
    print(f"\n🚀 Starting crawl for {total_commanders} commanders...")
    print(f"📊 Max pages per commander: {max_pages}")
    print(f"⏱️  Politeness delay: {politeness_seconds}s")
    print("-" * 50)
    
    for i, commander_name in enumerate(commanders, 1):
        print(f"\n[{i}/{total_commanders}] Processing: {commander_name}")
        
        try:
            # Discover deck IDs for this commander
            deck_ids = adapter.discover_top_viewed_deck_ids_by_commander(
                commander_name=commander_name,
                max_pages=max_pages,
                politeness_seconds=politeness_seconds
            )
            
            # Create data structure
            commander_data = {
                "commander": commander_name,
                "deck_ids": deck_ids,
                "total_decks": len(deck_ids),
                "crawl_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "max_pages_searched": max_pages
            }
            
            # Save to JSON file
            saved_file = save_commander_data(commander_data, output_path, commander_name)
            if saved_file:
                successful_saves += 1
            
            print(f"✅ Found {len(deck_ids)} deck IDs for '{commander_name}'")
            
        except Exception as e:
            print(f"❌ Error processing '{commander_name}': {e}")
            
            # Save error data
            error_data = {
                "commander": commander_name,
                "deck_ids": [],
                "total_decks": 0,
                "crawl_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "max_pages_searched": max_pages,
                "error": str(e)
            }
            save_commander_data(error_data, output_path, commander_name)
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 CRAWL SUMMARY")
    print("=" * 50)
    print(f"Total commanders processed: {total_commanders}")
    print(f"Successful saves: {successful_saves}")
    print(f"Failed saves: {total_commanders - successful_saves}")
    print(f"Output directory: {output_path.absolute()}")
    print("✅ Crawl completed!")


def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Crawl deck data for multiple commanders from Archidekt',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler.py commanders.txt output/
  python crawler.py commanders.txt output/ --max-pages 3 --politeness 10
  python crawler.py commanders.txt output/ --max-pages 1 --politeness 2

Input file format:
  One commander name per line, comments start with #
  
  Ezuri, Claw of Progress
  Hearthhull, the Worldseed
  # This is a comment
  Atraxa, Praetors' Voice
        """
    )
    
    parser.add_argument('input_file', 
                       help='Input file containing commander names (one per line)')
    parser.add_argument('output_dir', 
                       help='Output directory for JSON files')
    parser.add_argument('--max-pages', type=int, default=2,
                       help='Maximum pages to fetch per commander (default: 2)')
    parser.add_argument('--politeness', type=int, default=5,
                       help='Politeness delay in seconds between requests (default: 5)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not os.path.exists(args.input_file):
        print(f"❌ Error: Input file '{args.input_file}' does not exist")
        sys.exit(1)
    
    # Run crawler
    crawl_commanders(
        input_file=args.input_file,
        output_dir=args.output_dir,
        max_pages=args.max_pages,
        politeness_seconds=args.politeness
    )


if __name__ == '__main__':
    main()
