import click
import json
import time
from datetime import datetime
from ..utils.metrics import MetricsCollector, HealthChecker


@click.group()
def monitoring():
    """Monitoring and health check commands."""
    pass


@monitoring.command()
@click.option('--format', default='text', type=click.Choice(['text', 'json']),
              help='Output format')
@click.pass_context
def health(ctx, format):
    """Run system health checks."""
    config = ctx.obj['config']
    db = ctx.obj['db']

    health_checker = HealthChecker(db, config)
    health_checker.setup_default_checks()

    results = health_checker.run_checks()

    if format == 'json':
        click.echo(json.dumps(results, indent=2))
        return

    # Text format
    status_icons = {
        'healthy': '✅',
        'warning': '⚠️',
        'unhealthy': '❌',
        'error': '❌'
    }

    overall_icon = status_icons.get(results['overall_status'], '❓')
    click.echo(f"\n{overall_icon} Overall Status: {results['overall_status'].upper()}")
    click.echo(f"Last Check: {results['timestamp']}")

    click.echo(f"\n=== Health Checks ===")
    for name, check in results['checks'].items():
        icon = status_icons.get(check['status'], '❓')
        click.echo(f"{icon} {name}: {check['status']}")

        if check.get('duration_seconds'):
            click.echo(f"   Duration: {check['duration_seconds']:.3f}s")

        if check.get('warning'):
            click.echo(f"   ⚠️  {check['warning']}")

        if check.get('error'):
            click.echo(f"   ❌ Error: {check['error']}")

        if check.get('details'):
            for key, value in check['details'].items():
                click.echo(f"   {key}: {value}")


@monitoring.command()
@click.option('--format', default='text', type=click.Choice(['text', 'json']),
              help='Output format')
@click.pass_context
def metrics(ctx, format):
    """Show current metrics."""
    # In a real implementation, you'd retrieve metrics from the global collector
    # For now, we'll show some example data structure

    example_metrics = {
        'timestamp': datetime.utcnow().isoformat(),
        'uptime_seconds': 3600,
        'counters': {
            'http_requests_total[source=archidekt,status=success]': 1234,
            'http_requests_total[source=archidekt,status=error]': 5,
            'http_requests_total[source=moxfield,status=success]': 567,
            'decks_ingested_total[source=archidekt]': 1200,
            'cards_normalized_total': 15000,
            'normalization_failures_total': 45
        },
        'gauges': {
            'database_size_bytes': 52428800,
            'active_connections': 1,
            'normalization_rate_percent': 97.5
        },
        'histograms': {
            'http_request_duration_seconds[source=archidekt]': {
                'count': 1239,
                'min': 0.123,
                'max': 4.567,
                'mean': 0.845,
                'p95': 1.234,
                'p99': 2.345
            },
            'deck_processing_duration_seconds': {
                'count': 1200,
                'min': 0.001,
                'max': 0.156,
                'mean': 0.023,
                'p95': 0.067,
                'p99': 0.134
            }
        }
    }

    if format == 'json':
        click.echo(json.dumps(example_metrics, indent=2))
        return

    # Text format
    click.echo(f"\n=== System Metrics ===")
    click.echo(f"Timestamp: {example_metrics['timestamp']}")
    click.echo(f"Uptime: {example_metrics['uptime_seconds']}s")

    click.echo(f"\n--- Counters ---")
    for metric, value in example_metrics['counters'].items():
        click.echo(f"{metric}: {value:,}")

    click.echo(f"\n--- Gauges ---")
    for metric, value in example_metrics['gauges'].items():
        if 'bytes' in metric:
            click.echo(f"{metric}: {value / (1024*1024):.1f} MB")
        elif 'percent' in metric:
            click.echo(f"{metric}: {value:.1f}%")
        else:
            click.echo(f"{metric}: {value}")

    click.echo(f"\n--- Response Times ---")
    for metric, stats in example_metrics['histograms'].items():
        click.echo(f"{metric}:")
        click.echo(f"  Count: {stats['count']:,}")
        click.echo(f"  Mean: {stats['mean']:.3f}s")
        click.echo(f"  P95: {stats['p95']:.3f}s")
        click.echo(f"  P99: {stats['p99']:.3f}s")


@monitoring.command()
@click.option('--interval', default=30, help='Check interval in seconds')
@click.option('--count', default=0, help='Number of checks to run (0 = infinite)')
@click.pass_context
def watch(ctx, interval, count):
    """Continuously monitor system health."""
    config = ctx.obj['config']
    db = ctx.obj['db']

    health_checker = HealthChecker(db, config)
    health_checker.setup_default_checks()

    check_num = 0
    try:
        while count == 0 or check_num < count:
            check_num += 1

            # Clear screen
            click.clear()

            # Show header
            click.echo(f"=== EDH Deck Harvester Monitor (Check #{check_num}) ===")
            click.echo(f"Interval: {interval}s | Press Ctrl+C to stop\n")

            # Run health checks
            results = health_checker.run_checks()

            # Display status
            status_icons = {'healthy': '✅', 'warning': '⚠️', 'unhealthy': '❌'}
            overall_icon = status_icons.get(results['overall_status'], '❓')

            click.echo(f"{overall_icon} Overall: {results['overall_status'].upper()}")
            click.echo(f"Time: {results['timestamp']}")

            # Show individual checks
            for name, check in results['checks'].items():
                icon = status_icons.get(check['status'], '❓')
                click.echo(f"{icon} {name}: {check['status']}")

                if check.get('details'):
                    relevant_details = {
                        k: v for k, v in check['details'].items()
                        if k in ['total_decks', 'decks_last_24h', 'normalization_rate', 'unmapped_cards']
                    }
                    for key, value in relevant_details.items():
                        if 'rate' in key:
                            click.echo(f"   {key}: {value:.1f}%")
                        else:
                            click.echo(f"   {key}: {value:,}")

            # Wait for next check
            if count == 0 or check_num < count:
                time.sleep(interval)

    except KeyboardInterrupt:
        click.echo(f"\n\nMonitoring stopped after {check_num} checks.")


@monitoring.command()
@click.option('--days', default=7, help='Number of days of logs to analyze')
@click.pass_context
def alerts(ctx, days):
    """Check for potential issues that need attention."""
    db = ctx.obj['db']

    alerts = []

    with db.get_connection() as conn:
        # Check for high error rates
        cursor = conn.execute("""
            SELECT source_name, operation,
                   SUM(errors_count) as total_errors,
                   COUNT(*) as total_runs
            FROM ingestion_logs
            WHERE created_at > datetime('now', '-{} days')
            GROUP BY source_name, operation
            HAVING total_errors > 0
        """.replace('{}', str(days)))

        for row in cursor.fetchall():
            error_rate = (row['total_errors'] / row['total_runs']) * 100
            if error_rate > 20:  # More than 20% error rate
                alerts.append({
                    'type': 'high_error_rate',
                    'severity': 'warning' if error_rate < 50 else 'critical',
                    'message': f"{row['source_name']}.{row['operation']} has {error_rate:.1f}% error rate",
                    'details': dict(row)
                })

        # Check for stale data
        cursor = conn.execute("""
            SELECT source_name, MAX(created_at) as last_run
            FROM ingestion_logs
            WHERE operation = 'incremental' OR operation = 'export'
            GROUP BY source_name
        """)

        for row in cursor.fetchall():
            # Parse timestamp and check if older than 2 days
            last_run = datetime.fromisoformat(row['last_run'])
            hours_since = (datetime.utcnow() - last_run).total_seconds() / 3600

            if hours_since > 48:  # More than 2 days
                alerts.append({
                    'type': 'stale_data',
                    'severity': 'warning',
                    'message': f"{row['source_name']} hasn't run successfully in {hours_since:.1f} hours",
                    'details': dict(row)
                })

    # Check normalization rate
    stats = db.get_stats()
    normalization_rate = stats.get('normalization_percentage', 0)

    if normalization_rate < 80:
        alerts.append({
            'type': 'low_normalization',
            'severity': 'warning',
            'message': f"Card normalization rate is {normalization_rate:.1f}% (target: >90%)",
            'details': stats
        })

    # Display alerts
    if not alerts:
        click.echo("✅ No alerts found - system appears healthy!")
        return

    click.echo(f"⚠️  Found {len(alerts)} alerts:")

    for i, alert in enumerate(alerts, 1):
        severity_icon = '🔴' if alert['severity'] == 'critical' else '🟡'
        click.echo(f"\n{i}. {severity_icon} {alert['type'].upper()}")
        click.echo(f"   {alert['message']}")

        if alert.get('details'):
            relevant_keys = ['total_errors', 'total_runs', 'last_run', 'normalization_percentage']
            for key, value in alert['details'].items():
                if key in relevant_keys:
                    click.echo(f"   {key}: {value}")


# Add monitoring commands to the main CLI
def add_monitoring_commands(main_cli):
    """Add monitoring commands to the main CLI group."""
    main_cli.add_command(monitoring)