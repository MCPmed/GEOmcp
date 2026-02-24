---
name: geo-mcp
description: MCP server for accessing GEO (Gene Expression Omnibus) data with comprehensive SRA (Sequence Read Archive) raw sequencing support. Enables natural language search, metadata download, size estimation with dry-run mode, and safe FASTQ downloads with prefetch/fastq-dump integration.
---

# GEO MCP Server with SRA Support

This skill provides a Model Context Protocol (MCP) server for accessing NCBI's GEO and SRA databases programmatically with enhanced safety features for large file downloads.

## Capabilities

### GEO Data Access
- Search GEO databases (GSE, GSM, GPL, GDS, Profiles) using natural language
- Download SOFT format metadata files
- Download series matrix files
- Download supplementary processed data

### SRA Raw Sequencing Data (with Safety Features)
- Query SRA Run accessions from GEO Series
- Map GSM samples to SRR run accessions
- **Estimate download sizes** (dry-run mode)
- **Download & convert** with integrated prefetch + fastq-dump workflow
- **Safety constraints**: Size warnings, explicit output directory, confirmation for large files

## Installation

```bash
cd /path/to/geo_mcp_server
pip install -e .
```

## Configuration

1. Create config file:
```bash
python3 server.py --init
```

2. Edit `~/.geo-mcp/config.json`:
```json
{
    "email": "your_email@example.com",
    "api_key": "YOUR_NCBI_API_KEY (optional but recommended)",
    "download_dir": "~/geo_downloads",
    "sra_toolkit_path": "/path/to/sra-toolkit/bin (optional)"
}
```

> **Note:** NCBI requires an email address. API key provides higher rate limits (10 req/s vs 3 req/s).

## Usage with Claude Desktop

Add to `~/.config/claude-desktop/config.json`:

```json
{
  "mcpServers": {
    "geo_mcp": {
      "command": "python3",
      "args": ["/path/to/geo_mcp_server/server.py"],
      "env": {
        "CONFIG_PATH": "/home/username/.geo-mcp/config.json"
      }
    }
  }
}
```

## Available Tools (18 Total)

### Search Tools (Natural Language Support)

All search tools support natural language queries like "Human RNA-seq", "mouse brain single cell", "breast cancer transcriptome".

| Tool | Description | Example Query |
|------|-------------|---------------|
| `geo_search` | Universal GEO search | "cancer RNA-seq" |
| `geo_search_series` | Search GSE records | "Human RNA-seq" |
| `geo_search_samples` | Search GSM records | "HeLa cell line" |
| `geo_search_platforms` | Search GPL records | "Illumina HiSeq" |
| `geo_search_datasets` | Search GDS records | "breast cancer" |
| `geo_search_profiles` | Search GEO Profiles | "p53 expression" |

### GEO Download Tools

| Tool | Description |
|------|-------------|
| `geo_download_series` | Download GSE data (SOFT, matrix, supplementary) |
| `geo_download_sample` | Download GSM supplementary files |
| `geo_get_download_status` | Check download status |
| `geo_list_downloads` | List downloaded datasets |
| `geo_cleanup_downloads` | Clean up files |

### SRA Tools

| Tool | Description | Safety Features |
|------|-------------|-----------------|
| `sra_query_from_geo` | Get SRA accessions from GEO Series | - |
| `sra_get_metadata` | Get SRA run metadata | - |
| `sra_estimate_size` | **Estimate sizes (dry-run)** | Shows warnings for >1GB, >5GB |
| `sra_generate_download_commands` | Generate download commands | - |
| `sra_check_toolkit` | Check sra-toolkit installation | - |
| `sra_download` | Direct HTTP download | Small files only |
| `sra_download_and_convert` | **Download & convert to FASTQ** | dry_run=True default, size checks |

## Safety Features

### Default Safe Behavior

All SRA downloads default to **dry-run mode** (`dry_run=True`):

```python
# This only estimates size, does NOT download
sra_download_and_convert(sra_id="SRR1234567")
```

### Size-Based Safety Constraints

| File Size | Required Parameters |
|-----------|---------------------|
| < 1 GB | `dry_run=False` |
| 1-5 GB | `dry_run=False` + `output_dir="/path"` |
| > 5 GB | `dry_run=False` + `output_dir="/path"` + `confirm_large=True` |

### Safety Check Examples

**Error for >1GB without output_dir:**
```
SAFETY CHECK: File size is ~2.5 GB. Large downloads require an explicit 
output directory. Please provide output_dir parameter.
Tip: Run with dry_run=True first to see size estimates.
```

**Error for >5GB without confirmation:**
```
SAFETY CHECK: File size is ~6.2 GB (>5GB). This is a VERY LARGE download 
that will consume significant disk space and time. 
To proceed, set confirm_large=True.
```

## Example Workflows

### Workflow 1: Search with Natural Language

```python
# Search for Human RNA-seq datasets
geo_search_series(term="Human RNA-seq", retmax=10)

# Search for specific tissue + disease
geo_search_series(term="mouse brain Alzheimer's", retmax=5)
```

### Workflow 2: Safe SRA Download

**Step 1: Always estimate first**
```python
sra_estimate_size(sra_ids=["SRR1234567"])
# Returns: SRA size, FASTQ estimate, read count, safety warnings
```

**Step 2: Download based on size**

Small file (<1GB):
```python
sra_download_and_convert(
    sra_id="SRR1234567",
    dry_run=False,
    split_3=True,           # Properly handle paired-end
    check_refseq=False      # Skip refseq to save space
)
```

Medium file (1-5GB):
```python
sra_download_and_convert(
    sra_id="SRR1234567",
    dry_run=False,
    output_dir="/data/sra",  # Required!
    split_3=True
)
```

Large file (>5GB):
```python
sra_download_and_convert(
    sra_id="SRR1234567",
    dry_run=False,
    output_dir="/data/sra",   # Required
    confirm_large=True,        # Required
    split_3=True
)
```

### Workflow 3: Complete Analysis Pipeline

```python
# 1. Search for datasets
results = geo_search_series(term="GLOR2 m6A", retmax=5)

# 2. Get SRA accessions for a dataset
sra_info = sra_query_from_geo(gse_id="GSE272467")
# Returns: 4 SRR accessions

# 3. Estimate sizes
sizes = sra_estimate_size(sra_ids=sra_info["all_sra_accessions"])
# Shows: ~76 MB each, total ~304 MB

# 4. Download and convert
for sra_id in sra_info["all_sra_accessions"]:
    sra_download_and_convert(
        sra_id=sra_id,
        dry_run=False,
        split_3=True,
        check_refseq=False
    )
```

## Architecture

```
geo_mcp_server/
├── geomcp_sra/
│   ├── config.py          # Configuration management
│   ├── geo_search.py      # NCBI E-Utilities search
│   ├── geo_download.py    # FTP/HTTP downloads
│   └── sra_handler.py     # SRA query, size estimation, download & convert
├── server.py              # MCP server with 18 tools (FastMCP)
├── config.json            # Config template
└── pyproject.toml         # Project metadata
```

## Dependencies

- `mcp>=1.9.0` - MCP Python SDK
- `httpx>=0.27.0` - Async HTTP client
- `aiofiles>=23.0.0` - Async file operations
- `pydantic>=2.0.0` - Input validation

## References

- [GEO Documentation](https://www.ncbi.nlm.nih.gov/geo/info/)
- [SRA Documentation](https://www.ncbi.nlm.nih.gov/sra/docs/)
- [SRA Toolkit](https://github.com/ncbi/sra-tools)
- [MCP Specification](https://modelcontextprotocol.io/)
- [Original GEOmcp Issue #1 - SRA Support](https://github.com/MCPmed/GEOmcp/issues/1)
