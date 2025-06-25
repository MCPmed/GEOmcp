# Gene Expression Omnibus (GEO) MCP

<div align="center">
  <img src="https://www.ncbi.nlm.nih.gov/geo/img/geo_main.gif" alt="GEO Logo" width="200"/>
  <br/>
  <em>Gene Expression Omnibus (GEO) - A public functional genomics data repository</em>
</div>

[![PyPI version](https://badge.fury.io/py/geo-bio-mcp.svg)](https://pypi.org/project/geo-bio-mcp/)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Protocol-blue.svg)](https://modelcontextprotocol.io/)
[![GEO](https://img.shields.io/badge/GEO-NCBI-orange.svg)](https://www.ncbi.nlm.nih.gov/geo/)

> ⚠️ **Development Warning** ⚠️
> 
> **This project is currently in active development and is not yet production-ready.**
> 
> - The MCP stdio server is functional but may have bugs or incomplete features
> - The HTTP server is in early development phase and has **not been properly tested**
> - API endpoints and functionality may change without notice
> - Use at your own risk and report any issues you encounter
> 
> We recommend testing thoroughly in a development environment before using in production.

A Model Context Protocol (MCP) server for accessing [GEO (Gene Expression Omnibus)](https://www.ncbi.nlm.nih.gov/geo/) data through NCBI E-Utils API.
The tool will enable you to search for GEO datasets, series, samples, platforms, and profiles for your LLM.
Tested with Claude Desktop, chatGPT has no out of the box support for this tool yet.
Claude will automatically use the tools if it fits the context.

## Quick Install (pip)

install from pip
```bash
pip install geo-bio-mcp
```
install from source
```bash
# Clone the repo (if not already)
git clone <repo-url>
cd GEO_MCP
pip install -e .
```

## Configuration

Run init to create a config file
```bash
geo-bio-mcp --init
```

This will create a config file at `~/.geo-bio-mcp/config.json` (auto-created on first run if missing).
This file will contain the following:
```json
{
    "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
    "email": "your_email@example.com",
    "api_key": "YOUR_API_KEY"
}
```

It will also print out a configuration template for your claude desktop configuration file.

- `email` is required by NCBI.
- `api_key` is optional but recommended for higher rate limits ([get one here](https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/)).

## Running the Server

- **MCP stdio mode:**
  ```bash
  geo-bio-mcp
  ```
- **HTTP mode:**
  ```bash
  geo-bio-mcp --http --port 8001
  ```

## Claude Desktop Integration

### Common Issue: `spawn geo-bio-mcp ENOENT`

This error means Claude Desktop cannot find the `geo-bio-mcp` command. This is usually a PATH issue.

### Solution
1. **Find the full path to the executable:**
   ```bash
   which geo-bio-mcp
   ```
   Example output: `/Users/youruser/miniforge3/bin/geo-bio-mcp`

2. **Update your Claude config:**
   Instead of just `"geo-bio-mcp"`, use the full path:
   ```json
   {
     "mcpServers": {
       "geo-mcp": {
         "command": "/Users/youruser/miniforge3/bin/geo-bio-mcp",
         "env": {
           "CONFIG_PATH": "/Users/youruser/.geo-mcp/config.json"
         }
       }
     }
   }
   ```

3. **(Optional) Use a Conda Environment:**
   - Activate your conda env and run `which geo-bio-mcp` to get the correct path.
   - Use that path in your Claude config as above.

4. **Restart Claude Desktop** after updating the config.

---

## Troubleshooting
- If you see `command not found: geo-bio-mcp`, make sure you installed with the correct Python/conda environment and that its `bin` directory is in your PATH.
- If the config file is missing, it will be auto-created on first run, or you can copy the template from `geo_mcp_server/config_template.json`.

---

## Usage

### MCP Server (stdio mode)
For use with MCP clients like Claude Desktop:

```bash
cd geo_mcp_server
python main.py --mode stdio
```

### HTTP Server (localhost:8000)
For HTTP API access:

```bash
# Option 1: Using the main script
cd geo_mcp_server
python main.py --mode http --host localhost --port 8000

# Option 2: Using the convenience script
python run_server.py
```

### HTTP API Endpoints

Once the HTTP server is running on localhost:8000, you can access:

- **Root**: `GET /` - Server status
- **Health Check**: `GET /health` - Health check endpoint
- **List Tools**: `GET /tools` - List all available tools
- **Call Tool**: `POST /tools/call` - Execute a tool with arguments
- **API Documentation**: `GET /docs` - Interactive API documentation (Swagger UI)

### Example HTTP API Usage

```bash
# List available tools
curl http://localhost:8000/tools

# Search GEO Profiles
curl -X POST http://localhost:8000/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "search_geo_profiles",
    "arguments": {
      "term": "cancer",
      "retmax": 5
    }
  }'

# Search GEO Datasets
curl -X POST http://localhost:8000/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "search_geo_datasets", 
    "arguments": {
      "term": "breast cancer",
      "retmax": 10
    }
  }'
```

## Available Tools

This MCP server provides access to all major GEO databases through the following tools:

### Search Tools

- **`search_geo_profiles`** - Search gene expression profiles across different biological contexts
  - *Example searches*: "cancer", "breast cancer", "p53", "apoptosis"
  
- **`search_geo_datasets`** - Search curated gene expression datasets
  - *Example searches*: "diabetes", "Alzheimer's disease", "drug response", "tissue specific"
  
- **`search_geo_series`** - Search original submitter-supplied gene expression series
  - *Example searches*: "GSE12345", "microarray", "RNA-seq", "time course"
  
- **`search_geo_samples`** - Search individual gene expression samples
  - *Example searches*: "GSM123456", "human", "mouse", "tumor", "normal"
  
- **`search_geo_platforms`** - Search microarray platform definitions
  - *Example searches*: "Affymetrix", "Illumina", "Agilent", "GPL96"

### Search Parameters

Each tool accepts:
- **`term`** (required): Search term or query string
- **`retmax`** (optional, default: 20): Maximum number of results to return

### Example usage
For now just chat with claude desktop and it will use the tools automatically if it fits the context.

**User:** find a small brain dataset  

**Assistant:** I'll help you find a small brain dataset from the GEO database. Let me search for brain-related datasets with a maximum of one result.  

**Assistant (system):** *search_geo_datasets*  

**Assistant:** I found a brain-related dataset for you:

- **Dataset:** GSE290848  
- **Title:** Maternal Stress Triggers Early-Life Eczema via Fetal Mast Cell Reprogramming [10x Genomics Multiome ATAC + Gene Expression]  
- **Species:** Mouse (*Mus musculus*)  
- **Samples:** 8  
- **Data type:** ATAC-seq & gene expression (10x Genomics Multiome)  
- **Publication date:** 21 Jun 2025  

This small dataset explores how prenatal stress affects neuro-immune circuits and mast-cell development.  

Would you like me to download this dataset or search for others?

---

**User:** download GSE290848  

**Assistant:** I'll download the GSE290848 dataset for you.  

**Assistant (system):** *download_geo_data*  

**Assistant:** Download complete.  

**Downloaded files**

- `GSE290848_family.soft.gz` — series, platform & sample info  
- `GSE290848_metadata.xml` — detailed study metadata  

**Location:** `/Users/matthiasflo/Documents/2025/GEO_MCP/geo_mcp_server/downloads/gse/GSE290848`  
**Total size:** 0.01 MB  

The dataset is ready for analysis. Let me know if you’d like to explore it further.