"""Configuration management for GEO MCP Server."""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional


# Default configuration values
DEFAULT_CONFIG = {
    "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
    "sra_base_url": "https://trace.ncbi.nlm.nih.gov/Traces/sra",
    "email": None,
    "api_key": None,
    "retmax": 20,
    "download_dir": "./downloads",
    "max_file_size_mb": 5000,
    "max_total_downloads_mb": 50000,
    "max_concurrent_downloads": 3,
    "download_timeout_seconds": 300,
    "sra_toolkit_path": None,  # Path to sra-toolkit (prefetch/fasterq-dump)
    "allowed_download_paths": ["./downloads", "/tmp/geo_downloads"],
}


def find_config_file() -> Optional[Path]:
    """Find configuration file in standard locations."""
    # Check environment variable first
    env_config = os.getenv("CONFIG_PATH")
    if env_config:
        path = Path(env_config).expanduser()
        if path.exists():
            return path
    
    # Check current directory
    current_dir = Path.cwd() / "config.json"
    if current_dir.exists():
        return current_dir
    
    # Check module directory
    module_dir = Path(__file__).parent / "config.json"
    if module_dir.exists():
        return module_dir
    
    # Check user home directory
    home_config = Path.home() / ".geo-mcp" / "config.json"
    if home_config.exists():
        return home_config
    
    return None


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load configuration from file or use defaults.
    
    Args:
        config_path: Optional explicit path to config file
        
    Returns:
        Configuration dictionary
    """
    config = DEFAULT_CONFIG.copy()
    
    # Find config file
    if config_path is None:
        config_path = find_config_file()
    
    if config_path and config_path.exists():
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                config.update(user_config)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Error loading config from {config_path}: {e}", file=sys.stderr)
    
    # Override with environment variables
    if os.getenv("NCBI_EMAIL"):
        config["email"] = os.getenv("NCBI_EMAIL")
    if os.getenv("NCBI_API_KEY"):
        config["api_key"] = os.getenv("NCBI_API_KEY")
    if os.getenv("GEO_DOWNLOAD_DIR"):
        config["download_dir"] = os.getenv("GEO_DOWNLOAD_DIR")
    if os.getenv("SRA_TOOLKIT_PATH"):
        config["sra_toolkit_path"] = os.getenv("SRA_TOOLKIT_PATH")
    
    return config


def validate_config(config: Dict[str, Any]) -> bool:
    """Validate configuration values.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        True if valid, raises ValueError otherwise
    """
    if not config.get("email"):
        raise ValueError(
            "Email is required for NCBI E-utilities. "
            "Set it in config.json or via NCBI_EMAIL environment variable."
        )
    
    # Validate download directory
    download_dir = Path(config.get("download_dir", "./downloads"))
    try:
        download_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ValueError(f"Cannot create download directory: {e}")
    
    return True


def create_config_template(path: Path) -> None:
    """Create a configuration file template.
    
    Args:
        path: Path where to create the config file
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    template = {
        "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        "sra_base_url": "https://trace.ncbi.nlm.nih.gov/Traces/sra",
        "email": "your_email@example.com",
        "api_key": "YOUR_NCBI_API_KEY (optional)",
        "retmax": 20,
        "download_dir": "./downloads",
        "max_file_size_mb": 5000,
        "max_total_downloads_mb": 50000,
        "max_concurrent_downloads": 3,
        "download_timeout_seconds": 300,
        "sra_toolkit_path": "/path/to/sra-toolkit/bin (optional, for fasterq-dump)",
        "allowed_download_paths": ["./downloads", "/tmp/geo_downloads"]
    }
    
    with open(path, 'w') as f:
        json.dump(template, f, indent=4)
    
    print(f"Configuration template created at: {path}")


# Global config instance (lazy loading)
_config: Optional[Dict[str, Any]] = None


def get_config() -> Dict[str, Any]:
    """Get the global configuration instance.
    
    Returns:
        Configuration dictionary
    """
    global _config
    if _config is None:
        _config = load_config()
        validate_config(_config)
    return _config
