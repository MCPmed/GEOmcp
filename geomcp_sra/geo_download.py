"""GEO data download functionality."""

import asyncio
import gzip
import json
import os
import re
import shutil
import tarfile
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
import aiofiles

from .config import get_config


class GEODownloadError(Exception):
    """Exception raised for GEO download errors."""
    pass


class GEODownloadClient:
    """Client for downloading GEO data files."""
    
    # GEO FTP base URL (using HTTPS)
    GEO_FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/geo"
    
    def __init__(self):
        self.config = get_config()
        self.download_dir = Path(self.config["download_dir"]).resolve()
        self.max_file_bytes = self.config.get("max_file_size_mb", 5000) * 1024 * 1024
        self.max_total_bytes = self.config.get("max_total_downloads_mb", 50000) * 1024 * 1024
        self.timeout = self.config.get("download_timeout_seconds", 300)
        self.allowed_paths = self.config.get("allowed_download_paths", ["./downloads"])
        
        # Create download directory
        self.download_dir.mkdir(parents=True, exist_ok=True)
    
    def _is_allowed_path(self, path: Path) -> bool:
        """Check if path is within allowed download directories."""
        path = path.resolve()
        for allowed in self.allowed_paths:
            allowed_path = Path(allowed).resolve()
            try:
                path.relative_to(allowed_path)
                return True
            except ValueError:
                continue
        return False
    
    def _get_dir_size(self, path: Path) -> int:
        """Calculate total size of files in directory."""
        total = 0
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total
    
    def _get_range_dir(self, accession: str) -> str:
        """Get range directory for GEO accession.
        
        GEO uses range directories to avoid too many files in one directory.
        E.g., GSE15701 -> GSE15nnn
        """
        match = re.match(r'(GSE|GSM|GPL|GDS)(\d+)', accession, re.IGNORECASE)
        if match:
            prefix = match.group(1).upper()
            number = match.group(2)
            return f"{prefix}{number[:-3]}nnn"
        return accession
    
    def _build_geo_urls(self, accession: str) -> Dict[str, str]:
        """Build download URLs for a GEO accession.
        
        Args:
            accession: GEO accession ID
            
        Returns:
            Dictionary of file types to URLs
        """
        urls = {}
        prefix = accession[:3].upper()
        range_dir = self._get_range_dir(accession)
        base_url = f"{self.GEO_FTP_BASE}"
        
        if prefix == "GSE":
            # Series files
            base = f"{base_url}/series/{range_dir}/{accession}"
            urls["series_matrix"] = f"{base}/matrix/{accession}_series_matrix.txt.gz"
            urls["soft"] = f"{base}/soft/{accession}_family.soft.gz"
            urls["miniml"] = f"{base}/miniml/{accession}_family.xml.tgz"
            urls["supplementary"] = f"{base}/suppl/{accession}_RAW.tar"
        elif prefix == "GDS":
            # Dataset files
            base = f"{base_url}/datasets/{range_dir}/{accession}"
            urls["soft"] = f"{base}/soft/{accession}.soft.gz"
            urls["soft_full"] = f"{base}/soft/{accession}_full.soft.gz"
        elif prefix == "GPL":
            # Platform files
            base = f"{base_url}/platforms/{range_dir}/{accession}"
            urls["annot"] = f"{base}/annot/{accession}.annot.gz"
            urls["soft"] = f"{base}/soft/{accession}_family.soft.gz"
            urls["supplementary"] = f"{base}/suppl/"
        elif prefix == "GSM":
            # Sample files
            base = f"{base_url}/samples/{range_dir}/{accession}"
            urls["supplementary"] = f"{base}/suppl/"
        
        return urls
    
    async def download_file(
        self, 
        url: str, 
        dest_path: Path,
        progress_callback: Optional[callable] = None
    ) -> Path:
        """Download a single file.
        
        Args:
            url: URL to download
            dest_path: Destination path
            progress_callback: Optional callback for progress updates
            
        Returns:
            Path to downloaded file
        """
        if not self._is_allowed_path(dest_path):
            raise GEODownloadError(f"Destination path not allowed: {dest_path}")
        
        # Check total download limit
        current_total = self._get_dir_size(self.download_dir)
        if current_total >= self.max_total_bytes:
            raise GEODownloadError("Total download limit reached")
        
        # Check disk space
        free_space = shutil.disk_usage(dest_path.parent).free
        if free_space < self.max_file_bytes:
            raise GEODownloadError("Insufficient disk space")
        
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET", 
                url, 
                timeout=self.timeout,
                follow_redirects=True
            ) as response:
                response.raise_for_status()
                
                # Check content length
                content_length = response.headers.get('content-length')
                if content_length:
                    size = int(content_length)
                    if size > self.max_file_bytes:
                        raise GEODownloadError(
                            f"File size ({size} bytes) exceeds maximum allowed"
                        )
                
                # Download file
                downloaded = 0
                async with aiofiles.open(dest_path, 'wb') as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        downloaded += len(chunk)
                        if downloaded > self.max_file_bytes:
                            dest_path.unlink()
                            raise GEODownloadError("File size exceeded limit during download")
                        await f.write(chunk)
                        
                        if progress_callback:
                            progress_callback(downloaded)
        
        return dest_path
    
    async def download_geo_series(
        self,
        gse_id: str,
        file_types: Optional[List[str]] = None,
        output_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Download files for a GEO Series.
        
        Args:
            gse_id: GSE accession ID
            file_types: List of file types to download (soft, matrix, miniml, supplementary)
            output_dir: Optional custom output directory
            
        Returns:
            Download results dictionary
        """
        if not gse_id.upper().startswith("GSE"):
            raise GEODownloadError(f"Invalid GSE ID: {gse_id}")
        
        file_types = file_types or ["soft"]
        output_dir = output_dir or self.download_dir / "series" / gse_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        urls = self._build_geo_urls(gse_id)
        downloaded = []
        errors = []
        
        for file_type in file_types:
            if file_type not in urls:
                errors.append(f"Unknown file type: {file_type}")
                continue
            
            url = urls[file_type]
            filename = url.split("/")[-1]
            dest_path = output_dir / filename
            
            # Skip if already exists
            if dest_path.exists():
                downloaded.append({
                    "type": file_type,
                    "path": str(dest_path),
                    "status": "already_exists",
                    "size_mb": round(dest_path.stat().st_size / (1024*1024), 2)
                })
                continue
            
            try:
                await self.download_file(url, dest_path)
                downloaded.append({
                    "type": file_type,
                    "path": str(dest_path),
                    "status": "downloaded",
                    "size_mb": round(dest_path.stat().st_size / (1024*1024), 2)
                })
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    errors.append(f"{file_type}: File not found on server")
                else:
                    errors.append(f"{file_type}: HTTP {e.response.status_code}")
            except Exception as e:
                errors.append(f"{file_type}: {str(e)}")
        
        return {
            "accession": gse_id,
            "output_dir": str(output_dir),
            "downloaded": downloaded,
            "errors": errors,
            "total_downloaded": len([d for d in downloaded if d["status"] == "downloaded"])
        }
    
    async def download_geo_sample(
        self,
        gsm_id: str,
        output_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Download supplementary files for a GEO Sample.
        
        Args:
            gsm_id: GSM accession ID
            output_dir: Optional custom output directory
            
        Returns:
            Download results dictionary
        """
        if not gsm_id.upper().startswith("GSM"):
            raise GEODownloadError(f"Invalid GSM ID: {gsm_id}")
        
        output_dir = output_dir or self.download_dir / "samples" / gsm_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Get the supplementary file listing
        urls = self._build_geo_urls(gsm_id)
        suppl_url = urls.get("supplementary")
        
        if not suppl_url:
            return {
                "accession": gsm_id,
                "output_dir": str(output_dir),
                "downloaded": [],
                "errors": ["No supplementary files URL available"]
            }
        
        # For samples, we need to list and download files
        # This requires parsing the directory listing
        downloaded = []
        errors = []
        
        try:
            # Try to get directory listing
            async with httpx.AsyncClient() as client:
                response = await client.get(suppl_url, timeout=30.0)
                if response.status_code == 200:
                    # Parse HTML directory listing
                    files = self._parse_directory_listing(response.text)
                    
                    for filename in files:
                        if filename.endswith('/'):
                            continue
                        
                        file_url = suppl_url + filename
                        dest_path = output_dir / filename
                        
                        try:
                            await self.download_file(file_url, dest_path)
                            downloaded.append({
                                "filename": filename,
                                "path": str(dest_path),
                                "size_mb": round(dest_path.stat().st_size / (1024*1024), 2)
                            })
                        except Exception as e:
                            errors.append(f"{filename}: {str(e)}")
                else:
                    errors.append(f"Could not list supplementary files: HTTP {response.status_code}")
        except Exception as e:
            errors.append(f"Error accessing supplementary files: {str(e)}")
        
        return {
            "accession": gsm_id,
            "output_dir": str(output_dir),
            "downloaded": downloaded,
            "errors": errors,
            "total_downloaded": len(downloaded)
        }
    
    def _parse_directory_listing(self, html: str) -> List[str]:
        """Parse HTML directory listing for file names."""
        # Simple regex to extract href values
        files = []
        for match in re.finditer(r'href=["\']([^"\']+)["\']', html):
            filename = match.group(1)
            if filename not in ['../', './']:
                files.append(filename)
        return files
    
    def get_download_status(self, accession: str, db_type: str = "gse") -> Dict[str, Any]:
        """Check download status of a GEO dataset.
        
        Args:
            accession: GEO accession ID
            db_type: Database type (gse, gsm, gpl, gds)
            
        Returns:
            Status dictionary
        """
        dataset_path = self.download_dir / db_type / accession
        
        if not dataset_path.exists():
            return {
                "accession": accession,
                "db_type": db_type,
                "downloaded": False,
                "path": str(dataset_path)
            }
        
        files = []
        total_size = 0
        for f in dataset_path.rglob("*"):
            if f.is_file():
                size = f.stat().st_size
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "size_mb": round(size / (1024*1024), 2)
                })
                total_size += size
        
        return {
            "accession": accession,
            "db_type": db_type,
            "downloaded": True,
            "path": str(dataset_path),
            "files": files,
            "total_size_mb": round(total_size / (1024*1024), 2),
            "file_count": len(files)
        }
    
    def list_downloaded_datasets(self, db_type: Optional[str] = None) -> Dict[str, Any]:
        """List all downloaded datasets.
        
        Args:
            db_type: Optional filter by database type
            
        Returns:
            List of downloaded datasets
        """
        datasets = []
        
        if db_type:
            db_path = self.download_dir / db_type
            if db_path.exists():
                for dataset_dir in db_path.iterdir():
                    if dataset_dir.is_dir():
                        total_size = sum(
                            f.stat().st_size for f in dataset_dir.rglob("*") if f.is_file()
                        )
                        datasets.append({
                            "accession": dataset_dir.name,
                            "db_type": db_type,
                            "path": str(dataset_dir),
                            "size_mb": round(total_size / (1024*1024), 2)
                        })
        else:
            for db_dir in self.download_dir.iterdir():
                if db_dir.is_dir():
                    for dataset_dir in db_dir.iterdir():
                        if dataset_dir.is_dir():
                            total_size = sum(
                                f.stat().st_size for f in dataset_dir.rglob("*") if f.is_file()
                            )
                            datasets.append({
                                "accession": dataset_dir.name,
                                "db_type": db_dir.name,
                                "path": str(dataset_dir),
                                "size_mb": round(total_size / (1024*1024), 2)
                            })
        
        return {
            "datasets": datasets,
            "count": len(datasets)
        }
    
    def cleanup_downloads(
        self, 
        accession: Optional[str] = None, 
        db_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Clean up downloaded files.
        
        Args:
            accession: Optional specific accession to remove
            db_type: Optional database type filter
            
        Returns:
            Cleanup results
        """
        removed = []
        
        if accession and db_type:
            # Remove specific dataset
            dataset_path = self.download_dir / db_type / accession
            if dataset_path.exists():
                shutil.rmtree(dataset_path)
                removed.append(str(dataset_path))
        elif db_type:
            # Remove all datasets of a specific type
            db_path = self.download_dir / db_type
            if db_path.exists():
                for dataset_dir in db_path.iterdir():
                    if dataset_dir.is_dir():
                        shutil.rmtree(dataset_dir)
                        removed.append(str(dataset_dir))
        elif accession:
            # Remove all matching accessions across types
            for db_dir in self.download_dir.iterdir():
                if db_dir.is_dir():
                    dataset_path = db_dir / accession
                    if dataset_path.exists():
                        shutil.rmtree(dataset_path)
                        removed.append(str(dataset_path))
        else:
            # Remove all downloads
            for db_dir in self.download_dir.iterdir():
                if db_dir.is_dir():
                    shutil.rmtree(db_dir)
                    removed.append(str(db_dir))
        
        return {
            "removed": removed,
            "count": len(removed)
        }
