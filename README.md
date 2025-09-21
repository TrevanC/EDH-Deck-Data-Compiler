# EDH Deck Data Harvester

A respectful, rate-limited system for collecting public Commander/EDH decklists from community sites, normalizing card data, and making it queryable for research and recommendations.

## Features

- **Polite Data Collection**: Rate-limited ingestion from Archidekt and Moxfield with proper backoff
- **Card Normalization**: Uses Scryfall Oracle data to normalize card names to stable IDs
- **Incremental Updates**: Supports scheduled daily/weekly refreshes with job orchestration
- **Multiple Export Formats**: CSV, JSON, and Parquet exports
- **Rich CLI Interface**: Comprehensive command-line interface for all operations
- **Standalone Discovery Tools**: Commander-based deck ID discovery and bulk download scripts
- **Health Monitoring**: Built-in metrics collection, health checks, and alerting system
- **Job Orchestration**: Automated scheduling with manual override capabilities
- **Performance Tracking**: Detailed metrics for requests, processing times, and error rates
- **Cloudflare Handling**: Selenium fallback for Moxfield when needed
- **Continuous Monitoring**: Real-time system health monitoring with configurable intervals

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

### 4. Standalone Discovery Tools

For bulk deck discovery and download, use the standalone scripts:

```bash
# Discover deck IDs for commanders
python crawler.py commanders.txt output/

# Consolidate and download deck contents
python consolidate_deck_ids.py output/ consolidated_deck_ids.json
python fetch_deck_lists.py consolidated_deck_ids.json deck_lists/
```

## CLI Commands

The system provides a comprehensive command-line interface for all operations:

### Data Management

```bash
# Database statistics
python main.py stats

# List decks with filters
python main.py list-decks --limit 20 --commander "Atraxa" --author "username"

# Show detailed deck information
python main.py show-deck 12345 --format json

# Show most popular cards
python main.py top-cards --limit 50 --format Commander

# Export data in multiple formats
python main.py export --format csv --output edh_decks.csv
python main.py export --format json --output edh_decks.json
python main.py export --format parquet --output edh_decks.parquet
```

### Job Management

```bash
# Run specific ingestion jobs manually
python main.py run-job archidekt_incremental
python main.py run-job moxfield_discovery
python main.py run-job moxfield_export
python main.py run-job normalization

# Start the scheduler daemon
python main.py scheduler

# View job execution history
python main.py job-history --limit 20
```

### Monitoring & Health Checks

```bash
# Run system health checks
python main.py monitoring health --format text
python main.py monitoring health --format json

# Show current system metrics
python main.py monitoring metrics --format text
python main.py monitoring metrics --format json

# Continuous monitoring (watch mode)
python main.py monitoring watch --interval 30 --count 10

# Check for alerts and issues
python main.py monitoring alerts --days 7
```

### Deck Discovery & Download

The system includes standalone scripts for discovering and downloading deck data from Archidekt:

#### Commander Deck ID Discovery

```bash
# Discover deck IDs for multiple commanders
python crawler.py commanders.txt output/

# With custom settings
python crawler.py commanders.txt output/ --max-pages 3 --politeness 10
```

**Input file format** (`commanders.txt`):
```
Ezuri, Claw of Progress
Hearthhull, the Worldseed
# This is a comment
Atraxa, Praetors' Voice
```

**Output:** Creates individual JSON files for each commander containing discovered deck IDs.

#### Deck ID Consolidation

```bash
# Consolidate deck IDs from multiple commander files
python consolidate_deck_ids.py output/ consolidated_deck_ids.json

# With detailed summary
python consolidate_deck_ids.py output/ consolidated.json --summary

# Minimal output (deck IDs only)
python consolidate_deck_ids.py output/ deck_ids.json --minimal
```

#### Deck Content Download

```bash
# Download full deck contents from consolidated deck IDs
python fetch_deck_lists.py consolidated_deck_ids.json deck_lists/

# With custom settings
python fetch_deck_lists.py consolidated_deck_ids.json deck_lists/ --politeness 3 --max-decks 100

# Resume from specific index
python fetch_deck_lists.py consolidated_deck_ids.json deck_lists/ --start-from 50 --max-decks 50
```

#### Complete Workflow Example

```bash
# 1. Create commander list
echo "Atraxa, Praetors' Voice" > commanders.txt
echo "Ezuri, Claw of Progress" >> commanders.txt

# 2. Discover deck IDs
python crawler.py commanders.txt output/

# 3. Consolidate deck IDs
python consolidate_deck_ids.py output/ consolidated_deck_ids.json --summary

# 4. Download deck contents
python fetch_deck_lists.py consolidated_deck_ids.json deck_lists/ --politeness 2
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

## Scheduled Jobs & Orchestration

The system includes a sophisticated job scheduler that runs ingestion and maintenance tasks automatically.

### Default Schedule

The system runs these jobs automatically:

- **00:00 UTC**: Archidekt incremental ingestion
- **02:00 UTC**: Moxfield deck discovery  
- **03:00 UTC**: Moxfield deck export
- **04:00 UTC**: Scryfall refresh + normalization

Configure schedules in `config/config.yaml` under `scheduling`.

### Job Types

**Archidekt Incremental**
- Fetches recent Commander decks from Archidekt API
- Processes up to 10 pages per run (configurable)
- Handles rate limiting and error recovery

**Moxfield Discovery**
- Discovers new deck IDs using popular commander searches
- Uses configured commander list for targeted discovery
- Stores discovered IDs for export processing

**Moxfield Export**
- Exports deck data for discovered IDs
- Handles Cloudflare protection with Selenium fallback
- Processes up to 100 decks per run (configurable)

**Normalization**
- Refreshes Scryfall Oracle data weekly
- Normalizes unmapped card names to oracle_id
- Processes up to 5000 cards per run

### Manual Job Execution

```bash
# Run any job manually for testing or immediate processing
python main.py run-job archidekt_incremental
python main.py run-job moxfield_discovery
python main.py run-job moxfield_export
python main.py run-job normalization

# Start the scheduler daemon for continuous operation
python main.py scheduler
```

### Job Monitoring

```bash
# View recent job execution history
python main.py job-history --limit 20

# Monitor job health and performance
python main.py monitoring alerts --days 7
```

## Monitoring & Health System

The system includes comprehensive monitoring capabilities to ensure reliable operation and early issue detection.

### Health Checks

The health check system monitors key system components:

```bash
# Run comprehensive health checks
python main.py monitoring health --format text
python main.py monitoring health --format json

# Continuous monitoring with custom intervals
python main.py monitoring watch --interval 30 --count 10

# Check for system alerts and issues
python main.py monitoring alerts --days 7
```

**Health Check Components:**
- **Database Connectivity**: Verifies database access and basic queries
- **Normalization Health**: Checks card normalization rates and unmapped cards
- **Recent Activity**: Monitors deck ingestion in the last 24 hours
- **Performance Metrics**: Tracks response times and system performance

### Metrics Collection

The system collects detailed metrics for monitoring and analysis:

```bash
# View current system metrics
python main.py monitoring metrics --format text
python main.py monitoring metrics --format json
```

**Metrics Categories:**
- **Counters**: HTTP requests, decks ingested, cards normalized, failures
- **Gauges**: Database size, active connections, normalization rates
- **Histograms**: Response times, processing durations with percentiles (P95, P99)

### Job History & Monitoring

```bash
# View recent job execution history
python main.py job-history --limit 20

# Monitor job performance and error rates
python main.py monitoring alerts --days 7
```

**Monitoring Features:**
- **Job Status Tracking**: Success/failure rates for all ingestion jobs
- **Error Rate Monitoring**: Automatic alerts for high error rates (>20%)
- **Stale Data Detection**: Alerts when sources haven't updated in >48 hours
- **Performance Tracking**: Duration and throughput metrics for all operations

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

### Diagnostic Commands

The system provides comprehensive diagnostic tools:

```bash
# Run full system health check
python main.py monitoring health

# Check for alerts and issues
python main.py monitoring alerts --days 7

# View recent job failures
python main.py job-history --limit 20

# Monitor system metrics
python main.py monitoring metrics

# Continuous monitoring for debugging
python main.py monitoring watch --interval 10 --count 5
```

### Common Issues

1. **Selenium Errors**: Make sure Chrome/Chromium is installed
   ```bash
   # Check if Selenium is working
   python main.py run-job moxfield_export
   ```

2. **Rate Limiting**: Reduce `rate_limit` values in config
   ```bash
   # Monitor request rates
   python main.py monitoring metrics
   ```

3. **Cloudflare Issues**: Enable Selenium fallback for Moxfield
   ```bash
   # Check Moxfield job status
   python main.py job-history --limit 5
   ```

4. **Database Locks**: Ensure WAL mode is enabled
   ```bash
   # Check database health
   python main.py monitoring health
   ```

5. **Normalization Failures**: Check Scryfall bulk data download
   ```bash
   # Check normalization status
   python main.py monitoring health
   python main.py stats
   ```

6. **High Error Rates**: Monitor job performance
   ```bash
   # Check for alerts
   python main.py monitoring alerts --days 3
   ```

### Log Locations

- **Application logs**: `logs/harvester.log`
- **Job history**: Database `ingestion_logs` table
- **Health checks**: `python main.py monitoring health`
- **Metrics**: `python main.py monitoring metrics`
- **Alerts**: `python main.py monitoring alerts`

### Performance Issues

```bash
# Check system performance metrics
python main.py monitoring metrics --format json

# Monitor job execution times
python main.py job-history --limit 10

# Watch real-time performance
python main.py monitoring watch --interval 30
```

## License

This project is designed for educational and research purposes. Please respect the terms of service of data sources and consider the impact on their infrastructure.

## Contributing

1. Follow the existing code patterns and documentation style
2. Add tests for new features
3. Update this README for significant changes
4. Ensure rate limits remain conservative

## Contact

For questions about this harvester system, please open an issue in the repository.