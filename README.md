# GEO MCP Server with SRA Support

An enhanced [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for accessing **GEO (Gene Expression Omnibus)** data through NCBI E-Utils API, with comprehensive support for **SRA (Sequence Read Archive)** raw sequencing data downloads and conversion.

## Features

### GEO Data Access
- 🔍 **Search GEO databases**: Series (GSE), Samples (GSM), Platforms (GPL), Datasets (GDS), and Profiles
- 📥 **Download metadata**: SOFT format, Series Matrix, MINiML XML
- 📦 **Download supplementary files**: Processed data tables, raw array data

### SRA Raw Sequencing Data (NEW)
- 🔗 **Query SRA from GEO**: Map GEO Samples (GSM) to SRA Runs (SRR)
- 📊 **Size estimation**: Dry-run mode to check file sizes before downloading
- 💾 **Download & convert**: Integrated prefetch + fastq-dump workflow
- 🛡️ **Safety constraints**: Size warnings and confirmation requirements
- ✅ **Check sra-toolkit**: Verify installation and get setup instructions

## Safety Features

Following [maintainer recommendations](https://github.com/MCPmed/GEOmcp/issues/1), this server implements safety constraints for large file downloads:

| Constraint | Implementation |
|------------|----------------|
| **Safe by Default** | `dry_run=True` by default - only estimates sizes |
| **Dry-Run Mode** | `sra_estimate_size()` tool for size checking |
| **Explicit Output** | Required `output_dir` for files >1GB |
| **Confirmation** | `confirm_large=True` required for files >5GB |

## Installation

### Prerequisites
- Python 3.10 or higher
- (Optional) [SRA Toolkit](https://github.com/ncbi/sra-tools) for downloading raw FASTQ files

### Install from Source
```bash
# Clone the repository
git clone https://github.com/yourusername/geo-mcp-server.git
cd geo-mcp-server

# Install dependencies
pip install -e .
```

### Configuration

1. **Initialize configuration:**
```bash
python server.py --init
```

2. **Edit the config file** at `~/.geo-mcp/config.json`:
```json
{
    "email": "your_email@example.com",
    "api_key": "YOUR_NCBI_API_KEY (optional)",
    "download_dir": "~/geo_downloads",
    "sra_toolkit_path": "/path/to/sra-toolkit/bin (optional)"
}
```

> **Note:** NCBI requires an email address for E-Utils access. An API key is optional but recommended for higher rate limits (10 req/s vs 3 req/s). Get one at [NCBI](https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/).

## Usage

### Running the Server

**MCP stdio mode** (for Claude Desktop):
```bash
python server.py
```

**HTTP mode**:
```bash
python server.py --http --port 8000
```

### Claude Desktop Integration

Add to your Claude Desktop configuration (`~/.config/claude-desktop/config.json`):

```json
{
  "mcpServers": {
    "geo_mcp": {
      "command": "python",
      "args": ["/path/to/geo_mcp_server/server.py"],
      "env": {
        "CONFIG_PATH": "/home/yourusername/.geo-mcp/config.json"
      }
    }
  }
}
```

## Available Tools (18 Total)

### GEO Search Tools

| Tool | Description |
|------|-------------|
| `geo_search` | Search all GEO record types with natural language (e.g., "Human RNA-seq") |
| `geo_search_series` | Search GEO Series (GSE) - complete experiments |
| `geo_search_samples` | Search GEO Samples (GSM) - individual samples |
| `geo_search_platforms` | Search GEO Platforms (GPL) - array/sequencing platforms |
| `geo_search_datasets` | Search GEO Datasets (GDS) - curated gene expression |
| `geo_search_profiles` | Search GEO Profiles - gene expression profiles |

### GEO Download Tools

| Tool | Description |
|------|-------------|
| `geo_download_series` | Download GSE data files (SOFT, matrix, supplementary) |
| `geo_download_sample` | Download GSM supplementary files |
| `geo_get_download_status` | Check if a GEO dataset has been downloaded |
| `geo_list_downloads` | List all downloaded datasets |
| `geo_cleanup_downloads` | Clean up downloaded files |

### SRA Tools

| Tool | Description |
|------|-------------|
| `sra_query_from_geo` | Query SRA Run information from a GEO Series |
| `sra_get_metadata` | Get SRA run metadata |
| `sra_estimate_size` | **NEW** Estimate download sizes before downloading (dry-run) |
| `sra_generate_download_commands` | Generate download commands for various methods |
| `sra_check_toolkit` | Check sra-toolkit installation |
| `sra_download` | Download SRA directly via HTTP (small files only) |
| `sra_download_and_convert` | **NEW** Download with prefetch and convert to FASTQ |

## Example Workflows

### 1. Search with Natural Language

```
User: Find Human RNA-seq datasets

AI: I'll search for Human RNA-seq datasets in GEO.
[Uses geo_search_series with term="Human RNA-seq"]

Results:
- GSE319287: "TPD52 Inhibits Aldosterone Synthesis..." (6 samples)
- GSE213095: "Positive feedback between cDC1s and CD8+ T cells..." (46 samples)
- GSE320065: "Transcriptomic and Functional Responses of Human Airway Cells..." (56 samples)
```

### 2. Download Processed Data

```
User: Download the metadata for GSE12345

AI: I'll download the SOFT file and series matrix for GSE12345.
[Uses geo_download_series with geo_id="GSE12345", file_types=["soft", "matrix"]]

Results:
✓ Downloaded GSE12345_family.soft.gz (1.2 MB)
✓ Downloaded GSE12345_series_matrix.txt.gz (5.6 MB)
Location: ~/geo_downloads/gse/GSE12345/
```

### 3. Find and Download Raw Sequencing Data (Safe Workflow)

**Step 1: Get SRA accessions**
```
User: Get the SRA run accessions for GSE272467

AI: I'll query the SRA information from this GEO Series.
[Uses sra_query_from_geo with gse_id="GSE272467"]

Results:
- Total samples: 4
- Samples with SRA data: 4
- Total SRA runs: 4
- All SRA accessions: ["SRR29864801", "SRR29864802", "SRR29864803", "SRR29864804"]
```

**Step 2: Estimate size (recommended)**
```
User: How large are these files?

AI: Let me estimate the download sizes.
[Uses sra_estimate_size with sra_ids=["SRR29864801"]]

Results:
- SRA size: ~76 MB
- Estimated FASTQ size: ~190 MB
- Read count: 7,178,576
- Warning: Small file (< 100 MB)
```

**Step 3: Download and convert**
```
User: Download and convert SRR29864801 to FASTQ

AI: I'll download the SRA file and convert it to FASTQ format.
[Uses sra_download_and_convert with sra_id="SRR29864801", dry_run=False]

Results:
✓ Downloaded SRR29864801.sra (76 MB)
✓ Converted to FASTQ
  - SRR29864801_1.fastq (660 KB, 5000 reads)
  - SRR29864801_2.fastq (660 KB, 5000 reads)
Location: ~/geo_downloads/sra/SRR29864801/
```

### 4. Safety Constraints in Action

```
User: Download SRR1234567

AI: First, let me estimate the size before downloading.
[Uses sra_estimate_size with sra_ids=["SRR1234567"]]

Results:
- SRA size: ~2.5 GB
- Estimated FASTQ size: ~6.25 GB
- Warning: LARGE FILE (1-5 GB)

⚠️ This is a large download that requires explicit output directory.
Please provide output_dir parameter to proceed.

User: Download to /data/sra

AI: 
[Uses sra_download_and_convert with 
 sra_id="SRR1234567", 
 dry_run=False, 
 output_dir="/data/sra"]

✓ Download complete!
```

### 5. Check SRA Toolkit

```
User: Do I have sra-toolkit installed?

AI: Let me check your sra-toolkit installation.
[Uses sra_check_toolkit]

Results:
✓ prefetch: available (version 3.3.0)
✓ fastq-dump: available (version 3.3.0)
✓ fasterq-dump: available (version 3.3.0)
✓ vdb-validate: available (version 3.3.0)

All tools are installed and ready to use!
```

## SRA Download Methods

### Method 1: Using sra_download_and_convert (Recommended)

Integrated workflow with safety features:
```python
# Step 1: Estimate size (dry-run)
sra_estimate_size(sra_ids=["SRR1234567"])

# Step 2: Download and convert based on size
# Small file (<1GB)
sra_download_and_convert(sra_id="SRR1234567", dry_run=False)

# Medium file (1-5GB) - requires output_dir
sra_download_and_convert(
    sra_id="SRR1234567",
    dry_run=False,
    output_dir="/path/to/output"
)

# Large file (>5GB) - requires confirmation
sra_download_and_convert(
    sra_id="SRR1234567",
    dry_run=False,
    output_dir="/path/to/output",
    confirm_large=True
)
```

### Method 2: Using SRA Toolkit Manually

1. **Install sra-toolkit**: Follow instructions at https://github.com/ncbi/sra-tools

2. **Download and convert**:
```bash
# Download SRA file
prefetch SRR1234567

# Convert to FASTQ (3-way split for paired-end)
fastq-dump --split-3 SRR1234567
```

### Method 3: Direct HTTP Download (Small Files Only)

For small files or when sra-toolkit is not available:
```bash
# Using wget
wget https://sra-downloadb.be-md.ncbi.nlm.nih.gov/sos2/sra-pub-run-11/SRR1234567/SRR1234567.1

# Using curl
curl -o SRR1234567.sra https://sra-downloadb.be-md.ncbi.nlm.nih.gov/sos2/sra-pub-run-11/SRR1234567/SRR1234567.1
```

## Project Structure

```
geo_mcp_server/
├── geomcp_sra/
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── geo_search.py      # GEO search functionality (E-Utilities)
│   ├── geo_download.py    # GEO data download
│   └── sra_handler.py     # SRA query, size estimation, download & convert
├── server.py              # Main MCP server with 18 tools
├── config.json            # Configuration template
├── pyproject.toml         # Project dependencies
├── requirements.txt       # Python dependencies
├── README.md              # This file
└── SKILL.md               # Skill documentation
```

## Comparison with Original GEOmcp

| Feature | GEOmcp (Original) | This Project (geo-mcp-server) |
|---------|-------------------|---------------------------|
| GEO Search | ✓ | ✓ (Enhanced with natural language) |
| SOFT Download | ✓ | ✓ |
| Matrix Download | ✓ | ✓ |
| Supplementary Files | ✓ | ✓ |
| **SRA Query** | ✗ | **✓** |
| **SRR Mapping** | ✗ | **✓** |
| **Size Estimation** | ✗ | **✓ (Dry-run mode)** |
| **Download & Convert** | ✗ | **✓ (Integrated workflow)** |
| **Safety Constraints** | ✗ | **✓ (>1GB, >5GB checks)** |
| Tool Count | 11 | **18** |

## Configuration Options

### Full Config File Reference

>>>>>>> ad562a4 (initialize files, commit to branch Test)
```json
{
    "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
    "email": "your_email@example.com",
    "api_key": "YOUR_NCBI_API_KEY (optional but recommended)",
    "download_dir": "~/geo_downloads",
    "max_file_size_mb": 5000,
    "max_total_downloads_mb": 10000,
    "max_concurrent_downloads": 3,
    "download_timeout_seconds": 300,
    "allowed_download_paths": ["~/geo_downloads", "/tmp/geo_downloads"],
    "sra_toolkit_path": "/path/to/sra-toolkit/bin (optional)"
}
```

## Troubleshooting

### Email not configured
```
Error: Email is required for NCBI E-utilities.
```
**Solution**: Edit `~/.geo-mcp/config.json` and add your email address.

### SRA toolkit not found
```
fasterq-dump not found. Please install sra-toolkit.
```
**Solution**: Install sra-toolkit from https://github.com/ncbi/sra-tools and set `sra_toolkit_path` in config.

### Rate limiting
```
Error: Rate limit exceeded
```
**Solution**: Add an NCBI API key to your config for higher rate limits (10 req/s vs 3 req/s).

### Large file safety error
```
SAFETY CHECK: File size is ~2.5 GB. Large downloads require an explicit output directory.
```
**Solution**: Provide `output_dir` parameter for files >1GB, or both `output_dir` and `confirm_large=True` for files >5GB.

## References

- [GEO Home](https://www.ncbi.nlm.nih.gov/geo/)
- [SRA Home](https://www.ncbi.nlm.nih.gov/sra)
- [NCBI E-Utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
- [SRA Toolkit Documentation](https://github.com/ncbi/sra-tools/wiki)
- [MCP Documentation](https://modelcontextprotocol.io/)

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

### Contributing SRA Support Back to Original GEOmcp

This project implements the [enhancement request](https://github.com/MCPmed/GEOmcp/issues/1) for SRA raw data support with the following safety features as recommended by maintainers:
- Safe by default (dry-run mode)
- Size estimation before download
- Explicit output directory requirement for large files
- Confirmation for very large files (>5GB)

## Acknowledgments

- Original [GEOmcp](https://github.com/MCPmed/GEOmcp) project for the foundation
- NCBI for providing the GEO and SRA databases
- MCP team for the Model Context Protocol
