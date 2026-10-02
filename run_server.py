"""Launch the installed viewer over stdio for Codex and other MCP clients."""

from celeste_gameplay_viewer.server import mcp


if __name__ == "__main__":
    mcp.run()
