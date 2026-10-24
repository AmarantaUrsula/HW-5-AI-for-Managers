"""Starts the campus-customs MCP server over stdio. The agent runner and the FastAPI backend both use it."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

SERVER = Path(__file__).resolve().parent.parent / "mcp_server" / "server.py"


def make_mcp_client(approval_secret: str = "") -> Client:
    """Only the MCP server process gets the approval secret. Without one, every payment is refused."""
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    if approval_secret:
        env["HW5_APPROVAL_SECRET"] = approval_secret
    return Client(StdioTransport(command=sys.executable, args=[str(SERVER)], env=env))
