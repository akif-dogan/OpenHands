#!/bin/bash
# Install dependencies if missing, then run MarsAI MCP server
pip install -q fastmcp httpx 2>/dev/null
exec python "$(dirname "$0")/marsai_server.py"
