"""SRA (Sequence Read Archive) handling functionality.

This module provides capabilities to:
1. Query SRA Run information from GEO Series (map GSM to SRR accessions)
2. Get SRA accession lists for datasets
3. Generate download commands for SRA data
4. Optionally download FASTQ files using sra-toolkit
"""

import asyncio
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import httpx

from .config import get_config


class SRAError(Exception):
    """Exception raised for SRA-related errors."""
    pass


class SRAHandler:
    """Handler for SRA data queries and downloads."""
    
    # SRA endpoints
    SRA_TRACE_URL = "https://trace.ncbi.nlm.nih.gov/Traces/sra"
    SRA_EUTILS_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    SRA_FETCH_URL = "https://sra-downloadb.be-md.ncbi.nlm.nih.gov/sos2/sra-pub-run-11"
    
    def __init__(self):
        self.config = get_config()
        self.email = self.config["email"]
        self.api_key = self.config.get("api_key")
        self.sra_toolkit_path = self.config.get("sra_toolkit_path")
        self.download_dir = Path(self.config["download_dir"]).resolve() / "sra"
        self.download_dir.mkdir(parents=True, exist_ok=True)
    
    def _build_params(self, extra_params: Dict[str, Any]) -> Dict[str, str]:
        """Build request parameters with authentication."""
        params = {"email": self.email, **extra_params}
        if self.api_key:
            params["api_key"] = self.api_key
        return params
    
    async def _fetch_geo_soft(self, gse_id: str) -> str:
        """Fetch GEO Series SOFT file to extract SRA information.
        
        Args:
            gse_id: GSE accession ID
            
        Returns:
            SOFT file content as string
        """
        range_dir = f"{gse_id[:-3]}nnn"
        url = f"https://ftp.ncbi.nlm.nih.gov/geo/series/{range_dir}/{gse_id}/soft/{gse_id}_family.soft.gz"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=60.0)
            
            if response.status_code == 404:
                # Try without _family suffix
                url = f"https://ftp.ncbi.nlm.nih.gov/geo/series/{range_dir}/{gse_id}/soft/{gse_id}.soft.gz"
                response = await client.get(url, timeout=60.0)
            
            response.raise_for_status()
            
            # Decompress gzip content
            import gzip
            content = gzip.decompress(response.content)
            return content.decode('utf-8', errors='replace')
    
    def _parse_sra_accessions_from_soft(self, soft_content: str) -> Dict[str, List[str]]:
        """Parse SRA accession numbers from SOFT file content.
        
        Args:
            soft_content: SOFT file content
            
        Returns:
            Dictionary mapping GSM IDs to lists of SRA accessions (SRX experiments)
        """
        gsm_to_sra = {}
        current_gsm = None
        
        for line in soft_content.split('\n'):
            line = line.strip()
            
            # Track current sample
            if line.startswith('^SAMPLE = '):
                current_gsm = line.split('=')[1].strip()
                gsm_to_sra[current_gsm] = []
            
            # Look for SRA relation links (contain SRX experiment IDs)
            elif current_gsm and line.startswith('!Sample_relation = SRA:'):
                # Extract SRX ID from URL like "https://www.ncbi.nlm.nih.gov/sra?term=SRX25362135"
                srx_pattern = r'([SED]RX\d+)'
                matches = re.findall(srx_pattern, line)
                gsm_to_sra[current_gsm].extend(matches)
        
        # Remove empty entries
        gsm_to_sra = {k: v for k, v in gsm_to_sra.items() if v}
        
        return gsm_to_sra
    
    async def _get_srr_from_srx(self, srx_id: str) -> List[str]:
        """Get SRA Run (SRR) IDs from Experiment (SRX) ID.
        
        Args:
            srx_id: SRX accession (e.g., 'SRX25362135')
            
        Returns:
            List of SRR accessions
        """
        srr_list = []
        
        try:
            async with httpx.AsyncClient() as client:
                # Use E-Utilities to search for runs linked to this experiment
                search_params = self._build_params({
                    "db": "sra",
                    "term": f"{srx_id}[Experiment]",
                    "retmode": "json",
                    "retmax": 100
                })
                
                response = await client.get(
                    f"{self.SRA_EUTILS_URL}/esearch.fcgi",
                    params=search_params,
                    timeout=30.0
                )
                response.raise_for_status()
                
                search_data = response.json()
                sra_ids = search_data.get('esearchresult', {}).get('idlist', [])
                
                if not sra_ids:
                    return srr_list
                
                # Get summary for each SRA entry to find SRR IDs
                for sra_id in sra_ids:
                    summary_params = self._build_params({
                        "db": "sra",
                        "id": sra_id,
                        "retmode": "json"
                    })
                    
                    response = await client.get(
                        f"{self.SRA_EUTILS_URL}/esummary.fcgi",
                        params=summary_params,
                        timeout=30.0
                    )
                    response.raise_for_status()
                    
                    summary_data = response.json()
                    
                    # Parse the result to find SRR IDs
                    result = summary_data.get('result', {})
                    for uid in result.get('uids', []):
                        item = result.get(uid, {})
                        # Look for run accessions in the summary
                        runs = item.get('runs', '')
                        if runs:
                            # Parse SRR from runs field
                            srr_matches = re.findall(r'([SED]RR\d+)', runs)
                            srr_list.extend(srr_matches)
                        
                        # Also check other fields
                        for key in ['accession', 'runlist', 'experiment']:
                            val = item.get(key, '')
                            if val:
                                srr_matches = re.findall(r'([SED]RR\d+)', str(val))
                                srr_list.extend(srr_matches)
                
        except Exception as e:
            # Don't fail if we can't get SRR info
            pass
        
        return list(set(srr_list))  # Remove duplicates
    
    async def query_sra_from_geo(self, gse_id: str) -> Dict[str, Any]:
        """Query SRA Run information from a GEO Series.
        
        This method extracts the mapping between GSM samples and SRR runs
        from the GEO Series SOFT file.
        
        Args:
            gse_id: GSE accession ID (e.g., 'GSE12345')
            
        Returns:
            Dictionary with SRA run information
            
        Example:
            {
                "gse_id": "GSE12345",
                "total_samples": 10,
                "samples_with_sra": 8,
                "sra_runs": [
                    {
                        "gsm_id": "GSM123456",
                        "sra_accessions": ["SRR1234567", "SRR1234568"]
                    }
                ]
            }
        """
        if not gse_id.upper().startswith("GSE"):
            raise SRAError(f"Invalid GSE ID: {gse_id}")
        
        try:
            # Fetch and parse SOFT file
            soft_content = await self._fetch_geo_soft(gse_id)
            gsm_to_sra = self._parse_sra_accessions_from_soft(soft_content)
            
            # Convert SRX (Experiment) IDs to SRR (Run) IDs
            gsm_to_srr = {}
            for gsm_id, srx_list in gsm_to_sra.items():
                srr_list = []
                for srx_id in srx_list:
                    srrs = await self._get_srr_from_srx(srx_id)
                    srr_list.extend(srrs)
                if srr_list:
                    gsm_to_srr[gsm_id] = list(set(srr_list))  # Remove duplicates
            
            # Also try to get from E-Utilities link
            additional_sra = await self._get_sra_from_eutils(gse_id)
            
            # Merge results
            for gsm_id, sra_list in additional_sra.items():
                if gsm_id in gsm_to_srr:
                    # Merge without duplicates
                    existing = set(gsm_to_srr[gsm_id])
                    for sra in sra_list:
                        if sra not in existing:
                            gsm_to_srr[gsm_id].append(sra)
                else:
                    gsm_to_srr[gsm_id] = sra_list
            
            # Build response
            samples_with_sra = [
                {
                    "gsm_id": gsm_id,
                    "sra_accessions": sra_list
                }
                for gsm_id, sra_list in gsm_to_srr.items()
            ]
            
            # Get all unique SRR accessions
            all_srr = set()
            for sra_list in gsm_to_srr.values():
                all_srr.update(sra_list)
            
            return {
                "gse_id": gse_id.upper(),
                "total_samples": len(samples_with_sra),
                "samples_with_sra": len(samples_with_sra),
                "total_sra_runs": len(all_srr),
                "all_sra_accessions": sorted(list(all_srr)),
                "samples": samples_with_sra
            }
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SRAError(f"GEO Series {gse_id} not found or SOFT file unavailable")
            raise SRAError(f"HTTP error querying SRA info: {e.response.status_code}")
        except Exception as e:
            raise SRAError(f"Error querying SRA information: {str(e)}")
    
    async def _get_sra_from_eutils(self, gse_id: str) -> Dict[str, List[str]]:
        """Get SRA accessions using E-Utilities.
        
        Args:
            gse_id: GSE accession ID
            
        Returns:
            Dictionary mapping GSM IDs to SRA accessions
        """
        result = {}
        
        try:
            # Search for samples in this series
            async with httpx.AsyncClient() as client:
                # First, get series UID
                search_params = self._build_params({
                    "db": "gds",
                    "term": f"{gse_id}[ACCN]",
                    "retmode": "json"
                })
                
                response = await client.get(
                    f"{self.SRA_EUTILS_URL}/esearch.fcgi",
                    params=search_params,
                    timeout=30.0
                )
                response.raise_for_status()
                
                search_data = response.json()
                gds_ids = search_data.get('esearchresult', {}).get('idlist', [])
                
                if not gds_ids:
                    return result
                
                # Fetch summary to get sample information
                summary_params = self._build_params({
                    "db": "gds",
                    "id": gds_ids[0],
                    "retmode": "json"
                })
                
                response = await client.get(
                    f"{self.SRA_EUTILS_URL}/esummary.fcgi",
                    params=summary_params,
                    timeout=30.0
                )
                response.raise_for_status()
                
                # Note: E-utilities doesn't always have SRA links
                # This is a fallback method
                
        except Exception:
            # Don't fail if eutils doesn't return data
            pass
        
        return result
    
    async def estimate_sra_size(self, sra_ids: List[str]) -> Dict[str, Any]:
        """Estimate the size of SRA files before downloading.
        
        This is a "dry-run" mode that queries the SRA database to estimate
        download sizes without actually downloading any data.
        
        Args:
            sra_ids: List of SRA accession IDs
            
        Returns:
            Dictionary with size estimates and warnings
        """
        if not sra_ids:
            raise SRAError("No SRA IDs provided")
        
        results = []
        total_size_bytes = 0
        
        try:
            async with httpx.AsyncClient() as client:
                for sra_id in sra_ids:
                    sra_id = sra_id.upper()
                    
                    # Use EBI ENA API to get file size (more reliable than NCBI for size info)
                    ena_url = f"https://www.ebi.ac.uk/ena/portal/api/filereport?accession={sra_id}&result=read_run&fields=run_accession,fastq_bytes,sra_bytes,read_count,base_count"
                    
                    try:
                        response = await client.get(ena_url, timeout=30.0)
                        response.raise_for_status()
                        
                        lines = response.text.strip().split('\n')
                        if len(lines) >= 2:
                            # Parse TSV response
                            headers = lines[0].split('\t')
                            values = lines[1].split('\t')
                            
                            data = dict(zip(headers, values))
                            
                            # Get SRA size if available, otherwise estimate from FASTQ
                            sra_bytes = data.get('sra_bytes', '')
                            fastq_bytes = data.get('fastq_bytes', '')
                            read_count = data.get('read_count', '0')
                            base_count = data.get('base_count', '0')
                            
                            # Calculate sizes
                            sra_size_mb = 0
                            if sra_bytes and sra_bytes.isdigit():
                                sra_size_mb = int(sra_bytes) / (1024 * 1024)
                            elif fastq_bytes:
                                # Estimate SRA size as ~40% of FASTQ (compressed)
                                fastq_sizes = fastq_bytes.split(';')
                                total_fastq = sum(int(x) for x in fastq_sizes if x.isdigit())
                                sra_size_mb = (total_fastq * 0.4) / (1024 * 1024)
                            
                            # Estimate FASTQ size (SRA * 2.5 for decompressed)
                            estimated_fastq_mb = sra_size_mb * 2.5
                            
                            total_size_bytes += sra_size_mb * 1024 * 1024
                            
                            results.append({
                                "sra_id": sra_id,
                                "sra_size_mb": round(sra_size_mb, 2),
                                "estimated_fastq_size_mb": round(estimated_fastq_mb, 2),
                                "read_count": int(read_count) if read_count.isdigit() else 0,
                                "base_count": int(base_count) if base_count.isdigit() else 0,
                                "warning": self._get_size_warning(sra_size_mb)
                            })
                        else:
                            results.append({
                                "sra_id": sra_id,
                                "sra_size_mb": "unknown",
                                "estimated_fastq_size_mb": "unknown",
                                "warning": "Could not retrieve size information from ENA"
                            })
                            
                    except Exception as e:
                        results.append({
                            "sra_id": sra_id,
                            "sra_size_mb": "unknown",
                            "estimated_fastq_size_mb": "unknown",
                            "warning": f"Error querying ENA: {str(e)}"
                        })
        
        except Exception as e:
            raise SRAError(f"Error estimating sizes: {str(e)}")
        
        # Calculate total
        total_mb = total_size_bytes / (1024 * 1024)
        total_gb = total_mb / 1024
        
        return {
            "dry_run": True,
            "sra_count": len(sra_ids),
            "individual_estimates": results,
            "total_sra_size_mb": round(total_mb, 2),
            "total_sra_size_gb": round(total_gb, 2),
            "estimated_total_fastq_size_gb": round(total_gb * 2.5, 2),
            "safety_warnings": self._get_safety_warnings(total_mb)
        }
    
    def _get_size_warning(self, size_mb: float) -> str:
        """Get warning message based on file size."""
        if size_mb == 0:
            return "Size unknown"
        elif size_mb < 100:
            return "Small file (< 100 MB)"
        elif size_mb < 1024:
            return "Medium file (100 MB - 1 GB)"
        elif size_mb < 5120:  # 5 GB
            return "⚠️  LARGE FILE (1-5 GB) - Ensure sufficient disk space"
        else:
            return "🚨 VERY LARGE FILE (> 5 GB) - Requires explicit confirmation"
    
    def _get_safety_warnings(self, total_mb: float) -> List[str]:
        """Get safety warnings for the total download size."""
        warnings = []
        
        if total_mb > 1024:  # > 1 GB
            warnings.append("Total download exceeds 1 GB. Ensure you have sufficient disk space.")
        if total_mb > 5120:  # > 5 GB
            warnings.append("Total download exceeds 5 GB. This will take significant time and space.")
        if total_mb > 10240:  # > 10 GB
            warnings.append("🚨 WARNING: Total download exceeds 10 GB! Consider downloading individual files.")
        
        return warnings
    
    async def get_sra_metadata(self, sra_id: str) -> Dict[str, Any]:
        """Get metadata for an SRA run.
        
        Args:
            sra_id: SRA accession (e.g., 'SRR1234567')
            
        Returns:
            SRA run metadata
        """
        if not re.match(r'^[SED]RR\d+$', sra_id, re.IGNORECASE):
            raise SRAError(f"Invalid SRA ID: {sra_id}")
        
        sra_id = sra_id.upper()
        
        try:
            # Use E-Utilities to get SRA metadata
            async with httpx.AsyncClient() as client:
                # Search in SRA database
                search_params = self._build_params({
                    "db": "sra",
                    "term": sra_id,
                    "retmode": "json"
                })
                
                response = await client.get(
                    f"{self.SRA_EUTILS_URL}/esearch.fcgi",
                    params=search_params,
                    timeout=30.0
                )
                response.raise_for_status()
                
                search_data = response.json()
                sra_ids = search_data.get('esearchresult', {}).get('idlist', [])
                
                if not sra_ids:
                    return {
                        "sra_id": sra_id,
                        "found": False,
                        "error": "SRA accession not found in database"
                    }
                
                # Get summary
                summary_params = self._build_params({
                    "db": "sra",
                    "id": sra_ids[0],
                    "retmode": "json"
                })
                
                response = await client.get(
                    f"{self.SRA_EUTILS_URL}/esummary.fcgi",
                    params=summary_params,
                    timeout=30.0
                )
                response.raise_for_status()
                
                summary_data = response.json()
                
                return {
                    "sra_id": sra_id,
                    "found": True,
                    "metadata": summary_data
                }
                
        except Exception as e:
            raise SRAError(f"Error getting SRA metadata: {str(e)}")
    
    def get_sra_download_url(self, sra_id: str) -> str:
        """Get direct download URL for an SRA run.
        
        Args:
            sra_id: SRA accession (e.g., 'SRR1234567')
            
        Returns:
            Direct download URL
        """
        sra_id = sra_id.upper()
        
        # Construct SRA download URL
        # Format: https://sra-downloadb.be-md.ncbi.nlm.nih.gov/sos2/sra-pub-run-11/{SRRxxxxxxx}/{SRRxxxxxxx}.1
        base_url = "https://sra-downloadb.be-md.ncbi.nlm.nih.gov/sos2/sra-pub-run-11"
        return f"{base_url}/{sra_id}/{sra_id}.1"
    
    def generate_download_commands(
        self, 
        sra_ids: List[str],
        method: str = "prefetch",
        output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate commands to download SRA data.
        
        Args:
            sra_ids: List of SRA accessions
            method: Download method ('prefetch', 'wget', 'curl', or 'aspera')
            output_dir: Optional output directory
            
        Returns:
            Dictionary with download commands and instructions
        """
        if not sra_ids:
            raise SRAError("No SRA IDs provided")
        
        output_dir = output_dir or str(self.download_dir)
        commands = []
        
        if method == "prefetch":
            # sra-toolkit prefetch command
            toolkit_path = self.sra_toolkit_path or ""
            prefetch = f"{toolkit_path}/prefetch" if toolkit_path else "prefetch"
            
            for sra_id in sra_ids:
                cmd = f"{prefetch} -O {output_dir} {sra_id}"
                commands.append({
                    "sra_id": sra_id,
                    "command": cmd,
                    "description": f"Download {sra_id} using sra-toolkit prefetch"
                })
        
        elif method == "fasterq-dump":
            # Directly download and convert to FASTQ
            toolkit_path = self.sra_toolkit_path or ""
            fasterq_dump = f"{toolkit_path}/fasterq-dump" if toolkit_path else "fasterq-dump"
            
            for sra_id in sra_ids:
                cmd = f"{fasterq_dump} --outdir {output_dir} {sra_id}"
                commands.append({
                    "sra_id": sra_id,
                    "command": cmd,
                    "description": f"Download and convert {sra_id} to FASTQ"
                })
        
        elif method == "wget":
            # Direct HTTP download
            for sra_id in sra_ids:
                url = self.get_sra_download_url(sra_id)
                cmd = f"wget -P {output_dir} {url}"
                commands.append({
                    "sra_id": sra_id,
                    "command": cmd,
                    "description": f"Download {sra_id} using wget"
                })
        
        elif method == "curl":
            # Direct HTTP download with curl
            for sra_id in sra_ids:
                url = self.get_sra_download_url(sra_id)
                output_file = f"{output_dir}/{sra_id}.sra"
                cmd = f"curl -o {output_file} {url}"
                commands.append({
                    "sra_id": sra_id,
                    "command": cmd,
                    "description": f"Download {sra_id} using curl"
                })
        
        elif method == "aspera":
            # Aspera high-speed download
            # Requires aspera-cli to be installed
            for sra_id in sra_ids:
                aspera_url = f"anonftp@ftp.ncbi.nlm.nih.gov:/sra/sra-instant/reads/ByRun/sra/{sra_id[:3]}/{sra_id[:6]}/{sra_id}/{sra_id}.sra"
                cmd = f"ascp -QT -l 300m -P33001 -i $HOME/.aspera/connect/etc/asperaweb_id_dsa.openssh {aspera_url} {output_dir}"
                commands.append({
                    "sra_id": sra_id,
                    "command": cmd,
                    "description": f"Download {sra_id} using Aspera (high-speed)"
                })
        
        else:
            raise SRAError(f"Unknown download method: {method}")
        
        return {
            "sra_ids": sra_ids,
            "method": method,
            "output_dir": output_dir,
            "commands": commands,
            "notes": self._get_method_notes(method)
        }
    
    def _get_method_notes(self, method: str) -> str:
        """Get notes for a download method."""
        notes = {
            "prefetch": (
                "Requires sra-toolkit (https://github.com/ncbi/sra-tools). "
                "Downloads SRA files which can then be converted to FASTQ using fasterq-dump."
            ),
            "fasterq-dump": (
                "Requires sra-toolkit. Downloads and converts to FASTQ in one step. "
                "May take longer but produces immediately usable files."
            ),
            "wget": (
                "Direct HTTP download. Works without sra-toolkit but downloads SRA format files "
                "which need to be converted using fasterq-dump."
            ),
            "curl": (
                "Direct HTTP download using curl. Similar to wget but more portable."
            ),
            "aspera": (
                "High-speed download using Aspera protocol. Requires aspera-cli. "
                "Fastest method for large files."
            )
        }
        return notes.get(method, "")
    
    async def download_sra(
        self, 
        sra_id: str,
        convert_to_fastq: bool = False,
        output_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Download an SRA file.
        
        Note: This method downloads SRA files directly. For production use,
        it's recommended to use sra-toolkit prefetch/fasterq-dump instead.
        
        Args:
            sra_id: SRA accession
            convert_to_fastq: Whether to convert to FASTQ (requires sra-toolkit)
            output_dir: Optional output directory
            
        Returns:
            Download results
        """
        sra_id = sra_id.upper()
        output_dir = output_dir or self.download_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        url = self.get_sra_download_url(sra_id)
        sra_file = output_dir / f"{sra_id}.sra"
        
        try:
            # Download the SRA file
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", url, timeout=300.0) as response:
                    response.raise_for_status()
                    
                    with open(sra_file, 'wb') as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
            
            result = {
                "sra_id": sra_id,
                "sra_file": str(sra_file),
                "size_mb": round(sra_file.stat().st_size / (1024*1024), 2),
                "converted_to_fastq": False
            }
            
            # Convert to FASTQ if requested
            if convert_to_fastq:
                fastq_result = await self._convert_to_fastq(sra_file, output_dir)
                result["converted_to_fastq"] = True
                result["fastq_files"] = fastq_result
            
            return result
            
        except Exception as e:
            # Clean up partial download
            if sra_file.exists():
                sra_file.unlink()
            raise SRAError(f"Download failed: {str(e)}")
    
    async def _convert_to_fastq(
        self, 
        sra_file: Path, 
        output_dir: Path
    ) -> List[str]:
        """Convert SRA file to FASTQ using fasterq-dump.
        
        Args:
            sra_file: Path to SRA file
            output_dir: Output directory for FASTQ files
            
        Returns:
            List of generated FASTQ files
        """
        toolkit_path = self.sra_toolkit_path or ""
        fasterq_dump = f"{toolkit_path}/fasterq-dump" if toolkit_path else "fasterq-dump"
        
        # Check if fasterq-dump is available
        try:
            result = subprocess.run(
                [fasterq_dump, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise SRAError("fasterq-dump not found. Please install sra-toolkit.")
        except FileNotFoundError:
            raise SRAError(
                "fasterq-dump not found. Please install sra-toolkit: "
                "https://github.com/ncbi/sra-tools"
            )
        
        # Run fasterq-dump
        cmd = [
            fasterq_dump,
            "--outdir", str(output_dir),
            "--threads", "4",
            str(sra_file)
        ]
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        )
        
        if result.returncode != 0:
            raise SRAError(f"fasterq-dump failed: {result.stderr}")
        
        # Find generated FASTQ files
        sra_id = sra_file.stem
        fastq_files = []
        for pattern in [f"{sra_id}*.fastq", f"{sra_id}*.fastq.gz"]:
            fastq_files.extend(output_dir.glob(pattern))
        
        return [str(f) for f in fastq_files]
    
    async def download_and_convert(
        self,
        sra_id: str,
        output_dir: Optional[Path] = None,
        split_3: bool = True,
        check_refseq: bool = True,
        dry_run: bool = False,
        confirm_large: bool = False
    ) -> Dict[str, Any]:
        """Download SRA data using prefetch and convert to FASTQ using fastq-dump.
        
        SAFETY FEATURES (as per maintainer recommendations):
        - Dry-run mode: Estimate sizes before downloading
        - Size warnings: Alerts for large files (>1GB, >5GB)
        - Explicit confirmation: Required for very large downloads
        - Explicit output directory: Must be provided for large files
        
        This is the recommended workflow for downloading and converting SRA data:
        1. Uses prefetch to download SRA file (handles large files better)
        2. Uses fastq-dump --split-3 to convert to FASTQ (handles paired-end properly)
        
        Args:
            sra_id: SRA accession ID (e.g., 'SRR1234567')
            output_dir: Optional output directory (default: download_dir/sra_id)
            split_3: Use --split-3 for 3-way splitting (recommended for mate-pairs)
            check_refseq: Whether to check/download reference sequences
            dry_run: If True, only estimate sizes without downloading (default: False)
            confirm_large: Must be True to download files >5GB (safety check)
            
        Returns:
            Dictionary with download and conversion results, or dry-run estimates
            
        Raises:
            SRAError: If output_dir not provided for large files, or if confirm_large=False for >5GB files
        """
        sra_id = sra_id.upper()
        
        # SAFETY CHECK 1: Estimate size before downloading
        size_estimate = await self.estimate_sra_size([sra_id])
        total_mb = size_estimate.get("total_sra_size_mb", 0)
        
        # SAFETY CHECK 2: Dry-run mode - return estimates without downloading
        if dry_run:
            return {
                "mode": "dry_run",
                "sra_id": sra_id,
                "size_estimate": size_estimate,
                "note": "To proceed with download, call with dry_run=False"
            }
        
        # SAFETY CHECK 3: Explicit output directory required for large files
        if total_mb > 1024 and output_dir is None:  # > 1GB
            raise SRAError(
                f"SAFETY CHECK: File size is ~{total_mb/1024:.1f} GB. "
                f"Large downloads require an explicit output directory. "
                f"Please provide output_dir parameter. "
                f"Tip: Run with dry_run=True first to see size estimates."
            )
        
        # SAFETY CHECK 4: Confirmation required for very large files
        if total_mb > 5120 and not confirm_large:  # > 5GB
            raise SRAError(
                f"SAFETY CHECK: File size is ~{total_mb/1024:.1f} GB (>5GB). "
                f"This is a VERY LARGE download that will consume significant "
                f"disk space and time. To proceed, set confirm_large=True. "
                f"Tip: Run with dry_run=True first to see detailed estimates."
            )
        
        output_dir = output_dir or (self.download_dir / sra_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Check for sra-toolkit
        toolkit_check = self.check_sra_toolkit()
        if not toolkit_check["all_available"]:
            raise SRAError(
                "sra-toolkit not found. Please install from: "
                "https://github.com/ncbi/sra-tools"
            )
        
        toolkit_path = self.sra_toolkit_path or ""
        prefetch = f"{toolkit_path}/prefetch" if toolkit_path else "prefetch"
        fastq_dump = f"{toolkit_path}/fastq-dump" if toolkit_path else "fastq-dump"
        
        result = {
            "sra_id": sra_id,
            "output_dir": str(output_dir),
            "size_estimate_mb": total_mb,
            "safety_warnings": size_estimate.get("safety_warnings", []),
            "steps": []
        }
        
        try:
            # Step 1: Download using prefetch
            import logging
            logger = logging.getLogger(__name__)
            
            cmd = [prefetch, "--progress", "--output-directory", str(output_dir)]
            
            # Handle refseq checking
            if not check_refseq:
                cmd.extend(["--check-rs", "no"])
            
            cmd.append(sra_id)
            
            loop = asyncio.get_event_loop()
            prefetch_result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1 hour timeout for large files
                )
            )
            
            if prefetch_result.returncode != 0:
                raise SRAError(f"prefetch failed: {prefetch_result.stderr}")
            
            # Find the downloaded SRA file
            sra_file = output_dir / sra_id / f"{sra_id}.sra"
            if not sra_file.exists():
                # Try alternative locations
                alt_paths = [
                    output_dir / f"{sra_id}.sra",
                    self.download_dir / sra_id / f"{sra_id}.sra",
                    Path(f"{sra_id}/{sra_id}.sra"),
                ]
                for alt_path in alt_paths:
                    if alt_path.exists():
                        sra_file = alt_path
                        break
            
            if not sra_file.exists():
                raise SRAError(f"SRA file not found after download: {sra_file}")
            
            sra_size_mb = round(sra_file.stat().st_size / (1024*1024), 2)
            
            result["steps"].append({
                "step": "download",
                "status": "success",
                "sra_file": str(sra_file),
                "sra_size_mb": sra_size_mb
            })
            
            # Step 2: Convert to FASTQ using fastq-dump
            print(f"Step 2: Converting {sra_id} to FASTQ using fastq-dump...")
            
            cmd = [fastq_dump, "--outdir", str(output_dir)]
            
            if split_3:
                cmd.append("--split-3")
            else:
                cmd.append("--split-files")
            
            cmd.append(str(sra_file))
            
            fastq_result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1 hour timeout
                )
            )
            
            if fastq_result.returncode != 0:
                raise SRAError(f"fastq-dump failed: {fastq_result.stderr}")
            
            # Find generated FASTQ files
            fastq_files = []
            for pattern in [f"{sra_id}*.fastq", f"{sra_id}*.fastq.gz"]:
                fastq_files.extend(output_dir.glob(pattern))
            
            # Also check in sra_id subdirectory
            if (output_dir / sra_id).exists():
                for pattern in [f"{sra_id}*.fastq", f"{sra_id}*.fastq.gz"]:
                    fastq_files.extend((output_dir / sra_id).glob(pattern))
            
            fastq_info = []
            total_fastq_size_mb = 0
            for f in fastq_files:
                size_mb = round(f.stat().st_size / (1024*1024), 2)
                total_fastq_size_mb += size_mb
                
                # Count reads (each read = 4 lines)
                line_count = 0
                try:
                    with open(f, 'r') as fp:
                        for _ in fp:
                            line_count += 1
                            if line_count >= 4:
                                break
                    # Get total lines
                    result_count = subprocess.run(
                        ["wc", "-l", str(f)],
                        capture_output=True,
                        text=True
                    )
                    total_lines = int(result_count.stdout.split()[0])
                    read_count = total_lines // 4
                except:
                    read_count = "unknown"
                
                fastq_info.append({
                    "file": str(f.name),
                    "path": str(f),
                    "size_mb": size_mb,
                    "reads": read_count
                })
            
            result["steps"].append({
                "step": "convert",
                "status": "success",
                "fastq_files": fastq_info,
                "total_fastq_size_mb": total_fastq_size_mb
            })
            
            result["status"] = "success"
            result["total_size_mb"] = sra_size_mb + total_fastq_size_mb
            
            return result
            
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            raise SRAError(f"Download and convert failed: {str(e)}")
    
    def check_sra_toolkit(self) -> Dict[str, Any]:
        """Check if sra-toolkit is installed and available.
        
        Returns:
            Status information about sra-toolkit
        """
        toolkit_path = self.sra_toolkit_path or ""
        tools = ["prefetch", "fastq-dump", "fasterq-dump", "vdb-validate"]
        
        results = {}
        all_found = True
        
        for tool in tools:
            cmd = f"{toolkit_path}/{tool}" if toolkit_path else tool
            try:
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                results[tool] = {
                    "available": result.returncode == 0,
                    "version": result.stdout.strip() if result.returncode == 0 else None,
                    "path": cmd
                }
                if result.returncode != 0:
                    all_found = False
            except FileNotFoundError:
                results[tool] = {"available": False, "path": cmd}
                all_found = False
            except Exception as e:
                results[tool] = {"available": False, "error": str(e)}
                all_found = False
        
        return {
            "all_available": all_found,
            "toolkit_path": toolkit_path or "System PATH",
            "tools": results,
            "installation_url": "https://github.com/ncbi/sra-tools/wiki/02.-Installing-SRA-Toolkit"
        }
