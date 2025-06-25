import json
import os
import requests
from pathlib import Path
import sys

# Load configuration from JSON file
CONFIG_PATH = os.getenv("CONFIG_PATH", "config.json")

def load_config():
    """Load configuration from JSON file with fallback to defaults."""
    try:
        # Try to load config from the specified path
        config_file = Path(CONFIG_PATH)
        if not config_file.is_absolute():
            # If relative path, make it relative to the directory containing this script
            script_dir = Path(__file__).parent
            config_file = script_dir / config_file
        
        if not config_file.exists():
            print(f"Config file not found: {config_file}", file=sys.stderr)
            raise FileNotFoundError(f"Config file not found: {config_file}")
        
        with open(config_file, 'r') as cfg_file:
            return json.load(cfg_file)
    except Exception as e:
        print(f"Error loading config from {CONFIG_PATH}: {e}", file=sys.stderr)
        print("Please run `geo-mcp-server --init` to create a config file.", file=sys.stderr)
        raise e

# Load initial config
config = load_config()

# Base URL and credentials from config
BASE_URL = config.get("base_url", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils")
EMAIL = config["email"]  # This will fail if email is not in config
API_KEY = config.get("api_key")

# Validate required configuration
if not EMAIL:
    print("Error: Email is required for NCBI E-Utils. Please add 'email' to your config.json", file=sys.stderr)
    sys.exit(1)

def _esearch(db: str, term: str, retmax: int = 20) -> dict:
    """Perform an ESearch query and return JSON results."""
    params = {
        'db': db,
        'term': term,
        'retmax': retmax,
        'retmode': 'json',
        'email': EMAIL,
    }
    if API_KEY:
        params['api_key'] = API_KEY
    resp = requests.get(f"{BASE_URL}/esearch.fcgi", params=params)
    resp.raise_for_status()
    return resp.json()


def _esummary(db: str, ids: list) -> dict:
    """Fetch summaries for a list of IDs."""
    params = {
        'db': db,
        'id': ','.join(ids),
        'retmode': 'json',
        'email': EMAIL,
    }
    if API_KEY:
        params['api_key'] = API_KEY
    resp = requests.get(f"{BASE_URL}/esummary.fcgi", params=params)
    resp.raise_for_status()
    return resp.json()


def search_geo_profiles(term: str, retmax: int = 20) -> dict:
    """Search GEO Profiles."""
    data = _esearch('geoprofiles', term, retmax)
    ids = data.get('esearchresult', {}).get('idlist', [])
    return _esummary('geoprofiles', ids)


def search_geo_datasets(term: str, retmax: int = 20) -> dict:
    """Search GEO DataSets."""
    data = _esearch('gds', term, retmax)
    ids = data.get('esearchresult', {}).get('idlist', [])
    return _esummary('gds', ids)


if __name__ == '__main__':
    # Example config.json content:
    # {
    #     "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
    #     "email": "your_email@example.com",
    #     "api_key": "YOUR_API_KEY"
    # }
    term = 'cancer'
    profiles = search_geo_profiles(term)
    print('Profiles:', profiles)
    datasets = search_geo_datasets(term)
    print('DataSets:', datasets)
