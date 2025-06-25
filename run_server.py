#!/usr/bin/env python3
"""Script to run the GEO MCP HTTP server from the correct directory."""
import os
import sys
from pathlib import Path

# Change to the geo_mcp_server directory
server_dir = Path(__file__).parent / "geo_mcp_server"
os.chdir(server_dir)

# Add the server directory to Python path
sys.path.insert(0, str(server_dir))

# Import and run the server
from mcp_http_server import main
import asyncio

if __name__ == "__main__":
    print(f"Starting GEO MCP HTTP server from: {server_dir}")
    asyncio.run(main()) 