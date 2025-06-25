import json
import os
import sys
from pathlib import Path
from typing import Any

import mcp.server
import mcp.types as types
import requests

# Import downloader functionality
from geo_downloader import (
    download_geo, 
    get_download_status, 
    list_downloaded_datasets, 
    cleanup_downloads,
    get_download_stats
)


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
            # Try alternative locations like main.py does
            config_dir = Path.home() / ".geo-mcp"
            config_file = config_dir / "config.json"
            
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
EMAIL = config.get("email")
API_KEY = config.get("api_key")
RETMAX = config.get("retmax", 20)

# Validate required configuration
if not EMAIL:
    print("Error: Email is required for NCBI E-Utils. Please add 'email' to your config.json", file=sys.stderr)
    sys.exit(1)

# Create MCP server
server = mcp.server.Server("geo-mcp-server")


def _esearch(db: str, term: str, retmax: int = 1) -> dict:
    """Perform an ESearch query and return JSON results."""
    params = {
        'db': db,
        'term': term,
        'retmax': retmax,
        'retmode': 'json',
        'email': EMAIL,
    }
    # Always include API key if available (provides higher rate limits)
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
    # Always include API key if available (provides higher rate limits)
    if API_KEY:
        params['api_key'] = API_KEY
    resp = requests.get(f"{BASE_URL}/esummary.fcgi", params=params)
    resp.raise_for_status()
    return resp.json()


def search_geo_profiles(term: str, retmax: int = None) -> dict:
    """Search GEO Profiles database for gene expression profiles."""
    if retmax is None:
        retmax = RETMAX
    data = _esearch('geoprofiles', term, retmax)
    ids = data.get('esearchresult', {}).get('idlist', [])
    return _esummary('geoprofiles', ids)


def search_geo_datasets(term: str, retmax: int = None) -> dict:
    """Search GEO DataSets database for gene expression datasets."""
    if retmax is None:
        retmax = RETMAX
    data = _esearch('gds', term, retmax)
    ids = data.get('esearchresult', {}).get('idlist', [])
    return _esummary('gds', ids)


def search_geo_series(term: str, retmax: int = None) -> dict:
    """Search GEO Series database for gene expression series."""
    if retmax is None:
        retmax = RETMAX
    data = _esearch('gse', term, retmax)
    ids = data.get('esearchresult', {}).get('idlist', [])
    return _esummary('gse', ids)


def search_geo_samples(term: str, retmax: int = None) -> dict:
    """Search GEO Samples database for gene expression samples."""
    if retmax is None:
        retmax = RETMAX
    data = _esearch('gsm', term, retmax)
    ids = data.get('esearchresult', {}).get('idlist', [])
    return _esummary('gsm', ids)


def search_geo_platforms(term: str, retmax: int = None) -> dict:
    """Search GEO Platforms database for microarray platforms."""
    if retmax is None:
        retmax = RETMAX
    data = _esearch('gpl', term, retmax)
    ids = data.get('esearchresult', {}).get('idlist', [])
    return _esummary('gpl', ids)


def _get_current_retmax() -> int:
    """Get the current retmax value from config file."""
    try:
        current_config = load_config()
        return current_config.get("retmax", RETMAX)
    except Exception as e:
        print(f"Error loading config for retmax: {e}", file=sys.stderr)
        sys.exit(1)


def _get_tool_schemas() -> list[types.Tool]:
    """Dynamically generate tool schemas with current config values."""
    # Reload config to get current values
    try:
        current_config = load_config()
        current_retmax = current_config.get("retmax", 20)
    except Exception as e:
        print(f"Error loading config for tool schemas: {e}", file=sys.stderr)
        sys.exit(1)
    
    return [
        types.Tool(
            name="search_geo_profiles",
            description="Search GEO Profiles database for gene expression profiles",
            inputSchema={
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "Search term for GEO Profiles"
                    },
                    "retmax": {
                        "type": "integer",
                        "description": f"Maximum number of results to return (default: {current_retmax})",
                        "default": current_retmax
                    }
                },
                "required": ["term"]
            }
        ),
        types.Tool(
            name="search_geo_datasets",
            description="Search GEO DataSets database for gene expression datasets",
            inputSchema={
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "Search term for GEO DataSets"
                    },
                    "retmax": {
                        "type": "integer",
                        "description": f"Maximum number of results to return (default: {current_retmax})",
                        "default": current_retmax
                    }
                },
                "required": ["term"]
            }
        ),
        types.Tool(
            name="search_geo_series",
            description="Search GEO Series database for gene expression series",
            inputSchema={
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "Search term for GEO Series"
                    },
                    "retmax": {
                        "type": "integer",
                        "description": f"Maximum number of results to return (default: {current_retmax})",
                        "default": current_retmax
                    }
                },
                "required": ["term"]
            }
        ),
        types.Tool(
            name="search_geo_samples",
            description="Search GEO Samples database for gene expression samples",
            inputSchema={
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "Search term for GEO Samples"
                    },
                    "retmax": {
                        "type": "integer",
                        "description": f"Maximum number of results to return (default: {current_retmax})",
                        "default": current_retmax
                    }
                },
                "required": ["term"]
            }
        ),
        types.Tool(
            name="search_geo_platforms",
            description="Search GEO Platforms database for microarray platforms",
            inputSchema={
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "Search term for GEO Platforms"
                    },
                    "retmax": {
                        "type": "integer",
                        "description": f"Maximum number of results to return (default: {current_retmax})",
                        "default": current_retmax
                    }
                },
                "required": ["term"]
            }
        ),
        types.Tool(
            name="download_geo_data",
            description="Download GEO data for a specific ID and database type",
            inputSchema={
                "type": "object",
                "properties": {
                    "geo_id": {
                        "type": "string",
                        "description": "GEO ID to download (e.g., GSE12345, GSM12345)"
                    },
                    "db_type": {
                        "type": "string",
                        "description": "Database type: gds, gse, gsm, or gpl",
                        "enum": ["gds", "gse", "gsm", "gpl"]
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Optional output directory (must be in allowed paths)"
                    }
                },
                "required": ["geo_id", "db_type"]
            }
        ),
        types.Tool(
            name="download_geo_batch",
            description="Download multiple GEO datasets in batch",
            inputSchema={
                "type": "object",
                "properties": {
                    "geo_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of GEO IDs to download"
                    },
                    "db_type": {
                        "type": "string",
                        "description": "Database type: gds, gse, gsm, or gpl",
                        "enum": ["gds", "gse", "gsm", "gpl"]
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Optional output directory (must be in allowed paths)"
                    }
                },
                "required": ["geo_ids", "db_type"]
            }
        ),
        types.Tool(
            name="get_download_status",
            description="Check if a GEO dataset has been downloaded",
            inputSchema={
                "type": "object",
                "properties": {
                    "geo_id": {
                        "type": "string",
                        "description": "GEO ID to check"
                    },
                    "db_type": {
                        "type": "string",
                        "description": "Database type: gds, gse, gsm, or gpl",
                        "enum": ["gds", "gse", "gsm", "gpl"]
                    }
                },
                "required": ["geo_id", "db_type"]
            }
        ),
        types.Tool(
            name="list_downloaded_datasets",
            description="List all downloaded datasets",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_type": {
                        "type": "string",
                        "description": "Optional database type filter: gds, gse, gsm, or gpl",
                        "enum": ["gds", "gse", "gsm", "gpl"]
                    }
                }
            }
        ),
        types.Tool(
            name="get_download_stats",
            description="Get overall download statistics and limits",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="cleanup_downloads",
            description="Clean up downloaded files",
            inputSchema={
                "type": "object",
                "properties": {
                    "geo_id": {
                        "type": "string",
                        "description": "Optional specific GEO ID to remove"
                    },
                    "db_type": {
                        "type": "string",
                        "description": "Optional database type to remove all datasets from",
                        "enum": ["gds", "gse", "gsm", "gpl"]
                    }
                }
            }
        )
    ]


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List the available tools."""
    return _get_tool_schemas()


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls."""
    current_retmax = _get_current_retmax()
    
    if name == "search_geo_profiles":
        term = arguments["term"]
        retmax = arguments.get("retmax", current_retmax)
        result = search_geo_profiles(term, retmax)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "search_geo_datasets":
        term = arguments["term"]
        retmax = arguments.get("retmax", current_retmax)
        result = search_geo_datasets(term, retmax)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "search_geo_series":
        term = arguments["term"]
        retmax = arguments.get("retmax", current_retmax)
        result = search_geo_series(term, retmax)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "search_geo_samples":
        term = arguments["term"]
        retmax = arguments.get("retmax", current_retmax)
        result = search_geo_samples(term, retmax)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "search_geo_platforms":
        term = arguments["term"]
        retmax = arguments.get("retmax", current_retmax)
        result = search_geo_platforms(term, retmax)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "download_geo_data":
        geo_id = arguments["geo_id"]
        db_type = arguments["db_type"]
        output_dir = arguments.get("output_dir")
        result = await download_geo(geo_id, db_type, output_dir)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "download_geo_batch":
        geo_ids = arguments["geo_ids"]
        db_type = arguments["db_type"]
        output_dir = arguments.get("output_dir")
        # For batch downloads, we'll process them sequentially for now
        results = []
        for geo_id in geo_ids:
            try:
                result = await download_geo(geo_id, db_type, output_dir)
                results.append(result)
            except Exception as e:
                results.append({"geo_id": geo_id, "error": str(e)})
        return [types.TextContent(type="text", text=json.dumps(results, indent=2))]
    
    elif name == "get_download_status":
        geo_id = arguments["geo_id"]
        db_type = arguments["db_type"]
        result = get_download_status(geo_id, db_type)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "list_downloaded_datasets":
        db_type = arguments.get("db_type")
        result = list_downloaded_datasets(db_type)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_download_stats":
        result = get_download_stats()
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "cleanup_downloads":
        geo_id = arguments.get("geo_id")
        db_type = arguments.get("db_type")
        result = cleanup_downloads(geo_id, db_type)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}") 