"""Deliver the existing room browser through the MCP Apps resource protocol."""

import json
from pathlib import Path

from fastmcp.tools import ToolResult
from mcp.types import TextContent

from .room_gallery import ASSETS, make_gallery_fragment, render_room_gallery
from .room_gallery import wrap_gallery

RESOURCE_URI = "ui://celeste/room-browser-v2.html"
RESOURCE_MIME = "text/html;profile=mcp-app"
RESULT_SCHEMA = {
    "type": "object",
    "required": ["room_count", "page_count", "map_sha256", "html_path"],
    "properties": {
        "room_count": {"type": "integer"},
        "page_count": {"type": "integer"},
        "map_sha256": {"type": "string"},
        "html_path": {"type": "string"},
    },
    "additionalProperties": True,
}


def make_app_resource() -> str:
    """Return a data-free HTML resource; the host supplies each tool's images."""
    fragment = make_gallery_fragment([], "celeste-mcp-app")
    bridge = (ASSETS / "mcp-app-bridge.js").read_text(encoding="utf-8")
    return wrap_gallery(fragment + "<script>" + bridge + "</script>")


def render_interactive_map(workspace: Path, output_dir: Path,
                           map_path: str = "", source: str = "mod") -> ToolResult:
    """Generate one gallery and provide its embedded images in UI-only metadata.

    Creates uniquely named outputs outside Celeste, through the existing source
    restrictions. Keeps image data out of model-visible content. Clients without
    MCP Apps retain the existing inline/standalone gallery paths. Images are a
    snapshot; viewing rooms never reads or changes maps or calls more tools.
    """
    result = render_room_gallery(workspace, output_dir, map_path, source)
    payload = json.loads(Path(result["gallery_data_path"]).read_text(encoding="utf-8"))
    return ToolResult(
        content=[TextContent(type="text", text=(
            f"Room browser ready: whole map and {result['room_count']} rooms. "
            "Click a room to open it; Whole map returns to the overview. "
            f"Source SHA-256: {result['map_sha256']}."
        ))],
        structured_content=result,
        meta={"celesteGallery": payload},
    )
