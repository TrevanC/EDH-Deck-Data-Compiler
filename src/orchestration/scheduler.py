import logging
import schedule
import time
from datetime import datetime
from typing import Dict, Any, List
from ..db import DatabaseManager
from .ingestion_job import IngestionJob

logger = logging.getLogger(__name__)


class JobScheduler:
    """Handles scheduled execution of ingestion jobs."""

    def __init__(self, config: Dict, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.job = IngestionJob(config, db_manager)
        self.running = False

        # Setup scheduled jobs
        self._setup_schedules()

    def _setup_schedules(self):
        """Setup scheduled jobs based on configuration."""
        schedule_config = self.config.get('scheduling', {})

        # Archidekt incremental
        archidekt_time = schedule_config.get('archidekt_incremental', '00:00')
        schedule.every().day.at(archidekt_time).do(
            self._run_with_logging,
            'archidekt_incremental',
            self.job.run_archidekt_incremental
        )

        # Moxfield discovery
        moxfield_discovery_time = schedule_config.get('moxfield_discovery', '02:00')
        schedule.every().day.at(moxfield_discovery_time).do(
            self._run_with_logging,
            'moxfield_discovery',
            self.job.run_moxfield_discovery
        )

        # Moxfield export
        moxfield_export_time = schedule_config.get('moxfield_export', '03:00')
        schedule.every().day.at(moxfield_export_time).do(
            self._run_with_logging,
            'moxfield_export',
            lambda: self.job.run_moxfield_export(max_decks=100)
        )

        # Scryfall refresh + normalization
        scryfall_time = schedule_config.get('scryfall_refresh', '04:00')
        schedule.every().day.at(scryfall_time).do(
            self._run_with_logging,
            'normalization',
            self.job.run_normalization
        )

        logger.info("Scheduled jobs configured:")
        logger.info(f"  - Archidekt incremental: {archidekt_time} UTC")
        logger.info(f"  - Moxfield discovery: {moxfield_discovery_time} UTC")
        logger.info(f"  - Moxfield export: {moxfield_export_time} UTC")
        logger.info(f"  - Normalization: {scryfall_time} UTC")

    def _run_with_logging(self, job_name: str, job_func):
        """Run a job with proper logging."""
        logger.info(f"Starting scheduled job: {job_name}")
        start_time = datetime.utcnow()

        try:
            result = job_func()
            duration = (datetime.utcnow() - start_time).total_seconds()

            logger.info(
                f"Job {job_name} completed: {result.get('status', 'unknown')} "
                f"in {duration:.1f}s"
            )

            if result.get('status') == 'error':
                logger.error(f"Job {job_name} failed: {result.get('message', 'Unknown error')}")

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Job {job_name} crashed after {duration:.1f}s: {e}")

    def run_forever(self):
        """Run the scheduler indefinitely."""
        self.running = True
        logger.info("Job scheduler started")

        try:
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # Check every minute

        except KeyboardInterrupt:
            logger.info("Scheduler interrupted by user")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        finally:
            self.stop()

    def run_once(self, job_name: str) -> Dict[str, Any]:
        """Run a specific job once (for manual execution)."""
        logger.info(f"Running job manually: {job_name}")

        job_methods = {
            'archidekt_incremental': self.job.run_archidekt_incremental,
            'moxfield_discovery': self.job.run_moxfield_discovery,
            'moxfield_export': lambda: self.job.run_moxfield_export(max_decks=50),
            'normalization': self.job.run_normalization
        }

        if job_name not in job_methods:
            return {
                'status': 'error',
                'message': f'Unknown job: {job_name}. Available: {list(job_methods.keys())}'
            }

        try:
            return job_methods[job_name]()
        except Exception as e:
            logger.error(f"Manual job {job_name} failed: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }

    def stop(self):
        """Stop the scheduler."""
        self.running = False
        logger.info("Stopping scheduler")

        # Cleanup resources
        try:
            self.job.cleanup()
        except Exception as e:
            logger.warning(f"Failed to cleanup job resources: {e}")

        logger.info("Scheduler stopped")

    def get_next_runs(self) -> Dict[str, str]:
        """Get the next run times for all scheduled jobs."""
        next_runs = {}

        for job in schedule.jobs:
            job_name = getattr(job.job_func, '__name__', 'unknown')
            if hasattr(job, 'next_run'):
                next_runs[job_name] = job.next_run.strftime('%Y-%m-%d %H:%M:%S UTC')

        return next_runs

    def get_job_history(self, limit: int = 20) -> List[Dict]:
        """Get recent job execution history."""
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT source_name, operation, status, decks_processed,
                       cards_processed, errors_count, duration_seconds,
                       message, created_at
                FROM ingestion_logs
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))

            return [dict(row) for row in cursor.fetchall()]