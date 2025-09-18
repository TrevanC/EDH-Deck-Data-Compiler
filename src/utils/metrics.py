import time
import logging
from typing import Dict, Any, Optional
from collections import defaultdict, Counter
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Simple metrics collector for monitoring harvester performance."""

    def __init__(self):
        self.counters = defaultdict(int)
        self.timers = {}
        self.gauges = {}
        self.histograms = defaultdict(list)
        self.start_time = datetime.utcnow()

    def increment(self, metric_name: str, value: int = 1, tags: Dict[str, str] = None):
        """Increment a counter metric."""
        key = self._build_key(metric_name, tags)
        self.counters[key] += value

    def gauge(self, metric_name: str, value: float, tags: Dict[str, str] = None):
        """Set a gauge metric."""
        key = self._build_key(metric_name, tags)
        self.gauges[key] = {
            'value': value,
            'timestamp': datetime.utcnow()
        }

    def histogram(self, metric_name: str, value: float, tags: Dict[str, str] = None):
        """Add a value to a histogram metric."""
        key = self._build_key(metric_name, tags)
        self.histograms[key].append({
            'value': value,
            'timestamp': datetime.utcnow()
        })

    def timer(self, metric_name: str, tags: Dict[str, str] = None):
        """Create a timer context manager."""
        return TimerContext(self, metric_name, tags)

    def _build_key(self, metric_name: str, tags: Dict[str, str] = None) -> str:
        """Build a metric key with optional tags."""
        if not tags:
            return metric_name

        tag_str = ','.join(f'{k}={v}' for k, v in sorted(tags.items()))
        return f'{metric_name}[{tag_str}]'

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics."""
        now = datetime.utcnow()
        uptime = (now - self.start_time).total_seconds()

        summary = {
            'uptime_seconds': uptime,
            'timestamp': now.isoformat(),
            'counters': dict(self.counters),
            'gauges': {k: v['value'] for k, v in self.gauges.items()},
            'histograms': {}
        }

        # Summarize histograms
        for metric, values in self.histograms.items():
            if values:
                vals = [v['value'] for v in values]
                summary['histograms'][metric] = {
                    'count': len(vals),
                    'min': min(vals),
                    'max': max(vals),
                    'mean': sum(vals) / len(vals),
                    'p95': self._percentile(vals, 0.95),
                    'p99': self._percentile(vals, 0.99)
                }

        return summary

    def _percentile(self, values: list, p: float) -> float:
        """Calculate percentile of a list of values."""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        index = int(len(sorted_values) * p)
        return sorted_values[min(index, len(sorted_values) - 1)]

    def reset(self):
        """Reset all metrics."""
        self.counters.clear()
        self.gauges.clear()
        self.histograms.clear()
        self.start_time = datetime.utcnow()


class TimerContext:
    """Context manager for timing operations."""

    def __init__(self, metrics: MetricsCollector, metric_name: str, tags: Dict[str, str] = None):
        self.metrics = metrics
        self.metric_name = metric_name
        self.tags = tags
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            self.metrics.histogram(
                f'{self.metric_name}.duration_seconds',
                duration,
                self.tags
            )

            # Also track success/failure
            status = 'error' if exc_type else 'success'
            tags = dict(self.tags) if self.tags else {}
            tags['status'] = status

            self.metrics.increment(
                f'{self.metric_name}.total',
                tags=tags
            )


class HealthChecker:
    """Health check system for monitoring system status."""

    def __init__(self, db_manager, config: Dict):
        self.db = db_manager
        self.config = config
        self.checks = {}
        self.last_check = None

    def register_check(self, name: str, check_func, warning_threshold: float = 5.0):
        """Register a health check function."""
        self.checks[name] = {
            'func': check_func,
            'warning_threshold': warning_threshold
        }

    def run_checks(self) -> Dict[str, Any]:
        """Run all registered health checks."""
        results = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_status': 'healthy',
            'checks': {}
        }

        for name, check_config in self.checks.items():
            try:
                start_time = time.time()
                result = check_config['func']()
                duration = time.time() - start_time

                check_result = {
                    'status': 'healthy',
                    'duration_seconds': duration,
                    'details': result
                }

                # Check if duration exceeds warning threshold
                if duration > check_config['warning_threshold']:
                    check_result['status'] = 'warning'
                    check_result['warning'] = f'Check took {duration:.2f}s (threshold: {check_config["warning_threshold"]}s)'

                results['checks'][name] = check_result

            except Exception as e:
                logger.error(f"Health check {name} failed: {e}")
                results['checks'][name] = {
                    'status': 'error',
                    'error': str(e)
                }
                results['overall_status'] = 'unhealthy'

        # Update overall status based on individual checks
        if any(check['status'] == 'error' for check in results['checks'].values()):
            results['overall_status'] = 'unhealthy'
        elif any(check['status'] == 'warning' for check in results['checks'].values()):
            results['overall_status'] = 'warning'

        self.last_check = results
        return results

    def database_check(self) -> Dict[str, Any]:
        """Check database connectivity and basic stats."""
        with self.db.get_connection() as conn:
            # Test basic query
            cursor = conn.execute("SELECT COUNT(*) as count FROM decks")
            deck_count = cursor.fetchone()['count']

            # Check recent activity
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM decks
                WHERE created_at > datetime('now', '-24 hours')
            """)
            recent_decks = cursor.fetchone()['count']

            return {
                'total_decks': deck_count,
                'decks_last_24h': recent_decks,
                'database_path': self.db.db_path
            }

    def normalization_check(self) -> Dict[str, Any]:
        """Check card normalization health."""
        stats = self.db.get_stats()

        normalization_rate = stats.get('normalization_percentage', 0)
        unmapped_count = stats.get('unmapped_unique_names', 0)

        return {
            'normalization_rate': normalization_rate,
            'unmapped_cards': unmapped_count,
            'healthy': normalization_rate > 85.0 and unmapped_count < 1000
        }

    def setup_default_checks(self):
        """Setup default health checks."""
        self.register_check('database', self.database_check, 2.0)
        self.register_check('normalization', self.normalization_check, 3.0)


# Global metrics instance
metrics = MetricsCollector()