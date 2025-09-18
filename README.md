# EDH Deck Data Harvester

A respectful, rate-limited system for collecting public Commander/EDH decklists from community sites, normalizing card data, and making it queryable for research and recommendations.

## Features

- **Polite Data Collection**: Rate-limited ingestion from Archidekt and Moxfield with proper backoff
- **Card Normalization**: Uses Scryfall Oracle data to normalize card names to stable IDs
- **Incremental Updates**: Supports scheduled daily/weekly refreshes
- **Multiple Export Formats**: CSV, JSON, and Parquet exports
- **CLI Interface**: Rich command-line interface for queries and management
- **Health Monitoring**: Built-in metrics and health checks
- **Cloudflare Handling**: Selenium fallback for Moxfield when needed

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd EDHDeckData

# Install dependencies
pip install -r requirements.txt

# Install Chrome/Chromium for Selenium (if using Moxfield)
# On Ubuntu: sudo apt install chromium-browser
# On macOS: brew install chromium
```

### 2. Configuration

The system uses `config/config.yaml` for configuration. Key settings:

- **Rate Limits**: Adjust `sources.*.rate_limit` (requests per second)
- **Page Limits**: Set `sources.*.max_pages` to control bulk ingestion size
- **Schedules**: Configure when jobs run in `scheduling` section
- **Storage**: Database path and settings in `storage`

### 3. Basic Usage

```bash
# Show help
python main.py --help

# Show database statistics
python main.py stats

# Run a manual ingestion job
python main.py run-job archidekt_incremental

# List recent decks
python main.py list-decks --limit 20

# Show popular cards
python main.py top-cards --limit 50

# Export data
python main.py export --format csv --output edh_decks.csv

# Start the scheduler daemon
python main.py scheduler
```

## Architecture

```
[Archidekt] ┐                  ┌─> [Decks]
[Moxfield]  ├─> [Adapters] ────┼─> [DeckCards]
            │                  └─> [Sources]
            └─> [Queue] ─────────> [Logs/Metrics]
                         └─> [Normalization (Scryfall)] ──> [oracle_id on DeckCards]
```

### Components

- **Adapters**: Source-specific data ingestion (Archidekt, Moxfield)
- **Normalization**: Card name → Scryfall oracle_id mapping
- **Database**: SQLite storage with proper indexing
- **Orchestration**: Scheduled jobs with retry/backoff
- **CLI**: User interface for queries and management
- **Monitoring**: Health checks and metrics collection

## Data Model

### Core Tables

- **sources**: Data source registry (Archidekt, Moxfield)
- **decks**: Deck metadata (title, author, URL, format)
- **deck_cards**: Individual cards in decks with quantities
- **deck_commanders**: Explicit commander tracking
- **unmapped_cards**: Cards that couldn't be normalized
- **ingestion_logs**: Operation history and metrics

### Card Normalization

All cards are normalized using Scryfall's Oracle bulk data:
- Maps card names to stable `oracle_id` values
- Handles DFC, split cards, and alternative names
- Logs unmapped cards for review
- Refreshes weekly with latest Scryfall data

## Scheduled Jobs

The system runs these jobs automatically:

- **00:00 UTC**: Archidekt incremental ingestion
- **02:00 UTC**: Moxfield deck discovery
- **03:00 UTC**: Moxfield deck export
- **04:00 UTC**: Scryfall refresh + normalization

Configure schedules in `config/config.yaml` under `scheduling`.

## Monitoring

### Health Checks

```bash
# Run health checks
python main.py monitoring health

# Show current metrics
python main.py monitoring metrics

# Watch system status
python main.py monitoring watch --interval 30

# Check for alerts
python main.py monitoring alerts --days 7
```

### Job History

```bash
# Show recent job runs
python main.py job-history --limit 20
```

## Politeness & Compliance

This system is designed to be respectful:

- **Rate Limiting**: Conservative request rates (0.5-1.5 req/sec)
- **Public Data Only**: No authentication or private deck access
- **Backoff**: Exponential backoff on errors and 429 responses
- **Identification**: Proper User-Agent with contact information
- **Caching**: Avoids duplicate requests when possible

## Scaling

### Phase 1: SQLite (Current)
- Single-host deployment with cron scheduling
- SQLite WAL mode for concurrent access
- Suitable for ~100K-1M decks

### Phase 2: PostgreSQL
- Migrate to PostgreSQL for better concurrency
- Partition large tables by deck ID ranges
- Add materialized views for common queries

### Phase 3: Distributed
- Multiple harvester instances with job coordination
- Message queues for work distribution
- Separate read replicas for query workloads

## Export Formats

The system supports multiple export formats:

```bash
# CSV export (default)
python main.py export --format csv

# JSON export
python main.py export --format json

# Parquet export (for analytics)
python main.py export --format parquet
```

## Development

### Project Structure

```
src/
├── adapters/          # Source-specific ingestion
├── cli/               # Command-line interface
├── db/                # Database schema and access
├── normalization/     # Card name normalization
├── orchestration/     # Job scheduling
└── utils/             # Configuration and utilities

config/                # Configuration files
data/                  # Database and cache storage
logs/                  # Application logs
tests/                 # Test files
```

### Adding New Sources

1. Create a new adapter in `src/adapters/`
2. Extend `BaseAdapter` with source-specific methods
3. Add source configuration to `config/config.yaml`
4. Update the `IngestionJob` to include the new source

### Testing

```bash
# Run tests (when implemented)
python -m pytest tests/

# Test individual components
python main.py run-job archidekt_incremental --limit 1
```

## Troubleshooting

### Common Issues

1. **Selenium Errors**: Make sure Chrome/Chromium is installed
2. **Rate Limiting**: Reduce `rate_limit` values in config
3. **Cloudflare Issues**: Enable Selenium fallback for Moxfield
4. **Database Locks**: Ensure WAL mode is enabled
5. **Normalization Failures**: Check Scryfall bulk data download

### Log Locations

- Application logs: `logs/harvester.log`
- Job history: Database `ingestion_logs` table
- Health checks: `python main.py monitoring health`

## License

This project is designed for educational and research purposes. Please respect the terms of service of data sources and consider the impact on their infrastructure.

## Contributing

1. Follow the existing code patterns and documentation style
2. Add tests for new features
3. Update this README for significant changes
4. Ensure rate limits remain conservative

## Contact

For questions about this harvester system, please open an issue in the repository.