import yaml
import os
from typing import Dict, Any


def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Create directories if they don't exist
    os.makedirs(config['http']['cache_dir'], exist_ok=True)
    os.makedirs(os.path.dirname(config['storage']['path']), exist_ok=True)
    os.makedirs(os.path.dirname(config['logging']['file']), exist_ok=True)

    return config