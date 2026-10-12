"""Compose an overview and room images into offline browser delivery variants."""

import json
from pathlib import Path
from uuid import uuid4

from .gallery_data import write_room_images
from .map_source import hash_file, resolve_map_source, validate_preview_output
from .overview import render_overview
from .progression import order_rooms
from .room_view import render_room
from .serialization import encode_image, encode_script_json
from .viewer import cb, extract_layout

ASSETS = Path(__file__).parent / "assets"
INLINE_FRAGMENT_LIMIT = 1_000_000


def make_gallery_fragment(rooms: list[dict], instance: str) -> str:
    """Embed page data and the shared controller with no external requests."""
    markup = (ASSETS / "room-gallery.html").read_text(encoding="utf-8")
    controller = (ASSETS / "room-gallery.js").read_text(encoding="utf-8")
    fragment = markup.replace(
        "<!-- GALLERY_SCRIPT -->", "<script>" + controller + "</script>"
    )
    return fragment.replace(
        "__ROOM_DATA__", encode_script_json(rooms)
    ).replace("__INSTANCE__", instance)


def image_url(
    png: bytes, compact: bool = False, full_size: bool = False
) -> str:
    """Keep the existing encoding API while delegating to named delivery modes."""
    encoding = "png"
    if compact:
        encoding = "lossless_webp" if full_size else "inline_webp"
    return encode_image(png, encoding)


def wrap_gallery(fragment: str) -> str:
    """Place a gallery inside the shared standalone dark-theme document."""
    shell = (ASSETS / "gallery-shell.html").read_text(encoding="utf-8")
    return shell.replace("<!-- GALLERY -->", fragment)


def write_gallery_documents(
    destination: Path,
    full_pages: list[dict],
    compact_pages: list[dict],
    source_hash: str,
) -> dict:
    """Write native browser data and a compact inline fallback when it fits.

    The source hash and page schema remain the MCP App delivery contract.
    Compact images are confined to the optional inline fallback.
    """
    instance = "rooms-" + uuid4().hex[:12]
    html_path = destination / "index.html"
    html_path.write_text(
        wrap_gallery(make_gallery_fragment(full_pages, instance)),
        encoding="utf-8",
    )
    data_path = destination / "gallery-data.json"
    payload = {
        "schema_version": 1,
        "source_hash": source_hash,
        "pages": full_pages,
    }
    data_path.write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )
    result = {"gallery_data_path": str(data_path), "html_path": str(html_path)}
    compact_fragment = make_gallery_fragment(compact_pages, instance)
    if len(compact_fragment.encode("utf-8")) < INLINE_FRAGMENT_LIMIT:
        fragment_path = destination / "room-picker.html"
        fragment_path.write_text(compact_fragment, encoding="utf-8")
        result["visualization"] = (
            "visualize" + json.dumps({"path": str(fragment_path)}) + ""
        )
        result["fragment_path"] = str(fragment_path)
    else:
        result["inline_limit_note"] = (
            "All rooms generated; compact gallery exceeds the inline size limit. Use the standalone gallery."
        )
    return result


def render_room_gallery(
    workspace: Path, output_dir: Path, map_path: str = "", source: str = "mod"
) -> dict:
    """Render every room once and write a new overview and offline gallery.

    Output stays outside Celeste and uses a unique directory. The source is
    checked before any rendered files are written. Native galleries retain
    original pixels; only the compact inline fallback downsamples room images.
    Returns the existing MCP manifest without changing source maps.
    """
    path = resolve_map_source(workspace, map_path, source)
    output_dir = output_dir.resolve()
    validate_preview_output(workspace, output_dir)
    source_hash = hash_file(path)
    layout = extract_layout(cb.read_map(path), path.stem)
    ordered_rooms, order_metadata = order_rooms(layout, source)
    rendered_rooms = [
        render_room(layout, room["name"], source_hash)
        for room in ordered_rooms
    ]
    overview_png, overview_metadata = render_overview(layout, source_hash)
    if hash_file(path) != source_hash:
        raise RuntimeError(
            "Map changed while rendering; request another gallery."
        )

    destination = output_dir / f"room-gallery-{uuid4().hex[:12]}"
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "overview.png").write_bytes(overview_png)
    (destination / "overview.json").write_text(
        json.dumps(overview_metadata, indent=2), encoding="utf-8"
    )
    room_data = write_room_images(destination, rendered_rooms)
    overview_page = {
        "name": "Whole map",
        "kind": "overview",
        "size": overview_metadata["image_size"],
        "regions": overview_metadata["room_bounds"],
        "image": encode_image(overview_png, "lossless_webp"),
    }
    documents = write_gallery_documents(
        destination,
        [overview_page, *room_data.full_pages],
        [overview_page, *room_data.compact_pages],
        source_hash,
    )
    result = {
        "source": str(path),
        "map_sha256": source_hash,
        "room_count": len(room_data.manifest),
        "rooms": room_data.manifest,
        "page_count": len(room_data.manifest) + 1,
        "room_order": order_metadata,
        "overview_room_click_navigation": True,
        "overview_path": str(destination / "overview.png"),
        **documents,
    }
    (destination / "manifest.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result
