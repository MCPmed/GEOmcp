import json
import os
import requests
from pathlib import Path
import sys
import time

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
        print("Please run `geo-mcp --init` to create a config file.", file=sys.stderr)
        raise e

def _get_config():
    """Get configuration, loading it when needed."""
    try:
        return load_config()
    except Exception:
        # Return default config for basic functionality
        return {
            "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
            "email": None,
            "api_key": None
        }

def _esearch(db: str, term: str, retmax: int = 20) -> dict:
    """Perform an ESearch query and return JSON results."""
    config = _get_config()
    email = config.get("email")
    
    # Make email optional with warning
    if not email:
        print("Warning: No email configured for NCBI E-Utils. Consider adding one for better compliance.", file=sys.stderr)
    
    params = {
        'db': db,
        'term': term,
        'retmax': retmax,
        'retmode': 'json',
    }
    
    # Only add email if configured
    if email:
        params['email'] = email
    
    api_key = config.get("api_key")
    if api_key:
        params['api_key'] = api_key
    
    # Add rate limiting to be respectful to NCBI servers
    time.sleep(0.1)
    
    try:
        resp = requests.get(f"{config.get('base_url', 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils')}/esearch.fcgi", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"Error during esearch: {e}", file=sys.stderr)
        raise

def _esummary(db: str, ids: list) -> dict:
    """Fetch summaries for a list of IDs."""
    if not ids:
        return {"result": {}}
    
    config = _get_config()
    email = config.get("email")
    
    params = {
        'db': db,
        'id': ','.join(map(str, ids)),
        'retmode': 'json',
    }
    
    # Only add email if configured
    if email:
        params['email'] = email
    
    api_key = config.get("api_key")
    if api_key:
        params['api_key'] = api_key
    
    # Add rate limiting
    time.sleep(0.1)
    
    try:
        resp = requests.get(f"{config.get('base_url', 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils')}/esummary.fcgi", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"Error during esummary: {e}", file=sys.stderr)
        raise

def search_geo(term: str, retmax: int = 20, record_types: list = None) -> dict:
    """
    Universal GEO search function that finds all relevant records.
    
    Args:
        term: Search term (e.g., "breast cancer", "GSE12345", "RNA-seq")
        retmax: Maximum number of results to return
        record_types: Optional filter for specific types ["GSE", "GSM", "GPL", "GDS"]
    
    Returns:
        Dict with categorized results by record type
    """
    try:
        # Search the gds database which contains most GEO records
        data = _esearch('gds', term, retmax)
        ids = data.get('esearchresult', {}).get('idlist', [])
        
        if not ids:
            return {
                "total_count": 0,
                "results": [],
                "series": [],
                "samples": [], 
                "platforms": [],
                "datasets": []
            }
        
        # Get detailed summaries
        summaries = _esummary('gds', ids)
        results = summaries.get('result', {})
        
        # Categorize results by accession type
        categorized = {
            "total_count": len(ids),
            "results": [],
            "series": [],      # GSE records
            "samples": [],     # GSM records  
            "platforms": [],   # GPL records
            "datasets": []     # GDS records
        }
        
        for uid in ids:
            if uid in results:
                record = results[uid]
                accession = record.get('accession', '')
                
                # Add to main results
                categorized["results"].append(record)
                
                # Categorize by type
                if accession.startswith('GSE'):
                    categorized["series"].append(record)
                elif accession.startswith('GSM'):
                    categorized["samples"].append(record)
                elif accession.startswith('GPL'):
                    categorized["platforms"].append(record)
                elif accession.startswith('GDS'):
                    categorized["datasets"].append(record)
        
        # Filter by record types if specified
        if record_types:
            record_types = [rt.upper() for rt in record_types]
            filtered_results = []
            
            if "GSE" in record_types:
                filtered_results.extend(categorized["series"])
            if "GSM" in record_types:
                filtered_results.extend(categorized["samples"])
            if "GPL" in record_types:
                filtered_results.extend(categorized["platforms"])
            if "GDS" in record_types:
                filtered_results.extend(categorized["datasets"])
            
            categorized["results"] = filtered_results
            categorized["total_count"] = len(filtered_results)
        
        return categorized
        
    except Exception as e:
        print(f"Error in search_geo: {e}", file=sys.stderr)
        return {
            "total_count": 0,
            "results": [],
            "series": [],
            "samples": [],
            "platforms": [],
            "datasets": [],
            "error": str(e)
        }

def search_geo_profiles(term: str, retmax: int = 20) -> dict:
    """Search GEO Profiles - keeping original functionality."""
    try:
        data = _esearch('geoprofiles', term, retmax)
        ids = data.get('esearchresult', {}).get('idlist', [])
        if not ids:
            return {"esummaryresult": ["Empty id list - nothing todo"]}
        summary = _esummary('geoprofiles', ids)
        return summary
    except Exception as e:
        print(f"Error in search_geo_profiles: {e}", file=sys.stderr)
        return {"esummaryresult": ["Empty id list - nothing todo"], "error": str(e)}

def search_geo_datasets(term: str, retmax: int = 20) -> dict:
    """Search for GEO Dataset (GDS) records only."""
    try:
        result = search_geo(term, retmax, record_types=["GDS"])
        
        # Format to match expected output structure
        if result["datasets"]:
            formatted_result = {
                "header": {"type": "esummary", "version": "0.3"},
                "result": {
                    "uids": [r.get("uid") for r in result["datasets"]]
                }
            }
            # Add each record to the result dict
            for record in result["datasets"]:
                uid = record.get("uid")
                if uid:
                    formatted_result["result"][uid] = record
            
            return formatted_result
        else:
            return {"esummaryresult": ["Empty id list - nothing todo"]}
            
    except Exception as e:
        print(f"Error in search_geo_datasets: {e}", file=sys.stderr)
        return {"esummaryresult": ["Empty id list - nothing todo"], "error": str(e)}

def search_geo_series(term: str, retmax: int = 20) -> dict:
    """Search for GEO Series (GSE) records only."""
    try:
        result = search_geo(term, retmax, record_types=["GSE"])
        
        # Format to match expected output structure
        if result["series"]:
            formatted_result = {
                "header": {"type": "esummary", "version": "0.3"},
                "result": {
                    "uids": [r.get("uid") for r in result["series"]]
                }
            }
            # Add each record to the result dict
            for record in result["series"]:
                uid = record.get("uid")
                if uid:
                    formatted_result["result"][uid] = record
            
            return formatted_result
        else:
            return {"esummaryresult": ["Empty id list - nothing todo"]}
            
    except Exception as e:
        print(f"Error in search_geo_series: {e}", file=sys.stderr)
        return {"esummaryresult": ["Empty id list - nothing todo"], "error": str(e)}

def search_geo_samples(term: str, retmax: int = 20) -> dict:
    """Search for GEO Sample (GSM) records only."""
    try:
        result = search_geo(term, retmax, record_types=["GSM"])
        
        # Format to match expected output structure
        if result["samples"]:
            formatted_result = {
                "header": {"type": "esummary", "version": "0.3"},
                "result": {
                    "uids": [r.get("uid") for r in result["samples"]]
                }
            }
            # Add each record to the result dict
            for record in result["samples"]:
                uid = record.get("uid")
                if uid:
                    formatted_result["result"][uid] = record
            
            return formatted_result
        else:
            return {"esummaryresult": ["Empty id list - nothing todo"]}
            
    except Exception as e:
        print(f"Error in search_geo_samples: {e}", file=sys.stderr)
        return {"esummaryresult": ["Empty id list - nothing todo"], "error": str(e)}

def search_geo_platforms(term: str, retmax: int = 20) -> dict:
    """Search for GEO Platform (GPL) records only."""
    try:
        result = search_geo(term, retmax, record_types=["GPL"])
        
        # Format to match expected output structure
        if result["platforms"]:
            formatted_result = {
                "header": {"type": "esummary", "version": "0.3"},
                "result": {
                    "uids": [r.get("uid") for r in result["platforms"]]
                }
            }
            # Add each record to the result dict
            for record in result["platforms"]:
                uid = record.get("uid")
                if uid:
                    formatted_result["result"][uid] = record
            
            return formatted_result
        else:
            return {"esummaryresult": ["Empty id list - nothing todo"]}
            
    except Exception as e:
        print(f"Error in search_geo_platforms: {e}", file=sys.stderr)
        return {"esummaryresult": ["Empty id list - nothing todo"], "error": str(e)}

def download_geo_data(geo_id: str, output_dir: str = "downloads") -> str:
    """Download GEO data file."""
    try:
        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Determine the correct URL based on GEO ID type
        if geo_id.startswith('GSE'):
            # Series data
            url = f"https://ftp.ncbi.nlm.nih.gov/geo/series/{geo_id[:-3]}nnn/{geo_id}/matrix/{geo_id}_series_matrix.txt.gz"
        elif geo_id.startswith('GDS'):
            # Dataset data
            url = f"https://ftp.ncbi.nlm.nih.gov/geo/datasets/{geo_id[:-3]}nnn/{geo_id}/soft/{geo_id}.soft.gz"
        elif geo_id.startswith('GPL'):
            # Platform data
            url = f"https://ftp.ncbi.nlm.nih.gov/geo/platforms/{geo_id[:-3]}nnn/{geo_id}/annot/{geo_id}.annot.gz"
        else:
            raise ValueError(f"Unsupported GEO ID format: {geo_id}")
        
        filename = os.path.join(output_dir, url.split('/')[-1])
        
        print(f"Downloading {geo_id} from {url}...", file=sys.stderr)
        
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"Downloaded: {filename}", file=sys.stderr)
        return filename
        
    except Exception as e:
        print(f"Error downloading {geo_id}: {e}", file=sys.stderr)
        raise

def list_downloaded_datasets(output_dir: str = "downloads") -> list:
    """List all downloaded datasets."""
    try:
        download_path = Path(output_dir)
        if not download_path.exists():
            return []
        
        files = list(download_path.glob("*"))
        return [str(f) for f in files if f.is_file()]
    except Exception as e:
        print(f"Error listing downloads: {e}", file=sys.stderr)
        return []

def get_download_stats(output_dir: str = "downloads") -> dict:
    """Get statistics about downloaded files."""
    try:
        files = list_downloaded_datasets(output_dir)
        total_size = 0
        
        for file_path in files:
            try:
                total_size += Path(file_path).stat().st_size
            except OSError:
                continue
        
        return {
            "total_files": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "files": files
        }
    except Exception as e:
        print(f"Error getting download stats: {e}", file=sys.stderr)
        return {"total_files": 0, "total_size_bytes": 0, "total_size_mb": 0, "files": []}

if __name__ == '__main__':
    # Example usage
    try:
        term = 'cancer'
        print(f"Searching for: {term}")
        
        # Test the new universal search function
        print("\n=== Testing universal search function ===")
        all_results = search_geo(term, 10)
        print(f"Total found: {all_results['total_count']}")
        print(f"- Series (GSE): {len(all_results['series'])}")
        print(f"- Samples (GSM): {len(all_results['samples'])}")
        print(f"- Platforms (GPL): {len(all_results['platforms'])}")
        print(f"- Datasets (GDS): {len(all_results['datasets'])}")
        
        # Test individual functions
        print("\n=== Testing individual search functions ===")
        
        datasets = search_geo_datasets(term, 5)
        dataset_count = len(datasets.get('result', {}).get('uids', []))
        print(f"DataSets found: {dataset_count}")
        
        series = search_geo_series(term, 5)
        series_count = len(series.get('result', {}).get('uids', []))
        print(f"Series found: {series_count}")
        
        samples = search_geo_samples(term, 5)
        samples_count = len(samples.get('result', {}).get('uids', []))
        print(f"Samples found: {samples_count}")
        
        platforms = search_geo_platforms("Illumina", 5)
        platforms_count = len(platforms.get('result', {}).get('uids', []))
        print(f"Illumina platforms found: {platforms_count}")
        
    except Exception as e:
        print(f"Error in main: {e}", file=sys.stderr)
        sys.exit(1)