"""Build all room images once and provide local browsing without more MCP calls."""

import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
from uuid import uuid4

from PIL import Image

from overview import render_overview, resolve_overview_source
from progression import order_rooms
from room_view import render_room
from viewer import cb, extract_layout

ASSETS = Path(__file__).parent / "assets"


def make_gallery_fragment(rooms: list[dict], instance: str) -> str:
    """Embed already-rendered images safely in a self-contained room selector."""
    data = json.dumps(rooms, separators=(",", ":"), ensure_ascii=True)
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return (ASSETS / "room-gallery.html").read_text(encoding="utf-8").replace(
        "__ROOM_DATA__", data).replace("__INSTANCE__", instance)


def image_url(png: bytes, compact: bool = False, full_size: bool = False) -> str:
    """Encode PNG, full-resolution lossless WebP, or a compact inline WebP."""
    if compact:
        with Image.open(BytesIO(png)) as image, BytesIO() as output:
            if not full_size:
                image = image.resize((736, round(image.height*736/image.width)), Image.Resampling.LANCZOS)
            image.save(output, "WEBP", quality=55, lossless=full_size, method=6)
            return "data:image/webp;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def wrap_gallery(fragment: str) -> str:
    """Wrap the shared room browser with standalone dark-theme styles."""
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Celeste rooms</title>
<style>body{margin:16px auto;padding:0 12px;max-width:980px;background:#101216;color:#eef2f7;font:16px system-ui}
.viz-controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center}button,select{font:inherit;padding:8px;background:#272e38;color:inherit;border:1px solid #8b98aa;border-radius:4px}label{display:flex;gap:8px;align-items:center}button:disabled{opacity:.4}.text-muted{color:#b7c1cd}</style><body>""" + fragment + "</body></html>"


def render_room_gallery(workspace: Path, output_dir: Path, map_path: str = "",
                        source: str = "mod") -> dict:
    """Write a new overview, every room PNG/JSON, and two gallery documents.

    Output must be outside the Celeste installation. Uses a unique directory,
    preserving earlier outputs and all source files. Returns a complete manifest
    and an inline visualization reference when the fragment fits the 1 MB limit.
    MCP and standalone galleries embed full-resolution lossless WebP images.
    Only the inline fallback downsamples rooms; browsing needs no network.
    """
    path = resolve_overview_source(workspace, map_path, source)
    output_dir = output_dir.resolve()
    forbidden = [workspace.resolve()]
    mods = next((parent for parent in workspace.resolve().parents if parent.name.lower() == "mods"), None)
    if mods:
        forbidden.append(mods.parent)
    if any(output_dir.is_relative_to(root) for root in forbidden):
        raise ValueError("Preview output must be outside the Celeste installation.")
    source_bytes = path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    layout = extract_layout(cb.read_map(path), path.stem)
    ordered, order_metadata = order_rooms(layout, source)
    rendered = [render_room(layout, room["name"], source_hash) for room in ordered]
    overview, overview_metadata = render_overview(layout, source_hash)
    if hashlib.sha256(path.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError("Map changed while rendering; request another gallery.")
    destination = output_dir / f"room-gallery-{uuid4().hex[:12]}"
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "overview.png").write_bytes(overview)
    (destination / "overview.json").write_text(json.dumps(overview_metadata, indent=2), encoding="utf-8")
    manifest = []
    navigation = {"size": overview_metadata["image_size"],
                  "regions": overview_metadata["room_bounds"]}
    full_rooms = [{"name": "Whole map", "kind": "overview", **navigation,
                   "image": image_url(overview, compact=True, full_size=True)}]
    compact_rooms = [{"name": "Whole map", "kind": "overview", **navigation,
                      "image": image_url(overview, compact=True, full_size=True)}]
    for index, (png, metadata) in enumerate(rendered):
        filename = f"room-{index+1:03}.png"
        (destination / filename).write_bytes(png)
        (destination / f"room-{index+1:03}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        manifest.append({"room": metadata["room"], "png_path": str(destination / filename),
                         "png_sha256": hashlib.sha256(png).hexdigest()})
        full_rooms.append({"name": metadata["room"], "kind": "room",
                           "image": image_url(png, compact=True, full_size=True)})
        compact_rooms.append({"name": metadata["room"], "kind": "room", "image": image_url(png, compact=True)})
    instance = "rooms-"+uuid4().hex[:12]
    full_fragment = make_gallery_fragment(full_rooms, instance)
    standalone = wrap_gallery(full_fragment)
    (destination / "index.html").write_text(standalone, encoding="utf-8")
    compact_fragment = make_gallery_fragment(compact_rooms, instance)
    data_path = destination / "gallery-data.json"
    data_path.write_text(json.dumps({"schema_version": 1,
                                    "source_hash": source_hash,
                                    "pages": full_rooms}, separators=(",", ":")),
                         encoding="utf-8")
    result = {"source": str(path), "map_sha256": source_hash,
              "room_count": len(manifest), "rooms": manifest,
              "page_count": len(manifest)+1, "room_order": order_metadata,
              "overview_room_click_navigation": True,
              "overview_path": str(destination / "overview.png"),
              "gallery_data_path": str(data_path),
              "html_path": str(destination / "index.html")}
    if len(compact_fragment.encode("utf-8")) < 1_000_000:
        fragment_path = destination / "room-picker.html"
        fragment_path.write_text(compact_fragment, encoding="utf-8")
        result["visualization"] = "visualize"+json.dumps({"path": str(fragment_path)})+""
        result["fragment_path"] = str(fragment_path)
    else:
        result["inline_limit_note"] = "All rooms generated; compact gallery exceeds the inline size limit. Use the standalone gallery."
    (destination / "manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
