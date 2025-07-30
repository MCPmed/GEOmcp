#!/usr/bin/env python3
"""
MCP Server for GEO (Gene Expression Omnibus) Data
Handles MCP protocol and tool definitions for accessing GEO data through NCBI E-Utils
"""

import json
import logging
import asyncio
from typing import Any, Dict, List
from mcp.server import Server
import mcp.types as types
from . import geo_profiles, geo_downloader

logger = logging.getLogger("geo-mcp-server")


class GEOMCPServer:
    """
    MCP Server implementation for GEO Data Access
    Handles MCP protocol and tool definitions for Gene Expression Omnibus
    """
    
    def __init__(self):
        self.server = Server("geo-mcp")
        self._setup_tools()
    
    def _setup_tools(self):
        """Register all available GEO tools"""
        
        # Universal GEO search tool
        @self.server.call_tool()
        async def search_geo(arguments: dict) -> list[types.TextContent]:
            """Search GEO for all types of records (GSE, GSM, GPL, GDS)"""
            term = arguments.get("term", "")
            retmax = arguments.get("retmax", 20)
            record_types = arguments.get("record_types")
            
            if not term:
                raise ValueError("term parameter is required")
            
            result = geo_profiles.search_geo(term, retmax, record_types)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        # GEO Profiles search
        @self.server.call_tool()
        async def search_geo_profiles(arguments: dict) -> list[types.TextContent]:
            """Search GEO Profiles database"""
            term = arguments.get("term", "")
            retmax = arguments.get("retmax", 20)
            
            if not term:
                raise ValueError("term parameter is required")
                
            result = geo_profiles.search_geo_profiles(term, retmax)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        # GEO Datasets search
        @self.server.call_tool()
        async def search_geo_datasets(arguments: dict) -> list[types.TextContent]:
            """Search GEO Datasets (GDS) specifically"""
            term = arguments.get("term", "")
            retmax = arguments.get("retmax", 20)
            
            if not term:
                raise ValueError("term parameter is required")
                
            result = geo_profiles.search_geo_datasets(term, retmax)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        # GEO Series search
        @self.server.call_tool()
        async def search_geo_series(arguments: dict) -> list[types.TextContent]:
            """Search GEO Series (GSE) specifically"""
            term = arguments.get("term", "")
            retmax = arguments.get("retmax", 20)
            
            if not term:
                raise ValueError("term parameter is required")
                
            result = geo_profiles.search_geo_series(term, retmax)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        # GEO Samples search
        @self.server.call_tool()
        async def search_geo_samples(arguments: dict) -> list[types.TextContent]:
            """Search GEO Samples (GSM) specifically"""
            term = arguments.get("term", "")
            retmax = arguments.get("retmax", 20)
            
            if not term:
                raise ValueError("term parameter is required")
                
            result = geo_profiles.search_geo_samples(term, retmax)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        # GEO Platforms search
        @self.server.call_tool()
        async def search_geo_platforms(arguments: dict) -> list[types.TextContent]:
            """Search GEO Platforms (GPL) specifically"""
            term = arguments.get("term", "")
            retmax = arguments.get("retmax", 20)
            
            if not term:
                raise ValueError("term parameter is required")
                
            result = geo_profiles.search_geo_platforms(term, retmax)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        # Download GEO data
        @self.server.call_tool()
        async def download_geo_data(arguments: dict) -> list[types.TextContent]:
            """Download GEO data files"""
            geo_id = arguments.get("geo_id", "")
            db_type = arguments.get("db_type", "gse")
            output_dir = arguments.get("output_dir")
            
            if not geo_id:
                raise ValueError("geo_id parameter is required")
                
            result = await geo_downloader.download_geo(geo_id, db_type, output_dir)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        # Get download status
        @self.server.call_tool()
        async def get_download_status(arguments: dict) -> list[types.TextContent]:
            """Check download status of a GEO dataset"""
            geo_id = arguments.get("geo_id", "")
            db_type = arguments.get("db_type", "gse")
            
            if not geo_id:
                raise ValueError("geo_id parameter is required")
                
            result = geo_downloader.get_download_status(geo_id, db_type)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        # List downloaded datasets
        @self.server.call_tool()
        async def list_downloaded_datasets(arguments: dict) -> list[types.TextContent]:
            """List all downloaded GEO datasets"""
            db_type = arguments.get("db_type")
            
            result = geo_downloader.list_downloaded_datasets(db_type)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        # Get download statistics
        @self.server.call_tool()
        async def get_download_stats(arguments: dict) -> list[types.TextContent]:
            """Get download statistics and limits"""
            result = geo_downloader.get_download_stats()
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        # Cleanup downloads
        @self.server.call_tool()
        async def cleanup_downloads_tool(arguments: dict) -> list[types.TextContent]:
            """Clean up downloaded files"""
            geo_id = arguments.get("geo_id")
            db_type = arguments.get("db_type")
            
            result = geo_downloader.cleanup_downloads(geo_id, db_type)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
    
    def get_server(self) -> Server:
        """Get the configured MCP server"""
        return self.server
    
    def get_tool_definitions(self) -> List[types.Tool]:
        """Get all tool definitions for the GEO MCP server"""
        return [
            # Universal GEO search
            types.Tool(
                name="search_geo",
                description="Search GEO for all types of records (GSE, GSM, GPL, GDS)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "term": {
                            "type": "string",
                            "description": "Search term (e.g., 'breast cancer', 'GSE12345', 'RNA-seq')"
                        },
                        "retmax": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 20)",
                            "default": 20
                        },
                        "record_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter for specific record types: GSE, GSM, GPL, GDS"
                        }
                    },
                    "required": ["term"]
                }
            ),
            
            # GEO Profiles search
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
                            "description": "Maximum number of results to return (default: 20)",
                            "default": 20
                        }
                    },
                    "required": ["term"]
                }
            ),
            
            # GEO Datasets search
            types.Tool(
                name="search_geo_datasets",
                description="Search GEO Datasets (GDS) - curated gene expression datasets",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "term": {
                            "type": "string",
                            "description": "Search term for GEO Datasets"
                        },
                        "retmax": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 20)",
                            "default": 20
                        }
                    },
                    "required": ["term"]
                }
            ),
            
            # GEO Series search
            types.Tool(
                name="search_geo_series",
                description="Search GEO Series (GSE) - complete experiments",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "term": {
                            "type": "string",
                            "description": "Search term for GEO Series"
                        },
                        "retmax": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 20)",
                            "default": 20
                        }
                    },
                    "required": ["term"]
                }
            ),
            
            # GEO Samples search
            types.Tool(
                name="search_geo_samples",
                description="Search GEO Samples (GSM) - individual samples",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "term": {
                            "type": "string",
                            "description": "Search term for GEO Samples"
                        },
                        "retmax": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 20)",
                            "default": 20
                        }
                    },
                    "required": ["term"]
                }
            ),
            
            # GEO Platforms search
            types.Tool(
                name="search_geo_platforms",
                description="Search GEO Platforms (GPL) - array/sequencing platforms",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "term": {
                            "type": "string",
                            "description": "Search term for GEO Platforms"
                        },
                        "retmax": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 20)",
                            "default": 20
                        }
                    },
                    "required": ["term"]
                }
            ),
            
            # Download tool
            types.Tool(
                name="download_geo_data",
                description="Download GEO data files (SOFT format)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "geo_id": {
                            "type": "string",
                            "description": "GEO accession ID (e.g., GSE12345, GSM789, GPL456, GDS123)"
                        },
                        "db_type": {
                            "type": "string",
                            "description": "Database type: gse, gsm, gpl, or gds (default: gse)",
                            "default": "gse"
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "Optional custom output directory"
                        }
                    },
                    "required": ["geo_id"]
                }
            ),
            
            # Download status
            types.Tool(
                name="get_download_status",
                description="Check if a GEO dataset has been downloaded",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "geo_id": {
                            "type": "string",
                            "description": "GEO accession ID"
                        },
                        "db_type": {
                            "type": "string",
                            "description": "Database type: gse, gsm, gpl, or gds (default: gse)",
                            "default": "gse"
                        }
                    },
                    "required": ["geo_id"]
                }
            ),
            
            # List downloads
            types.Tool(
                name="list_downloaded_datasets",
                description="List all downloaded GEO datasets",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "db_type": {
                            "type": "string",
                            "description": "Optional filter by database type: gse, gsm, gpl, or gds"
                        }
                    }
                }
            ),
            
            # Download stats
            types.Tool(
                name="get_download_stats",
                description="Get download statistics and limits",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            
            # Cleanup downloads
            types.Tool(
                name="cleanup_downloads_tool",
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
                            "description": "Optional database type filter for cleanup"
                        }
                    }
                }
            )
        ]


# Create the server instance
mcp_server = GEOMCPServer()
server = mcp_server.get_server()

# List tools for Claude Desktop integration
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Return the list of available tools"""
    return mcp_server.get_tool_definitions()

# Handle tool calls for HTTP server
async def handle_call_tool(name: str, arguments: dict):
    """Handle tool calls from HTTP server"""
    # Get the server's tool handlers
    server_instance = mcp_server.get_server()
    
    # Call the tool through the server
    from mcp.types import CallToolRequest
    request = CallToolRequest(
        method="tools/call",
        params={
            "name": name,
            "arguments": arguments
        }
    )
    
    # Simulate calling the tool
    if hasattr(server_instance, '_call_tool_handlers') and name in server_instance._call_tool_handlers:
        handler = server_instance._call_tool_handlers[name]
        return await handler(arguments)
    else:
        # Fallback: call functions directly
        if name == "search_geo":
            from . import geo_profiles
            result = geo_profiles.search_geo(
                arguments.get("term", ""), 
                arguments.get("retmax", 20), 
                arguments.get("record_types")
            )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        elif name == "search_geo_profiles":
            from . import geo_profiles
            result = geo_profiles.search_geo_profiles(
                arguments.get("term", ""), 
                arguments.get("retmax", 20)
            )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        elif name == "search_geo_datasets":
            from . import geo_profiles
            result = geo_profiles.search_geo_datasets(
                arguments.get("term", ""), 
                arguments.get("retmax", 20)
            )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        elif name == "search_geo_series":
            from . import geo_profiles
            result = geo_profiles.search_geo_series(
                arguments.get("term", ""), 
                arguments.get("retmax", 20)
            )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        elif name == "search_geo_samples":
            from . import geo_profiles
            result = geo_profiles.search_geo_samples(
                arguments.get("term", ""), 
                arguments.get("retmax", 20)
            )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        elif name == "search_geo_platforms":
            from . import geo_profiles
            result = geo_profiles.search_geo_platforms(
                arguments.get("term", ""), 
                arguments.get("retmax", 20)
            )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        elif name == "download_geo_data":
            from . import geo_downloader
            result = await geo_downloader.download_geo(
                arguments.get("geo_id", ""),
                arguments.get("db_type", "gse"),
                arguments.get("output_dir")
            )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        elif name == "get_download_status":
            from . import geo_downloader
            result = geo_downloader.get_download_status(
                arguments.get("geo_id", ""),
                arguments.get("db_type", "gse")
            )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        elif name == "list_downloaded_datasets":
            from . import geo_downloader
            result = geo_downloader.list_downloaded_datasets(
                arguments.get("db_type")
            )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        elif name == "get_download_stats":
            from . import geo_downloader
            result = geo_downloader.get_download_stats()
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        elif name == "cleanup_downloads_tool":
            from . import geo_downloader
            result = geo_downloader.cleanup_downloads(
                arguments.get("geo_id"),
                arguments.get("db_type")
            )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        else:
            raise ValueError(f"Unknown tool: {name}")