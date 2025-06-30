import asyncio
import argparse
import os
import sys
import json
import shutil
from pathlib import Path

def setup_environment():
    """Set up the environment for the MCP server."""
    # Set the working directory to the script's directory
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)
    
    # Add the script directory to Python path to ensure local imports work
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    # Set CONFIG_PATH environment variable if not already set
    if not os.getenv("CONFIG_PATH"):
        config_dir = Path.home() / ".geo-mcp"
        config_path = config_dir / "config.json"
        os.environ["CONFIG_PATH"] = str(config_path)

    # Get the config path
    config_path = Path(os.getenv("CONFIG_PATH", str(Path.home() / ".geo-mcp" / "config.json")))
    
    # If config file doesn't exist, create it from template
    if not config_path.exists():
        template_path = script_dir / "config_template.json"
        if template_path.exists():
            # Create parent directories if they don't exist
            config_path.parent.mkdir(parents=True, exist_ok=True)
            # Copy template to config location
            shutil.copy2(template_path, config_path)
            print(f"Created default configuration file at: {config_path}", file=sys.stderr)
        else:
            print(f"Config file not found: {config_path}", file=sys.stderr)
            print(f"Template file not found: {template_path}", file=sys.stderr)
            print(f"Current working directory: {os.getcwd()}", file=sys.stderr)
            print(f"Available files in current directory: {list(Path('.').glob('*'))}", file=sys.stderr)
            sys.exit(1)

    # point any child-spawns at the venv python
    venv_bin = os.path.join(os.path.dirname(__file__), ".venv", "bin")
    os.environ["PATH"] = venv_bin + os.pathsep + os.environ.get("PATH", "")

def run_http_server(host: str = "localhost", port: int = 8001):
    """Run the HTTP server."""
    import uvicorn
    
    # Check if we're running as a package or as a script
    try:
        from .mcp_http_server import app
    except ImportError:
        # Running as script, use absolute import
        from mcp_http_server import app
    
    print(f"Starting HTTP server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)

async def run_mcp_server():
    """Run the MCP stdio server."""
    import mcp.server.stdio
    
    # Check if we're running as a package or as a script
    try:
        from .mcp_server import server
    except ImportError:
        # Running as script, use absolute import
        from mcp_server import server
    
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    except Exception as e:
        print(f"Error starting MCP server: {e}", file=sys.stderr)
        sys.exit(1)

def init_config(config_path: Path = None):
    """Initialize a new configuration file with user input."""
    if config_path is None:
        # Use the same logic as setup_environment for consistency
        if not os.getenv("CONFIG_PATH"):
            config_dir = Path.home() / ".geo-mcp"
            config_path = config_dir / "config.json"
        else:
            config_path = Path(os.getenv("CONFIG_PATH"))
    
    # Create parent directories if they don't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("GEO MCP Server Configuration Initialization")
    print("=" * 50)
    
    # Get user input
    email = input("Enter your email address (required for NCBI E-utilities): ").strip()
    if not email:
        print("Error: Email address is required!")
        sys.exit(1)
    
    api_key = input("Enter your NCBI API key (optional, press Enter to skip): ").strip()
    if not api_key:
        api_key = ""
        print("Note: Without an API key, you'll be limited to 3 requests/second")
    else:
        print("Note: With an API key, you'll have 10 requests/second limit")
    
    # Create config with user input
    config = {
        "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        "email": email,
        "api_key": api_key,
        "retmax": 20,
        "download_dir": "./downloads",
        "max_file_size_mb": 5000,
        "max_total_downloads_mb": 10000,
        "max_concurrent_downloads": 3,
        "download_timeout_seconds": 300,
        "allowed_download_paths": ["./downloads", "/tmp/geo_downloads"]
    }
    
    # Find absolute path to geo-mcp executable
    geo_mcp_path = shutil.which("geo-mcp") or "geo-mcp"
    if geo_mcp_path == "geo-mcp":
        print("WARNING: Could not find absolute path to geo-mcp executable. Falling back to 'geo-mcp'.", file=sys.stderr)
    
    # Write config file
    try:
        print(f"Creating config file at: {config_path}")
        print(f"config: {config}")
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"""\

            Configuration file created successfully at: {config_path}

            You can now run the server with:
            {geo_mcp_path} --http
            {geo_mcp_path}

            ==================================================
            CLAUDE DESKTOP CONFIGURATION
            ==================================================
            Add the following to your Claude Desktop configuration file:
            (Usually located at ~/.config/claude-desktop/config.json)

            WARNING: INSERT CORRECT PATH TO CONFIG FILE BELOW

            {{
            "mcpServers": {{
                "geo-mcp": {{
                "command": "{geo_mcp_path}",
                "env": {{
                    "CONFIG_PATH": "{config_path}"
                }}
                }}
            }}
            }}

            After adding this configuration:
            1. Restart Claude Desktop
            2. You should see GEO tools available in Claude
            """)
        return True
    except Exception as e:
        print(f"Error creating config file: {e}")
        return False

def main():
    """Main entry point for the GEO MCP server."""
    parser = argparse.ArgumentParser(
        description="GEO MCP Server - Access GEO data through Model Context Protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  geo-mcp --init                    # Initialize configuration file
  geo-mcp                          # Run MCP stdio server
  geo-mcp --http                    # Run HTTP server on localhost:8001
  geo-mcp --http --port 8080        # Run HTTP server on port 8080
  geo-mcp --http --host 0.0.0.0 --port 8080  # Run HTTP server on all interfaces
        """
    )
    
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize configuration file with interactive prompts"
    )
    
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run HTTP server instead of MCP stdio server"
    )
    
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host for HTTP server (default: localhost)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port for HTTP server (default: 8001)"
    )
    
    # Configuration options
    parser.add_argument(
        "--email",
        help="Email address for NCBI E-utilities (required)"
    )
    
    parser.add_argument(
        "--api-key",
        help="NCBI API key for higher rate limits (optional)"
    )
    
    parser.add_argument(
        "--retmax",
        type=int,
        default=20,
        help="Maximum number of search results to return (default: 20)"
    )
    
    parser.add_argument(
        "--download-dir",
        default="./downloads",
        help="Directory where downloads will be stored (default: ./downloads)"
    )
    
    parser.add_argument(
        "--max-file-size-mb",
        type=int,
        default=5000,
        help="Maximum size of individual files to download in MB (default: 5000)"
    )
    
    parser.add_argument(
        "--max-total-downloads-mb",
        type=int,
        default=10000,
        help="Maximum total size of all downloads in MB (default: 10000)"
    )
    
    parser.add_argument(
        "--max-concurrent-downloads",
        type=int,
        default=3,
        help="Maximum number of concurrent downloads (default: 3)"
    )
    
    parser.add_argument(
        "--download-timeout-seconds",
        type=int,
        default=300,
        help="Timeout for download requests in seconds (default: 300)"
    )
    
    parser.add_argument(
        "--allowed-download-paths",
        nargs="+",
        default=["./downloads", "/tmp/geo_downloads"],
        help="List of allowed download paths for security (default: ./downloads /tmp/geo_downloads)"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="geo-mcp 0.1.0"
    )
    
    args = parser.parse_args()
    
    # Handle init command first, before any environment setup
    if args.init:
        success = init_config()
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    
    # Set up environment only for non-init commands
    setup_environment()
    
    if args.http:
        # Run HTTP server
        run_http_server(args.host, args.port)
    else:
        # Run MCP stdio server
        asyncio.run(run_mcp_server())

if __name__ == "__main__":
    main()
