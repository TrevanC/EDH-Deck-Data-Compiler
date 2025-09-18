import click
import json
import csv
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Any
from ..utils import load_config
from ..db import DatabaseManager
from ..orchestration import JobScheduler

logger = logging.getLogger(__name__)


@click.group()
@click.option('--config', default='config/config.yaml', help='Configuration file path')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.pass_context
def cli(ctx, config, verbose):
    """EDH Deck Data Harvester CLI"""
    # Setup logging
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load config and initialize database
    try:
        ctx.ensure_object(dict)
        ctx.obj['config'] = load_config(config)
        ctx.obj['db'] = DatabaseManager(
            ctx.obj['config']['storage']['path'],
            ctx.obj['config']['storage']['wal_mode']
        )
    except Exception as e:
        click.echo(f"Error initializing: {e}", err=True)
        ctx.exit(1)


@cli.command()
@click.pass_context
def stats(ctx):
    """Show database statistics."""
    db = ctx.obj['db']
    stats_data = db.get_stats()

    click.echo("\n=== EDH Deck Data Statistics ===")
    click.echo(f"Total decks: {stats_data['total_decks']:,}")
    click.echo(f"Total cards: {stats_data['total_cards']:,}")
    click.echo(f"Normalized cards: {stats_data['normalized_cards']:,}")
    click.echo(f"Normalization rate: {stats_data['normalization_percentage']:.1f}%")
    click.echo(f"Unmapped card names: {stats_data['unmapped_unique_names']:,}")


@cli.command()
@click.option('--format', default='Commander', help='Deck format to query')
@click.option('--limit', default=10, help='Number of decks to show')
@click.option('--commander', help='Filter by commander name')
@click.option('--author', help='Filter by deck author')
@click.pass_context
def list_decks(ctx, format, limit, commander, author):
    """List decks with optional filters."""
    db = ctx.obj['db']

    with db.get_connection() as conn:
        query = """
            SELECT d.id, d.title, d.author, d.url, d.source_id,
                   s.name as source_name, d.created_at
            FROM decks d
            JOIN sources s ON d.source_id = s.id
            WHERE d.format = ?
        """
        params = [format]

        if commander:
            query += """
                AND d.id IN (
                    SELECT DISTINCT deck_id
                    FROM deck_commanders
                    WHERE name LIKE ?
                )
            """
            params.append(f'%{commander}%')

        if author:
            query += " AND d.author LIKE ?"
            params.append(f'%{author}%')

        query += " ORDER BY d.created_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        decks = cursor.fetchall()

    if not decks:
        click.echo("No decks found matching criteria.")
        return

    click.echo(f"\n=== {len(decks)} Decks ===")
    for deck in decks:
        click.echo(f"\n{deck['title']} by {deck['author']}")
        click.echo(f"  Source: {deck['source_name']} | Created: {deck['created_at']}")
        click.echo(f"  URL: {deck['url']}")


@cli.command()
@click.argument('deck_id', type=int)
@click.option('--format', default='text', type=click.Choice(['text', 'json']),
              help='Output format')
@click.pass_context
def show_deck(ctx, deck_id, format):
    """Show detailed information for a specific deck."""
    db = ctx.obj['db']

    with db.get_connection() as conn:
        # Get deck info
        cursor = conn.execute("""
            SELECT d.*, s.name as source_name
            FROM decks d
            JOIN sources s ON d.source_id = s.id
            WHERE d.id = ?
        """, (deck_id,))
        deck = cursor.fetchone()

        if not deck:
            click.echo(f"Deck {deck_id} not found.")
            return

        # Get deck cards
        cursor = conn.execute("""
            SELECT name, qty, oracle_id, zone
            FROM deck_cards
            WHERE deck_id = ?
            ORDER BY zone, name
        """, (deck_id,))
        cards = cursor.fetchall()

        # Get commanders
        cursor = conn.execute("""
            SELECT name, oracle_id
            FROM deck_commanders
            WHERE deck_id = ?
        """, (deck_id,))
        commanders = cursor.fetchall()

    if format == 'json':
        deck_data = {
            'deck_info': dict(deck),
            'commanders': [dict(cmd) for cmd in commanders],
            'cards': [dict(card) for card in cards]
        }
        click.echo(json.dumps(deck_data, indent=2, default=str))
    else:
        click.echo(f"\n=== {deck['title']} ===")
        click.echo(f"Author: {deck['author']}")
        click.echo(f"Source: {deck['source_name']}")
        click.echo(f"Format: {deck['format']}")
        click.echo(f"URL: {deck['url']}")
        click.echo(f"Created: {deck['created_at']}")

        if commanders:
            click.echo(f"\nCommanders ({len(commanders)}):")
            for cmd in commanders:
                click.echo(f"  - {cmd['name']}")

        main_cards = [c for c in cards if c['zone'] == 'main']
        if main_cards:
            click.echo(f"\nMainboard ({len(main_cards)} cards):")
            for card in main_cards:
                click.echo(f"  {card['qty']}x {card['name']}")


@cli.command()
@click.option('--limit', default=20, help='Number of top cards to show')
@click.option('--format', default='Commander', help='Deck format')
@click.pass_context
def top_cards(ctx, limit, format):
    """Show most popular cards."""
    db = ctx.obj['db']

    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT dc.name, COUNT(*) as deck_count, SUM(dc.qty) as total_copies
            FROM deck_cards dc
            JOIN decks d ON dc.deck_id = d.id
            WHERE d.format = ? AND dc.zone = 'main'
            GROUP BY dc.name
            ORDER BY deck_count DESC, total_copies DESC
            LIMIT ?
        """, (format, limit))
        cards = cursor.fetchall()

    if not cards:
        click.echo(f"No cards found for format {format}.")
        return

    click.echo(f"\n=== Top {len(cards)} Cards in {format} ===")
    for i, card in enumerate(cards, 1):
        click.echo(
            f"{i:2d}. {card['name']} - "
            f"{card['deck_count']} decks ({card['total_copies']} copies)"
        )


@cli.command()
@click.option('--output', '-o', help='Output file path')
@click.option('--format', default='csv', type=click.Choice(['csv', 'json', 'parquet']),
              help='Export format')
@click.option('--deck-format', default='Commander', help='Deck format to export')
@click.pass_context
def export(ctx, output, format, deck_format):
    """Export deck data."""
    db = ctx.obj['db']

    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT d.id, d.title, d.author, d.url, s.name as source,
                   d.created_at, d.updated_at
            FROM decks d
            JOIN sources s ON d.source_id = s.id
            WHERE d.format = ?
            ORDER BY d.created_at DESC
        """, (deck_format,))
        decks = [dict(row) for row in cursor.fetchall()]

    if not decks:
        click.echo(f"No decks found for format {deck_format}.")
        return

    # Generate filename if not provided
    if not output:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output = f'edh_decks_{timestamp}.{format}'

    if format == 'csv':
        with open(output, 'w', newline='') as f:
            if decks:
                writer = csv.DictWriter(f, fieldnames=decks[0].keys())
                writer.writeheader()
                writer.writerows(decks)

    elif format == 'json':
        with open(output, 'w') as f:
            json.dump(decks, f, indent=2, default=str)

    elif format == 'parquet':
        df = pd.DataFrame(decks)
        df.to_parquet(output, index=False)

    click.echo(f"Exported {len(decks)} decks to {output}")


@cli.command()
@click.argument('job_name', type=click.Choice([
    'archidekt_incremental', 'moxfield_discovery', 'moxfield_export', 'normalization'
]))
@click.pass_context
def run_job(ctx, job_name):
    """Run a specific ingestion job manually."""
    config = ctx.obj['config']
    db = ctx.obj['db']

    scheduler = JobScheduler(config, db)

    try:
        click.echo(f"Running job: {job_name}")
        result = scheduler.run_once(job_name)

        if result['status'] == 'success':
            click.echo(f"✅ Job completed successfully!")
            if 'decks_processed' in result:
                click.echo(f"   Decks processed: {result['decks_processed']}")
            if 'cards_processed' in result:
                click.echo(f"   Cards processed: {result['cards_processed']}")
            if 'duration_seconds' in result:
                click.echo(f"   Duration: {result['duration_seconds']:.1f}s")
        else:
            click.echo(f"❌ Job failed: {result.get('message', 'Unknown error')}")

    except Exception as e:
        click.echo(f"❌ Job crashed: {e}", err=True)
    finally:
        scheduler.stop()


@cli.command()
@click.pass_context
def scheduler(ctx):
    """Start the job scheduler daemon."""
    config = ctx.obj['config']
    db = ctx.obj['db']

    scheduler = JobScheduler(config, db)

    click.echo("Starting EDH Deck Data Harvester scheduler...")
    click.echo("Press Ctrl+C to stop")

    try:
        scheduler.run_forever()
    except KeyboardInterrupt:
        click.echo("\nScheduler stopped by user.")
    finally:
        scheduler.stop()


@cli.command()
@click.option('--limit', default=10, help='Number of recent jobs to show')
@click.pass_context
def job_history(ctx, limit):
    """Show recent job execution history."""
    config = ctx.obj['config']
    db = ctx.obj['db']

    scheduler = JobScheduler(config, db)
    history = scheduler.get_job_history(limit)

    if not history:
        click.echo("No job history found.")
        return

    click.echo(f"\n=== Recent Job History ({len(history)} entries) ===")
    for job in history:
        status_icon = "✅" if job['status'] == 'success' else "❌"
        click.echo(
            f"{status_icon} {job['created_at']} | "
            f"{job['source_name']}.{job['operation']} | "
            f"decks: {job['decks_processed']} | "
            f"cards: {job['cards_processed']} | "
            f"{job['duration_seconds']:.1f}s"
        )

        if job['errors_count'] > 0:
            click.echo(f"    ⚠️  {job['errors_count']} errors")

        if job['message']:
            click.echo(f"    💬 {job['message']}")


# Add monitoring commands
from .monitoring import add_monitoring_commands
add_monitoring_commands(cli)


if __name__ == '__main__':
    cli()