import json
import os
import sys
import re
import requests
import asyncio
import aiohttp
import aiofiles
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List

CONFIG_PATH = os.getenv("CONFIG_PATH")  # optional override

# ------------------------------------------------------------------
# Configuration loading
# ------------------------------------------------------------------

def _load_config() -> Dict[str, Any]:
    """Return the first config.json we can find.

    Search order:
      1. $CONFIG_PATH (env‑var) if it points to a real file
      2. ./config.json next to this script
      3. ~/.geo-mcp/config.json (user default)
    """
    candidates: List[Path] = []
    if CONFIG_PATH:
        candidates.append(Path(os.path.expanduser(CONFIG_PATH)))
    candidates.append(Path(__file__).parent / "config.json")
    candidates.append(Path.home() / ".geo-mcp" / "config.json")

    for p in candidates:
        if p.exists():
            with open(p) as f:
                return json.load(f)

    raise FileNotFoundError("No config.json found. Looked in: " + ", ".join(str(p) for p in candidates))


config = _load_config()

# ------------------------------------------------------------------
# Global constants (with sane defaults)
# ------------------------------------------------------------------
BASE_URL = config.get("base_url", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils")
EMAIL = config.get("email")  # this *must* be set – NCBI requirement
API_KEY = config.get("api_key", "")
DOWNLOAD_DIR = config.get("download_dir", "./downloads")
MAX_FILE_MB = config.get("max_file_size_mb", 5000)
MAX_TOTAL_MB = config.get("max_total_downloads_mb", 10000)
MAX_CONCURRENT = config.get("max_concurrent_downloads", 3)
TIMEOUT = config.get("download_timeout_seconds", 300)
ALLOWED_PATHS = config.get("allowed_download_paths", ["./downloads", "/tmp/geo_downloads"])

if not EMAIL:
    print("✘ 'email' is missing in config.json (required by NCBI)", file=sys.stderr)
    sys.exit(1)

# byte helpers
BYTES_IN_MB = 1024 * 1024
MAX_FILE_BYTES = MAX_FILE_MB * BYTES_IN_MB
MAX_TOTAL_BYTES = MAX_TOTAL_MB * BYTES_IN_MB

root_path = Path(DOWNLOAD_DIR)
if not root_path.is_absolute():
    root_path = Path(__file__).parent / root_path

# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------

def _is_child(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _allowed(path: Path) -> bool:
    path = path.resolve()
    for ap in ALLOWED_PATHS:
        p = Path(ap)
        if not p.is_absolute():
            p = Path(__file__).parent / p
        p = p.resolve()
        if path == p or _is_child(path, p):
            return True
    return False


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _disk_free(p: Path) -> int:
    try:
        return shutil.disk_usage(p).free
    except Exception:
        return 0

# ------------------------------------------------------------------
# E‑utilities wrappers
# ------------------------------------------------------------------

def _request(path: str, params: Dict[str, str]) -> requests.Response:
    prm = params.copy()
    prm["email"] = EMAIL
    if API_KEY:
        prm["api_key"] = API_KEY
    resp = requests.get(f"{BASE_URL}/{path}", params=prm)
    resp.raise_for_status()
    return resp


def _esearch_uid(acc: str) -> Optional[str]:
    r = _request("esearch.fcgi", {
        "db": "gds",
        "term": f"{acc}[ACCN]",
        "retmode": "json",
        "retmax": "1",
    })
    ids = r.json().get("esearchresult", {}).get("idlist", [])
    return ids[0] if ids else None


def _efetch_gds(uid: str) -> str:
    return _request("efetch.fcgi", {"db": "gds", "id": uid, "retmode": "xml"}).text


# ------------------------------------------------------------------
# FTP/HTTP link extraction
# ------------------------------------------------------------------

def _extract_ftp_links(xml_text: str) -> List[str]:
    """Return *https* direct links to SOFT archives.

    The XML from GDS often includes only an FTP directory.  This helper:
      • converts any `ftp://` prefix to `https://` (to avoid FTP handling)
      • if the link ends with a GEO accession directory, appends the
        standard SOFT location (`soft/<ACC>[_family].soft.gz`).
    """
    raw_links = re.findall(r"ftp://[\w./-]+", xml_text, re.I)
    cleaned: List[str] = []

    for link in raw_links:
        base = re.sub(r"^ftp://", "https://", link.rstrip("/"))

        # if it's already a file we can use it straight away
        if base.endswith(".soft.gz"):
            cleaned.append(base)
            continue

        # otherwise build the conventional SOFT file path
        m = re.search(r"/(GSE\d+|GSM\d+|GPL\d+|GDS\d+)$", base, re.I)
        if not m:
            continue
        acc = m.group(1)
        soft = f"{base}/soft/{acc}_family.soft.gz" if acc.startswith("GSE") else f"{base}/soft/{acc}.soft.gz"
        cleaned.append(soft)

    return cleaned

# ------------------------------------------------------------------
# Download logic
# ------------------------------------------------------------------
sem = asyncio.Semaphore(MAX_CONCURRENT)


async def download_geo(acc: str, db_type: str, out_dir: Optional[str] = None) -> Dict[str, Any]:
    async with sem:
        dest = Path(out_dir or root_path / db_type / acc)
        if not _allowed(dest):
            raise ValueError("output dir violates ALLOWED_DOWNLOAD_PATHS")
        dest.mkdir(parents=True, exist_ok=True)

        if _dir_size(root_path) >= MAX_TOTAL_BYTES:
            raise ValueError("total download limit reached")

        uid = _esearch_uid(acc)
        if not uid:
            raise ValueError(f"{acc} not found in GDS database")
        xml = _efetch_gds(uid)
        urls = _extract_ftp_links(xml)
        if not urls:
            raise ValueError("no downloadable SOFT file exposed by E‑utilities")

        downloaded: List[str] = []
        total_bytes = 0
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url in urls:
                filename = url.split("/")[-1]
                filepath = dest / filename

                if _disk_free(dest) < MAX_FILE_BYTES * 2:
                    raise ValueError("insufficient disk space to continue")

                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise ValueError(f"download failed with HTTP {resp.status}: {url}")
                    clen = int(resp.headers.get("content-length", "0"))
                    if clen and clen > MAX_FILE_BYTES:
                        raise ValueError("SOFT archive exceeds MAX_FILE_SIZE_MB")

                    sz = 0
                    async with aiofiles.open(filepath, "wb") as fh:
                        async for chunk in resp.content.iter_chunked(8192):
                            sz += len(chunk)
                            if sz > MAX_FILE_BYTES:
                                raise ValueError("file size grew beyond limit during transfer")
                            await fh.write(chunk)
                    total_bytes += sz
                    downloaded.append(str(filepath))

        # save XML metadata next to archives
        meta_path = dest / f"{acc}_metadata.xml"
        meta_path.write_text(xml)
        downloaded.append(str(meta_path))

        return {
            "acc": acc,
            "db_type": db_type,
            "output_dir": str(dest),
            "files": downloaded,
            "total_size_mb": round(total_bytes / BYTES_IN_MB, 2),
        }

# ------------------------------------------------------------------
# Status and management functions
# ------------------------------------------------------------------

def get_download_status(geo_id: str, db_type: str) -> Dict[str, Any]:
    """Check if a GEO dataset has been downloaded."""
    try:
        dataset_path = root_path / db_type / geo_id
        if dataset_path.exists():
            files = list(dataset_path.glob("*"))
            total_size = sum(f.stat().st_size for f in files if f.is_file())
            return {
                "geo_id": geo_id,
                "db_type": db_type,
                "downloaded": True,
                "path": str(dataset_path),
                "files": [f.name for f in files],
                "total_size_mb": round(total_size / BYTES_IN_MB, 2)
            }
        else:
            return {
                "geo_id": geo_id,
                "db_type": db_type,
                "downloaded": False,
                "path": str(dataset_path)
            }
    except Exception as e:
        return {
            "geo_id": geo_id,
            "db_type": db_type,
            "downloaded": False,
            "error": str(e)
        }

def list_downloaded_datasets(db_type: str = None) -> Dict[str, Any]:
    """List all downloaded datasets, optionally filtered by database type."""
    try:
        datasets = []
        if db_type:
            db_path = root_path / db_type
            if db_path.exists():
                for dataset_dir in db_path.iterdir():
                    if dataset_dir.is_dir():
                        datasets.append({
                            "geo_id": dataset_dir.name,
                            "db_type": db_type,
                            "path": str(dataset_dir)
                        })
        else:
            for db_dir in root_path.iterdir():
                if db_dir.is_dir():
                    for dataset_dir in db_dir.iterdir():
                        if dataset_dir.is_dir():
                            datasets.append({
                                "geo_id": dataset_dir.name,
                                "db_type": db_dir.name,
                                "path": str(dataset_dir)
                            })
        
        return {
            "datasets": datasets,
            "count": len(datasets)
        }
    except Exception as e:
        return {
            "error": str(e),
            "datasets": [],
            "count": 0
        }

def get_download_stats() -> Dict[str, Any]:
    """Get overall download statistics and limits."""
    try:
        total_size = _dir_size(root_path)
        total_size_mb = round(total_size / BYTES_IN_MB, 2)
        
        return {
            "download_dir": str(root_path),
            "total_downloaded_mb": total_size_mb,
            "max_total_mb": MAX_TOTAL_MB,
            "max_file_mb": MAX_FILE_MB,
            "max_concurrent": MAX_CONCURRENT,
            "timeout_seconds": TIMEOUT,
            "allowed_paths": ALLOWED_PATHS,
            "disk_free_mb": round(_disk_free(root_path) / BYTES_IN_MB, 2)
        }
    except Exception as e:
        return {
            "error": str(e),
            "download_dir": str(root_path)
        }

def cleanup_downloads(geo_id: str = None, db_type: str = None) -> Dict[str, Any]:
    """Clean up downloaded files."""
    try:
        removed = []
        
        if geo_id and db_type:
            # Remove specific dataset
            dataset_path = root_path / db_type / geo_id
            if dataset_path.exists():
                shutil.rmtree(dataset_path)
                removed.append(str(dataset_path))
        elif db_type:
            # Remove all datasets of a specific type
            db_path = root_path / db_type
            if db_path.exists():
                for dataset_dir in db_path.iterdir():
                    if dataset_dir.is_dir():
                        shutil.rmtree(dataset_dir)
                        removed.append(str(dataset_dir))
        else:
            # Remove all downloads
            if root_path.exists():
                shutil.rmtree(root_path)
                removed.append(str(root_path))
        
        return {
            "removed": removed,
            "count": len(removed)
        }
    except Exception as e:
        return {
            "error": str(e),
            "removed": [],
            "count": 0
        }

# ------------------------------------------------------------------
# Minimal CLI example
# ------------------------------------------------------------------
if __name__ == "__main__":
    import argparse, json as _json

    parser = argparse.ArgumentParser(description="Download GEO SOFT archives using E‑utilities only")
    parser.add_argument("acc", nargs="?", default="GSE10072", help="GEO accession (e.g. GSE10072)")
    parser.add_argument("--db", dest="db", default="gse", help="Database type: gse/gsm/gpl/gds")
    args = parser.parse_args()

    try:
        result = asyncio.run(download_geo(args.acc, args.db))
        print(_json.dumps(result, indent=2))
    except Exception as exc:
        print(f"✘ {exc}", file=sys.stderr)
        sys.exit(1)
