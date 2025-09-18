import logging
import logging.handlers
import os
from typing import Dict


def setup_logging(config: Dict) -> None:
    """Setup structured logging configuration."""
    log_config = config.get('logging', {})

    # Create logs directory
    log_file = log_config.get('file', './logs/harvester.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Configure root logger
    level = getattr(logging, log_config.get('level', 'INFO').upper())

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=log_config.get('max_size_mb', 100) * 1024 * 1024,
        backupCount=log_config.get('backup_count', 5)
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('selenium').setLevel(logging.WARNING)