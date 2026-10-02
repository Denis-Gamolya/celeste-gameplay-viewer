"""Expose PNG overviews, optional HTML gameplay views, and an image probe."""

import os
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP
from fastmcp.tools import ToolResult

from .transport_probe import make_image_probe
from .overview import make_overview_result
from .room_view import make_room_result
from .room_gallery import render_room_gallery
from .viewer import render_map
from .findings import inspect_gameplay_map as inspect_map
from .mcp_app import RESOURCE_MIME, RESOURCE_URI, RESULT_SCHEMA, make_app_resource
from .mcp_app import render_interactive_map as render_app

mcp = FastMCP(
    "celeste-gameplay-viewer",
    instructions=(
        "Use render_map_overview for a whole-map PNG returned as image content "
        "with candidate connections and source hashes. Source maps are read-only. "
        "Use render_room_preview for on-demand individual room geometry and gameplay symbols. "
        "Use render_all_rooms to generate every room once and browse the resulting gallery. "
        "Use render_interactive_map to deliver that browser as an MCP App in compatible clients. "
        "Use inspect_gameplay_map for evidence-based saved-data findings and renderer coverage; "
        "review items and geometric connections do not establish playability. "
        "Show the image in chat; do not treat a local file path as image delivery. "
        "The optional render_gameplay_layout tool returns an HTML visualization "
        "reference for compatible clients and a standalone browser HTML path. "
        "test_image_delivery provides a tiny PNG for diagnosing client display."
    ),
)


@mcp.tool(annotations={
    "readOnlyHint": False, "destructiveHint": False,
    "idempotentHint": False, "openWorldHint": False,
})
def render_gameplay_layout(map_path: str = "") -> dict:
    """Render the latest Celeste map as a gameplay diagram with room zoom.

    Includes solid tiles, spawns, berries, entities, movement nodes, and triggers.
    Excludes decals, lamps, and known visual-only triggers. Unknown object types
    stay visible with generic markers; uncertain trigger types are reported.
    Writes uniquely named previews outside the mod folder; never edits maps.

    Args:
        map_path: Workspace-relative .bin path. Omit if Maps/ has one map.

    Returns:
        Inline visualization reference, browser HTML path, source hash, counts,
        and any unsupported entity or unclassified trigger warnings.
    """
    workspace = Path(os.environ["LOENN_MCP_WORKSPACE"])
    output_dir = Path(os.environ["CELESTE_VIEWER_OUTPUT"])
    return render_map(workspace, output_dir, map_path)


@mcp.tool(annotations={
    "readOnlyHint": True, "destructiveHint": False,
    "idempotentHint": True, "openWorldHint": False,
})
def test_image_delivery() -> ToolResult:
    """Return text and a tiny PNG to test whether chat displays MCP images.

    Takes no arguments and does not read or change maps. Ask the user to
    confirm seeing the P1-CELESTE image in their actual chat client before
    claiming successful end-to-end delivery. A local file or tool log is not
    proof of user-visible rendering.
    """
    return make_image_probe()


@mcp.tool(annotations={
    "readOnlyHint": True, "destructiveHint": False,
    "idempotentHint": True, "openWorldHint": False,
})
def render_map_overview(
    map_path: str = "", source: Literal["mod", "vanilla"] = "mod",
) -> ToolResult:
    """Return one high-resolution dark whole-map PNG as image content.

    Shows room geometry/names, candidate entrances/exits from touching air
    edges, compact spawns/checkpoints, berries, and other collectibles.
    Open the full-size image to zoom.
    Individual rooms are available through render_room_preview. Returns source hash
    and structured metadata; does not prove traversability. No writes.

    Args:
        map_path: For mod, path relative to the configured mod; omit for its
            single map. For vanilla, filename such as 1-ForsakenCity.bin.
        source: mod or vanilla; vanilla reads only Content/Maps in the same
            Celeste installation.
    """
    return make_overview_result(Path(os.environ["LOENN_MCP_WORKSPACE"]),
                                map_path, source)


@mcp.tool(annotations={
    "readOnlyHint": True, "destructiveHint": False,
    "idempotentHint": True, "openWorldHint": False,
})
def render_room_preview(
    room_name: str, map_path: str = "", source: Literal["mod", "vanilla"] = "mod",
) -> ToolResult:
    """Show one room's tiles, gameplay objects, saved nodes, and triggers as PNG.

    Room names match Lonn, e.g. lvl_11z; unambiguous IDs such as 11z also work.
    Source mod reads the configured mod; vanilla reads Content/Maps from the
    same installation and requires a filename, e.g. 1-ForsakenCity.bin.
    Known decorations and visual-only triggers are omitted. Unknown objects
    remain numbered and labeled. Symbols are schematic, not precise hitboxes.
    Returns image content, full object metadata, and source hash. No writes.
    """
    return make_room_result(Path(os.environ["LOENN_MCP_WORKSPACE"]),
                            room_name, map_path, source)


@mcp.tool(annotations={
    "readOnlyHint": False, "destructiveHint": False,
    "idempotentHint": False, "openWorldHint": False,
})
def render_all_rooms(map_path: str = "", source: Literal["mod", "vanilla"] = "mod") -> dict:
    """Generate all room PNGs, an overview, and a browsable room gallery.

    Reads source maps only. Writes uniquely named previews outside Celeste.
    Returns every room's path/hash, a standalone gallery, and a compact inline
    visualization reference when it fits. Room browsing makes no further calls.
    """
    return render_room_gallery(Path(os.environ["LOENN_MCP_WORKSPACE"]),
                               Path(os.environ["CELESTE_VIEWER_OUTPUT"]), map_path, source)


@mcp.tool(annotations={
    "readOnlyHint": True, "destructiveHint": False,
    "idempotentHint": True, "openWorldHint": False,
})
def inspect_gameplay_map(
    map_path: str = "", source: Literal["mod", "vanilla"] = "mod",
) -> dict:
    """Inspect duplicate names/IDs, overlapping rooms, node counts, and bounds.

    Returns review items and observations with saved room names, object IDs,
    local/world game-pixel coordinates, evidence, and source hash. Renderer
    coverage and undirected candidate connections are reported separately.
    No physics, spawn safety, or playability claim. Reads only; writes nothing.
    Uses the same mod/vanilla path rules as render_map_overview.
    """
    return inspect_map(Path(os.environ["LOENN_MCP_WORKSPACE"]), map_path, source)


@mcp.resource(RESOURCE_URI, mime_type=RESOURCE_MIME,
              app={"prefersBorder": False,
                   "csp": {"connectDomains": [], "resourceDomains": []}})
def room_browser_resource() -> str:
    """Shared room browser with no map-specific data or network dependencies."""
    return make_app_resource()


@mcp.tool(app={"resourceUri": RESOURCE_URI}, output_schema=RESULT_SCHEMA,
          annotations={"readOnlyHint": False, "destructiveHint": False,
                       "idempotentHint": False, "openWorldHint": False})
def render_interactive_map(
    map_path: str = "", source: Literal["mod", "vanilla"] = "mod",
) -> ToolResult:
    """Show the whole map and all rooms as an interactive MCP App.

    The overview is first; clicking a room opens its preview without opening
    the selector. Generates all images once and supplies them to the UI.
    Writes unique previews outside Celeste; never edits source maps. Clients
    without MCP Apps can use the returned inline or standalone gallery.
    Uses the same mod/vanilla input scope as the existing PNG tools.
    """
    return render_app(Path(os.environ["LOENN_MCP_WORKSPACE"]),
                      Path(os.environ["CELESTE_VIEWER_OUTPUT"]), map_path, source)


if __name__ == "__main__":
    mcp.run()
