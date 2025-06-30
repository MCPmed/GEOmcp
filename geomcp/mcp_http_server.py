#!/usr/bin/env python3
"""HTTP gateway for GEO-MCP on http://localhost:8001"""
import asyncio, os, sys
from pathlib import Path
from typing import Dict, Any, List
import json
from collections import deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
from .mcp_server import server

# Global event queue for SSE
event_queue = deque(maxlen=100)  # Keep last 100 events
connected_clients = set()

def publish_event(event_type: str, data: Any):
    """Publish an event to all connected SSE clients."""
    event = {
        "type": event_type,
        "data": data,
        "timestamp": asyncio.get_event_loop().time()
    }
    event_queue.append(event)
    # Notify all connected clients
    for client in connected_clients.copy():
        if not client.is_disconnected():
            client.put_nowait(event)


async def _get_tools() -> List[Any]:
    """Return the MCP tool-model list or raise."""
    try:
        # Import the handle_list_tools function directly
        from .mcp_server import handle_list_tools
        
        # Call the async function directly
        tools = await handle_list_tools()
        if isinstance(tools, list):
            return tools
    except Exception as e:
        print(f"Error getting tools: {e}", file=sys.stderr)
    
    # Fallback: try to access tools from server object
    for attr in ("tools", "_tools"):
        if hasattr(server, attr):
            tools = getattr(server, attr)
            if isinstance(tools, list):
                return tools
    
    try:
        maybe = server.list_tools()
        if isinstance(maybe, list):
            return maybe
    except TypeError:
        pass
    
    raise RuntimeError("Could not locate tool registry in mcp_server.server")


# Create the FastAPI app at module level
app = FastAPI(title="GEO MCP Server", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

class ToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any]

class ToolCallResponse(BaseModel):
    result: List[Dict[str, Any]]

@app.get("/")
async def root():
    return {"status": "healthy"}

@app.get("/tools", response_model=List[Dict[str, Any]])
async def list_tools():
    try:
        return [t.model_dump() for t in await _get_tools()]
    except Exception as e:
        raise HTTPException(500, f"Error listing tools: {e}")

@app.post("/tools/call", response_model=ToolCallResponse)
async def call_tool(req: ToolCallRequest):
    try:
        # Publish tool call start event
        publish_event("tool_call_start", {
            "tool": req.name,
            "arguments": req.arguments
        })
        
        # Import the handle_call_tool function directly
        from .mcp_server import handle_call_tool
        
        # Call the async function
        out = await handle_call_tool(req.name, req.arguments)
        result = [o.model_dump() for o in out]
        
        # Publish tool call completion event
        publish_event("tool_call_complete", {
            "tool": req.name,
            "arguments": req.arguments,
            "result": result
        })
        
        return ToolCallResponse(result=result)
    except ValueError as e:
        # Publish error event
        publish_event("tool_call_error", {
            "tool": req.name,
            "arguments": req.arguments,
            "error": str(e)
        })
        raise HTTPException(400, f"Invalid tool call: {e}")
    except Exception as e:
        # Publish error event
        publish_event("tool_call_error", {
            "tool": req.name,
            "arguments": req.arguments,
            "error": str(e)
        })
        raise HTTPException(500, f"Error calling tool: {e}")

@app.get("/health")
async def health():
    try:
        return {"status": "healthy", "tools_available": len(await _get_tools())}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/events")
async def events(request: Request):
    # Create a queue for this client
    client_queue = asyncio.Queue()
    connected_clients.add(client_queue)
    
    try:
        # Send initial connection event
        await client_queue.put({
            "type": "connection_established",
            "data": {"message": "Connected to GEO-MCP server"},
            "timestamp": asyncio.get_event_loop().time()
        })
        
        # Send recent events (last 10)
        recent_events = list(event_queue)[-10:]
        for event in recent_events:
            await client_queue.put(event)
        
        async def event_generator():
            while True:
                if await request.is_disconnected():
                    break
                
                try:
                    # Wait for new events with timeout
                    event = await asyncio.wait_for(client_queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat', 'data': {}, 'timestamp': asyncio.get_event_loop().time()})}\n\n"
                except Exception as e:
                    # Send error event
                    yield f"data: {json.dumps({'type': 'error', 'data': {'error': str(e)}, 'timestamp': asyncio.get_event_loop().time()})}\n\n"
                    break
        
        return StreamingResponse(event_generator(), media_type="text/event-stream")
    
    finally:
        # Clean up when client disconnects
        connected_clients.discard(client_queue)


async def main() -> None:
    os.chdir(Path(__file__).parent)
    os.environ.setdefault("CONFIG_PATH", str(Path("config.json")))

    print("Starting GEO-MCP HTTP server on http://localhost:8001")
    await uvicorn.Server(uvicorn.Config(app, host="localhost", port=8001, log_level="info")).serve()


if __name__ == "__main__":
    asyncio.run(main())