#!/usr/bin/env python3
"""
Deck ID Consolidator

A command line tool to scan crawler output JSON files and consolidate all unique deck IDs
into a single JSON file.
"""

import sys
import os
import argparse
import json
from pathlib import Path
from typing import Set, List, Dict, Any


def scan_json_files(input_dir: str) -> Dict[str, Any]:
    """
    Scan all JSON files in the input directory and extract deck IDs.
    
    Args:
        input_dir: Directory containing JSON files from crawler
        
    Returns:
        Dictionary containing consolidated data
    """
    input_path = Path(input_dir)
    
    if not input_path.exists():
        print(f"❌ Error: Input directory '{input_dir}' does not exist")
        sys.exit(1)
    
    if not input_path.is_dir():
        print(f"❌ Error: '{input_dir}' is not a directory")
        sys.exit(1)
    
    # Find all JSON files
    json_files = list(input_path.glob("*.json"))
    
    if not json_files:
        print(f"❌ No JSON files found in '{input_dir}'")
        sys.exit(1)
    
    print(f"📁 Found {len(json_files)} JSON files in '{input_dir}'")
    
    all_deck_ids: Set[str] = set()
    commander_data: List[Dict[str, Any]] = []
    total_commanders = 0
    successful_reads = 0
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            commander = data.get('commander', 'Unknown')
            deck_ids = data.get('deck_ids', [])
            
            # Add deck IDs to our set (automatically handles uniqueness)
            all_deck_ids.update(deck_ids)
            
            # Store commander data for summary
            commander_data.append({
                'commander': commander,
                'deck_count': len(deck_ids),
                'source_file': json_file.name
            })
            
            total_commanders += 1
            successful_reads += 1
            
            print(f"✅ {commander}: {len(deck_ids)} deck IDs")
            
        except Exception as e:
            print(f"❌ Error reading {json_file.name}: {e}")
    
    # Convert set to sorted list for consistent output
    unique_deck_ids = sorted(list(all_deck_ids), key=int)
    
    # Create consolidated data structure
    consolidated_data = {
        'total_unique_deck_ids': len(unique_deck_ids),
        'total_commanders_processed': total_commanders,
        'successful_file_reads': successful_reads,
        'unique_deck_ids': unique_deck_ids,
        'commander_summary': commander_data,
        'consolidation_timestamp': None  # Will be set when saving
    }
    
    return consolidated_data


def save_consolidated_data(data: Dict[str, Any], output_file: str):
    """
    Save consolidated data to JSON file.
    
    Args:
        data: Consolidated data dictionary
        output_file: Output file path
    """
    from datetime import datetime
    
    # Add timestamp
    data['consolidation_timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Consolidated data saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error saving consolidated data: {e}")
        sys.exit(1)


def print_summary(data: Dict[str, Any]):
    """
    Print a summary of the consolidation results.
    
    Args:
        data: Consolidated data dictionary
    """
    print("\n" + "=" * 60)
    print("📊 CONSOLIDATION SUMMARY")
    print("=" * 60)
    print(f"Total unique deck IDs: {data['total_unique_deck_ids']}")
    print(f"Total commanders processed: {data['total_commanders_processed']}")
    print(f"Successful file reads: {data['successful_file_reads']}")
    print(f"Consolidation timestamp: {data['consolidation_timestamp']}")
    
    print(f"\n📋 Commander Summary:")
    for cmd_data in data['commander_summary']:
        commander = cmd_data['commander']
        deck_count = cmd_data['deck_count']
        source_file = cmd_data['source_file']
        print(f"  • {commander}: {deck_count} deck IDs ({source_file})")
    
    print("\n✅ Consolidation completed!")


def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Consolidate deck IDs from crawler output JSON files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python consolidate_deck_ids.py output/ all_deck_ids.json
  python consolidate_deck_ids.py output/ consolidated.json --summary
  python consolidate_deck_ids.py output/ deck_ids.json --minimal

Output format:
  {
    "total_unique_deck_ids": 1500,
    "total_commanders_processed": 40,
    "unique_deck_ids": ["123", "456", "789", ...],
    "commander_summary": [...],
    "consolidation_timestamp": "2025-09-16 22:00:00"
  }
        """
    )
    
    parser.add_argument('input_dir', 
                       help='Input directory containing JSON files from crawler')
    parser.add_argument('output_file', 
                       help='Output JSON file for consolidated deck IDs')
    parser.add_argument('--summary', action='store_true',
                       help='Show detailed summary after consolidation')
    parser.add_argument('--minimal', action='store_true',
                       help='Create minimal output with only deck IDs array')
    
    args = parser.parse_args()
    
    print("🔍 Deck ID Consolidator")
    print("=" * 50)
    
    # Scan JSON files
    consolidated_data = scan_json_files(args.input_dir)
    
    # Create minimal output if requested
    if args.minimal:
        minimal_data = {
            'unique_deck_ids': consolidated_data['unique_deck_ids'],
            'total_count': consolidated_data['total_unique_deck_ids'],
            'consolidation_timestamp': None
        }
        consolidated_data = minimal_data
    
    # Save consolidated data
    save_consolidated_data(consolidated_data, args.output_file)
    
    # Print summary if requested
    if args.summary or not args.minimal:
        print_summary(consolidated_data)


if __name__ == '__main__':
    main()
