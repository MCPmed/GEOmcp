"""
GEO MCP Server - A Model Context Protocol (MCP) server for accessing GEO data.

This package provides tools to search and download data from the Gene Expression Omnibus (GEO)
through NCBI E-Utils API using the Model Context Protocol.
"""

__version__ = "0.1.0"
__author__ = "MCPmed Contributors"
__email__ = "matthias.flotho@ccb.uni-saarland.de"

from .main import main
from .geo_profiles import search_geo, search_geo_profiles, search_geo_datasets
from .geo_downloader import download_geo

__all__ = [
    "main",
    "search_geo",
    "search_geo_profiles", 
    "search_geo_datasets",
    "download_geo"
] 