#!/usr/bin/env python3
"""
GEO MCP Server with SRA Support

An enhanced Model Context Protocol (MCP) server for accessing 
GEO (Gene Expression Omnibus) data through NCBI E-Utils API,
with additional support for SRA (Sequence Read Archive) raw data queries.

Usage:
    python server.py                    # Run MCP stdio server
    python server.py --http             # Run HTTP server
    python server.py --http --port 8080 # Run HTTP server on custom port
    python server.py --init             # Initialize configuration
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, List
from enum import Enum

from pydantic import BaseModel, Field, field_validator, ConfigDict
from mcp.server.fastmcp import FastMCP

# Import our modules
from geomcp_sra.config import load_config, validate_config, create_config_template, get_config
from geomcp_sra.geo_search import GEOSearchClient, GEOSearchError
from geomcp_sra.geo_download import GEODownloadClient, GEODownloadError
from geomcp_sra.sra_handler import SRAHandler, SRAError


# Initialize MCP server
mcp = FastMCP("geo_mcp")


# ============================================================================
# Enums and Response Formats
# ============================================================================

class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"


class DownloadMethod(str, Enum):
    """SRA download methods."""
    PREFETCH = "prefetch"
    FASTERQ_DUMP = "fasterq-dump"
    WGET = "wget"
    CURL = "curl"
    ASPERA = "aspera"


# ============================================================================
# Pydantic Models for Input Validation
# ============================================================================

class SearchInput(BaseModel):
    """Base input for search operations."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    term: str = Field(
        ..., 
        description="Search term (e.g., 'breast cancer', 'GSE12345', 'RNA-seq')",
        min_length=1,
        max_length=500
    )
    retmax: int = Field(
        default=20, 
        description="Maximum number of results to return",
        ge=1,
        le=1000
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.JSON,
        description="Output format: 'json' for structured data or 'markdown' for readable text"
    )


class SearchWithTypesInput(SearchInput):
    """Input for search with record type filtering."""
    record_types: Optional[List[str]] = Field(
        default=None,
        description="Filter for specific record types: GSE, GSM, GPL, GDS"
    )


class GeoIdInput(BaseModel):
    """Input for GEO ID operations."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    geo_id: str = Field(
        ...,
        description="GEO accession ID (e.g., GSE12345, GSM789, GPL456, GDS123)",
        pattern=r'^(GSE|GSM|GPL|GDS)\d+$'
    )


class DownloadInput(GeoIdInput):
    """Input for download operations."""
    db_type: str = Field(
        default="gse",
        description="Database type: gse, gsm, gpl, or gds"
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Optional custom output directory"
    )
    file_types: Optional[List[str]] = Field(
        default=None,
        description="File types to download (for series: soft, matrix, miniml, supplementary)"
    )


class SRASearchInput(BaseModel):
    """Input for SRA search operations."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    gse_id: str = Field(
        ...,
        description="GEO Series accession ID (e.g., GSE12345)",
        pattern=r'^GSE\d+$'
    )


class SRADownloadInput(BaseModel):
    """Input for SRA download command generation."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    sra_ids: List[str] = Field(
        ...,
        description="List of SRA accession IDs (e.g., ['SRR1234567', 'SRR1234568'])",
        min_length=1
    )
    method: DownloadMethod = Field(
        default=DownloadMethod.PREFETCH,
        description="Download method: prefetch, fasterq-dump, wget, curl, or aspera"
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Optional output directory for downloads"
    )


class SRADirectDownloadInput(BaseModel):
    """Input for direct SRA download."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    sra_id: str = Field(
        ...,
        description="SRA accession ID (e.g., SRR1234567)",
        pattern=r'^[SED]RR\d+$'
    )
    convert_to_fastq: bool = Field(
        default=False,
        description="Whether to convert SRA to FASTQ format (requires sra-toolkit)"
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Optional output directory"
    )


class CleanupInput(BaseModel):
    """Input for cleanup operations."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    geo_id: Optional[str] = Field(
        default=None,
        description="Optional specific GEO ID to remove"
    )
    db_type: Optional[str] = Field(
        default=None,
        description="Optional database type filter for cleanup (gse, gsm, gpl, gds, sra)"
    )


# ============================================================================
# Helper Functions
# ============================================================================

def format_as_markdown(data: dict, title: str = "Results") -> str:
    """Format results as markdown for human readability."""
    lines = [f"# {title}", ""]
    
    def format_value(value, indent=0):
        prefix = "  " * indent
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{prefix}- **{k}:**")
                    format_value(v, indent + 1)
                else:
                    lines.append(f"{prefix}- **{k}:** {v}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"{prefix}-")
                    format_value(item, indent + 1)
                else:
                    lines.append(f"{prefix}- {item}")
        else:
            lines.append(f"{prefix}{value}")
    
    format_value(data)
    return "\n".join(lines)


def handle_error(error: Exception) -> str:
    """Format error messages consistently."""
    if isinstance(error, GEOSearchError):
        return f"GEO Search Error: {str(error)}"
    elif isinstance(error, GEODownloadError):
        return f"GEO Download Error: {str(error)}"
    elif isinstance(error, SRAError):
        return f"SRA Error: {str(error)}"
    elif isinstance(error, ValueError):
        return f"Validation Error: {str(error)}"
    else:
        return f"Error: {type(error).__name__}: {str(error)}"


# ============================================================================
# GEO Search Tools
# ============================================================================

@mcp.tool(
    name="geo_search",
    annotations={
        "title": "Search GEO Database",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def geo_search(params: SearchWithTypesInput) -> str:
    '''Search GEO for all types of records (GSE, GSM, GPL, GDS).
    
    This tool searches across all GEO databases and returns categorized results
    by record type (Series, Samples, Platforms, Datasets).
    
    Args:
        params: Search parameters including term, retmax, record_types, and response_format
        
    Returns:
        JSON or Markdown formatted search results
        
    Examples:
        - Search for cancer studies: term="breast cancer"
        - Find specific series: term="GSE12345"
        - Search for RNA-seq data: term="RNA-seq"
        - Filter to only series: record_types=["GSE"]
    '''
    try:
        client = GEOSearchClient()
        result = await client.search_geo(
            term=params.term,
            retmax=params.retmax,
            record_types=params.record_types
        )
        
        if params.response_format == ResponseFormat.MARKDOWN:
            return format_as_markdown(result, f"GEO Search Results: '{params.term}'")
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="geo_search_series",
    annotations={
        "title": "Search GEO Series",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def geo_search_series(params: SearchInput) -> str:
    '''Search for GEO Series (GSE) - complete experiments.
    
    Args:
        params: Search parameters including term and retmax
        
    Returns:
        JSON or Markdown formatted GSE search results
    '''
    try:
        client = GEOSearchClient()
        result = await client.search_geo_series(params.term, params.retmax)
        
        if params.response_format == ResponseFormat.MARKDOWN:
            return format_as_markdown(result, f"GEO Series Search: '{params.term}'")
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="geo_search_samples",
    annotations={
        "title": "Search GEO Samples",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def geo_search_samples(params: SearchInput) -> str:
    '''Search for GEO Samples (GSM) - individual samples.
    
    Args:
        params: Search parameters including term and retmax
        
    Returns:
        JSON or Markdown formatted GSM search results
    '''
    try:
        client = GEOSearchClient()
        result = await client.search_geo_samples(params.term, params.retmax)
        
        if params.response_format == ResponseFormat.MARKDOWN:
            return format_as_markdown(result, f"GEO Sample Search: '{params.term}'")
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="geo_search_platforms",
    annotations={
        "title": "Search GEO Platforms",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def geo_search_platforms(params: SearchInput) -> str:
    '''Search for GEO Platforms (GPL) - array/sequencing platforms.
    
    Args:
        params: Search parameters including term and retmax
        
    Returns:
        JSON or Markdown formatted GPL search results
    '''
    try:
        client = GEOSearchClient()
        result = await client.search_geo_platforms(params.term, params.retmax)
        
        if params.response_format == ResponseFormat.MARKDOWN:
            return format_as_markdown(result, f"GEO Platform Search: '{params.term}'")
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="geo_search_datasets",
    annotations={
        "title": "Search GEO Datasets",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def geo_search_datasets(params: SearchInput) -> str:
    '''Search for GEO Datasets (GDS) - curated gene expression datasets.
    
    Args:
        params: Search parameters including term and retmax
        
    Returns:
        JSON or Markdown formatted GDS search results
    '''
    try:
        client = GEOSearchClient()
        result = await client.search_geo_datasets(params.term, params.retmax)
        
        if params.response_format == ResponseFormat.MARKDOWN:
            return format_as_markdown(result, f"GEO Dataset Search: '{params.term}'")
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="geo_search_profiles",
    annotations={
        "title": "Search GEO Profiles",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def geo_search_profiles(params: SearchInput) -> str:
    '''Search GEO Profiles database for gene expression profiles.
    
    Args:
        params: Search parameters including term and retmax
        
    Returns:
        JSON or Markdown formatted GEO Profiles search results
    '''
    try:
        client = GEOSearchClient()
        result = await client.search_geo_profiles(params.term, params.retmax)
        
        if params.response_format == ResponseFormat.MARKDOWN:
            return format_as_markdown(result, f"GEO Profiles Search: '{params.term}'")
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


# ============================================================================
# GEO Download Tools
# ============================================================================

@mcp.tool(
    name="geo_download_series",
    annotations={
        "title": "Download GEO Series Data",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def geo_download_series(params: DownloadInput) -> str:
    '''Download GEO Series data files (SOFT, matrix, supplementary).
    
    Downloads data files for a GEO Series including:
    - SOFT format metadata (soft)
    - Series matrix file (matrix)
    - MINiML XML (miniml)
    - Supplementary files (supplementary)
    
    Args:
        params: Download parameters including geo_id, file_types, and output_dir
        
    Returns:
        JSON formatted download results
        
    Examples:
        - Download SOFT file: geo_id="GSE12345", file_types=["soft"]
        - Download all: geo_id="GSE12345", file_types=["soft", "matrix", "supplementary"]
    '''
    try:
        client = GEODownloadClient()
        output_dir = Path(params.output_dir) if params.output_dir else None
        
        result = await client.download_geo_series(
            gse_id=params.geo_id.upper(),
            file_types=params.file_types,
            output_dir=output_dir
        )
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="geo_download_sample",
    annotations={
        "title": "Download GEO Sample Data",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def geo_download_sample(params: DownloadInput) -> str:
    '''Download GEO Sample supplementary files.
    
    Downloads supplementary data files for a specific GEO Sample (GSM).
    
    Args:
        params: Download parameters including geo_id (GSM) and output_dir
        
    Returns:
        JSON formatted download results
    '''
    try:
        client = GEODownloadClient()
        output_dir = Path(params.output_dir) if params.output_dir else None
        
        result = await client.download_geo_sample(
            gsm_id=params.geo_id.upper(),
            output_dir=output_dir
        )
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="geo_get_download_status",
    annotations={
        "title": "Get GEO Download Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def geo_get_download_status(params: GeoIdInput) -> str:
    '''Check if a GEO dataset has been downloaded.
    
    Args:
        params: Parameters including geo_id and optional db_type
        
    Returns:
        JSON formatted status information
    '''
    try:
        client = GEODownloadClient()
        
        # Determine db_type from geo_id prefix
        db_type = params.geo_id[:3].lower()
        
        result = client.get_download_status(
            accession=params.geo_id.upper(),
            db_type=db_type
        )
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="geo_list_downloads",
    annotations={
        "title": "List Downloaded GEO Datasets",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def geo_list_downloads(db_type: Optional[str] = None) -> str:
    '''List all downloaded GEO datasets.
    
    Args:
        db_type: Optional filter by database type (gse, gsm, gpl, gds, sra)
        
    Returns:
        JSON formatted list of downloaded datasets
    '''
    try:
        client = GEODownloadClient()
        result = client.list_downloaded_datasets(db_type)
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="geo_cleanup_downloads",
    annotations={
        "title": "Clean Up GEO Downloads",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False
    }
)
async def geo_cleanup_downloads(params: CleanupInput) -> str:
    '''Clean up downloaded GEO files.
    
    Args:
        params: Parameters including optional geo_id and db_type to remove
        
    Returns:
        JSON formatted cleanup results
        
    Warning:
        This is a destructive operation that deletes downloaded files.
    '''
    try:
        client = GEODownloadClient()
        result = client.cleanup_downloads(
            accession=params.geo_id,
            db_type=params.db_type
        )
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


# ============================================================================
# SRA Tools (NEW - for raw sequencing data)
# ============================================================================

@mcp.tool(
    name="sra_query_from_geo",
    annotations={
        "title": "Query SRA Accessions from GEO Series",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def sra_query_from_geo(params: SRASearchInput) -> str:
    '''Query SRA Run information from a GEO Series.
    
    This tool extracts the mapping between GEO Samples (GSM) and 
    SRA Run accessions (SRR) from a GEO Series. This allows you to
    identify which SRA files contain the raw sequencing data for a dataset.
    
    Args:
        params: Parameters including gse_id
        
    Returns:
        JSON formatted SRA accession information
        
    Example:
        Input: gse_id="GSE12345"
        Output: {
            "gse_id": "GSE12345",
            "total_samples": 10,
            "samples_with_sra": 8,
            "all_sra_accessions": ["SRR1234567", "SRR1234568", ...],
            "samples": [
                {
                    "gsm_id": "GSM123456",
                    "sra_accessions": ["SRR1234567"]
                }
            ]
        }
    '''
    try:
        handler = SRAHandler()
        result = await handler.query_sra_from_geo(params.gse_id.upper())
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="sra_get_metadata",
    annotations={
        "title": "Get SRA Run Metadata",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def sra_get_metadata(sra_id: str) -> str:
    '''Get metadata for an SRA Run accession.
    
    Args:
        sra_id: SRA accession ID (e.g., SRR1234567)
        
    Returns:
        JSON formatted SRA metadata
    '''
    try:
        handler = SRAHandler()
        result = await handler.get_sra_metadata(sra_id)
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="sra_generate_download_commands",
    annotations={
        "title": "Generate SRA Download Commands",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def sra_generate_download_commands(params: SRADownloadInput) -> str:
    '''Generate commands to download SRA data.
    
    Generates download commands for SRA accessions using various methods:
    - prefetch: Using sra-toolkit prefetch (recommended)
    - fasterq-dump: Download and convert to FASTQ in one step
    - wget: Direct HTTP download
    - curl: Direct HTTP download using curl
    - aspera: High-speed Aspera download
    
    Args:
        params: Parameters including sra_ids list, method, and output_dir
        
    Returns:
        JSON formatted commands and instructions
        
    Note:
        This tool generates commands but does not execute them.
        Run the commands in your terminal or use the shell tool.
    '''
    try:
        handler = SRAHandler()
        result = handler.generate_download_commands(
            sra_ids=[s.upper() for s in params.sra_ids],
            method=params.method.value,
            output_dir=params.output_dir
        )
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="sra_check_toolkit",
    annotations={
        "title": "Check SRA Toolkit Installation",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def sra_check_toolkit() -> str:
    '''Check if SRA Toolkit is installed and available.
    
    Returns:
        JSON formatted toolkit status and installation information
    '''
    try:
        handler = SRAHandler()
        result = handler.check_sra_toolkit()
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="sra_download",
    annotations={
        "title": "Download SRA Data Directly",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def sra_download(params: SRADirectDownloadInput) -> str:
    '''Download SRA data directly (without sra-toolkit).
    
    Note: For large files or multiple downloads, using sra-toolkit
    prefetch is recommended instead. This method is suitable for
    small files or when sra-toolkit is not available.
    
    Args:
        params: Parameters including sra_id, convert_to_fastq, and output_dir
        
    Returns:
        JSON formatted download results
    '''
    try:
        handler = SRAHandler()
        output_dir = Path(params.output_dir) if params.output_dir else None
        
        result = await handler.download_sra(
            sra_id=params.sra_id.upper(),
            convert_to_fastq=params.convert_to_fastq,
            output_dir=output_dir
        )
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


class SRADownloadAndConvertInput(BaseModel):
    """Input for SRA download and convert operations."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    sra_id: str = Field(
        ...,
        description="SRA accession ID (e.g., SRR1234567)",
        pattern=r'^[SED]RR\d+$'
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Optional output directory (default: ~/geo_downloads/sra/<sra_id>). REQUIRED for files >1GB"
    )
    split_3: bool = Field(
        default=True,
        description="Use --split-3 for 3-way splitting (recommended for mate-pairs)"
    )
    check_refseq: bool = Field(
        default=True,
        description="Whether to check/download reference sequences (disable to save space)"
    )
    dry_run: bool = Field(
        default=True,
        description="SAFETY: If True (default), only estimates size without downloading. Set to False to actually download."
    )
    confirm_large: bool = Field(
        default=False,
        description="SAFETY: Must be True to download files >5GB. Use dry_run=True first to check size."
    )


class SRASizeEstimateInput(BaseModel):
    """Input for SRA size estimation (dry-run)."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    sra_ids: List[str] = Field(
        ...,
        description="List of SRA accession IDs to estimate (e.g., ['SRR1234567', 'SRR1234568'])",
        min_length=1
    )


@mcp.tool(
    name="sra_download_and_convert",
    annotations={
        "title": "Download SRA and Convert to FASTQ",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def sra_download_and_convert(params: SRADownloadAndConvertInput) -> str:
    '''Download SRA data using prefetch and convert to FASTQ using fastq-dump.
    
    SAFETY FEATURES (following maintainer recommendations):
    - DRY-RUN BY DEFAULT: dry_run=True (default) only estimates size without downloading
    - SIZE WARNINGS: Alerts for files >1GB, requires confirmation for >5GB
    - EXPLICIT OUTPUT: Required output_dir for files >1GB
    - CONFIRMATION: confirm_large=True required for files >5GB
    
    RECOMMENDED WORKFLOW:
    1. First, run with dry_run=True to see size estimates
    2. If size is acceptable, run with dry_run=False and output_dir="/path"
    3. For large files (>5GB), also set confirm_large=True
    
    Args:
        params: Parameters including sra_id, output_dir, split_3, check_refseq, dry_run, confirm_large
        
    Returns:
        JSON formatted results with download/conversion details OR dry-run estimates
        
    Examples:
        - Step 1: Check size first
          sra_id="SRR1234567", dry_run=true
          
        - Step 2a: Download small file (<1GB)
          sra_id="SRR1234567", dry_run=false
          
        - Step 2b: Download medium file (1-5GB)
          sra_id="SRR1234567", dry_run=false, output_dir="/path/to/output"
          
        - Step 2c: Download large file (>5GB)
          sra_id="SRR1234567", dry_run=false, output_dir="/path/to/output", confirm_large=true
    '''
    try:
        handler = SRAHandler()
        output_dir = Path(params.output_dir) if params.output_dir else None
        
        result = await handler.download_and_convert(
            sra_id=params.sra_id.upper(),
            output_dir=output_dir,
            split_3=params.split_3,
            check_refseq=params.check_refseq,
            dry_run=params.dry_run,
            confirm_large=params.confirm_large
        )
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


@mcp.tool(
    name="sra_estimate_size",
    annotations={
        "title": "Estimate SRA Download Size (Dry-Run)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def sra_estimate_size(params: SRASizeEstimateInput) -> str:
    '''Estimate the size of SRA files before downloading (dry-run mode).
    
    This tool queries the EBI ENA database to get file size estimates without
    actually downloading any data. Use this before sra_download_and_convert
    to check if you have sufficient disk space.
    
    Args:
        params: Parameters including list of sra_ids to estimate
        
    Returns:
        JSON formatted size estimates and safety warnings:
        - Individual file sizes (SRA and estimated FASTQ)
        - Total download size
        - Safety warnings for large files (>1GB, >5GB)
        
    Examples:
        - Estimate single file: sra_ids=["SRR1234567"]
        - Estimate multiple: sra_ids=["SRR1234567", "SRR1234568"]
    '''
    try:
        handler = SRAHandler()
        
        result = await handler.estimate_sra_size(
            sra_ids=[s.upper() for s in params.sra_ids]
        )
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return handle_error(e)


# ============================================================================
# Main Entry Point
# ============================================================================

def init_config():
    """Initialize configuration file."""
    config_path = Path.home() / ".geo-mcp" / "config.json"
    create_config_template(config_path)
    print(f"\nConfiguration template created at: {config_path}")
    print("\nPlease edit the file and add your email address (required by NCBI).")
    print("Optionally, add your NCBI API key for higher rate limits.")
    print(f"\nTo use with Claude Desktop, add this to your config:")
    print(json.dumps({
        "mcpServers": {
            "geo_mcp": {
                "command": "python",
                "args": [str(Path(__file__).resolve())],
                "env": {
                    "CONFIG_PATH": str(config_path)
                }
            }
        }
    }, indent=2))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="GEO MCP Server with SRA Support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python server.py --init              # Initialize configuration
  python server.py                     # Run MCP stdio server
  python server.py --http              # Run HTTP server on localhost:8000
  python server.py --http --port 8080  # Run HTTP server on custom port
        """
    )
    
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize configuration file"
    )
    
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run HTTP server instead of MCP stdio"
    )
    
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host for HTTP server (default: localhost)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP server (default: 8000)"
    )
    
    args = parser.parse_args()
    
    if args.init:
        init_config()
        return
    
    # Validate config before starting
    try:
        config = get_config()
        validate_config(config)
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("Run with --init to create a configuration template.", file=sys.stderr)
        sys.exit(1)
    
    if args.http:
        # Run HTTP server
        print(f"Starting HTTP server on http://{args.host}:{args.port}")
        mcp.run(transport="streamable_http", host=args.host, port=args.port)
    else:
        # Run MCP stdio server
        mcp.run()


if __name__ == "__main__":
    main()
