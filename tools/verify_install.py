"""Smoke-test the standalone viewer over its stdio MCP transport."""

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def verify() -> None:
    """Check discovery, the browser resource, and a read-only map preview."""
    root = Path(__file__).resolve().parents[1]
    workspace = Path(os.environ["LOENN_MCP_WORKSPACE"]).resolve(strict=True)
    maps = sorted((workspace / "Maps").rglob("*.bin"))
    if not maps:
        raise RuntimeError("The selected mod has no .bin map under Maps/.")
    map_file = maps[0]
    relative_map = map_file.relative_to(workspace).as_posix()
    source_hash = hashlib.sha256(map_file.read_bytes()).hexdigest()
    transport = StdioTransport(
        command=sys.executable,
        args=[str(root / "run_server.py")],
        env=dict(os.environ),
        cwd=str(root),
    )
    async with Client(transport, timeout=120) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools}
        required = {
            "render_map_overview",
            "render_room_preview",
            "render_interactive_map",
            "inspect_gameplay_map",
        }
        if not required <= names:
            raise RuntimeError(
                f"Missing viewer tools: {sorted(required - names)}"
            )
        browser_uri = "ui://celeste/room-browser-v2.html"
        resources = await client.list_resources()
        if browser_uri not in {str(resource.uri) for resource in resources}:
            raise RuntimeError("The room-browser MCP App resource is missing.")
        preview = await client.call_tool(
            "render_map_overview", {"map_path": relative_map}
        )
        if preview.is_error or not any(
            content.type == "image" for content in preview.content
        ):
            raise RuntimeError("The read-only PNG preview failed.")
        await client.read_resource(browser_uri)
    if hashlib.sha256(map_file.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError(
            "The source map changed during read-only verification."
        )
    print(
        json.dumps(
            {
                "status": "passed",
                "tool_count": len(tools),
                "map": relative_map,
                "browser_resource": browser_uri,
                "source_sha256": source_hash,
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(verify())
