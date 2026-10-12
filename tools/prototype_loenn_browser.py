"""Prototype Loenn's generated map as the entry page for the room browser.

Run from the repository with the existing viewer Python environment. This
development tool does not register an MCP server or replace the shipped viewer.
All output, including a source snapshot, goes outside the Celeste installation.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from celeste_gameplay_viewer.gallery_data import write_room_images
from celeste_gameplay_viewer.map_source import resolve_map_source
from celeste_gameplay_viewer.map_source import (
    validate_preview_output as validate_output,
)
from celeste_gameplay_viewer.progression import order_rooms
from celeste_gameplay_viewer.room_gallery import (
    make_gallery_fragment,
    wrap_gallery,
)
from celeste_gameplay_viewer.room_view import render_room
from celeste_gameplay_viewer.serialization import (
    encode_script_json as script_json,
)
from celeste_gameplay_viewer.viewer import cb, extract_layout

ASSETS = Path(__file__).with_name("prototype-assets")


def connect_loenn_document(
    document: str, room_names: list[str], channel: str
) -> str:
    """Add an isolated click bridge to generated loenn-mcp 5.2 HTML.

    Room indices refer to the unfiltered source order, never the shortened map
    labels. Raises ValueError if the generated structure does not match that
    order. The upstream source remains an independently installed dependency.
    """
    indices = re.findall(r'data-idx="(\d+)"', document)
    if indices != [str(index) for index in range(len(room_names))]:
        raise ValueError(
            "Loenn room targets do not match the source room order."
        )
    if len(set(room_names)) != len(room_names):
        raise ValueError(
            "Duplicate room names cannot identify a unique image."
        )

    # v5.2 applies its initial transform before the minimap context exists.
    # Defer only that first call so the generated page can finish initializing.
    initial_fit = "fitToWindow(); apply();\n\n//"
    if document.count(initial_fit) != 1:
        raise ValueError(
            "Unsupported Loenn initialization; review the adapter."
        )
    document = document.replace(
        initial_fit,
        "requestAnimationFrame(() => { fitToWindow(); apply(); });\n\n//",
        1,
    )
    bridge = (ASSETS / "loenn-navigation.js").read_text(encoding="utf-8")
    bridge = bridge.replace("__ROOM_NAMES__", script_json(room_names))
    bridge = bridge.replace("__CHANNEL__", script_json(channel))
    security = (
        '<meta http-equiv="Content-Security-Policy" content="'
        "default-src 'none'; script-src 'unsafe-inline'; "
        "style-src 'unsafe-inline'; img-src data:; connect-src 'none'; "
        "base-uri 'none'; form-action 'none'\">"
    )
    document = document.replace("<head>", "<head>" + security, 1)
    return document.replace(
        "</body>", "<script>" + bridge + "</script></body>", 1
    )


def make_prototype_fragment(
    document: str, pages: list[dict], channel: str
) -> str:
    """Compose upstream HTML and the existing gallery without changing either UI."""
    template = (ASSETS / "loenn-browser.html").read_text(encoding="utf-8")
    instance = "loenn-browser-" + channel
    gallery = make_gallery_fragment(pages, instance + "-rooms")
    return (
        template.replace("__GALLERY__", gallery)
        .replace("__MAP_DOCUMENT__", script_json(document))
        .replace("__CHANNEL__", script_json(channel))
        .replace("__INSTANCE__", instance)
    )


def render_loenn_map(snapshot_root: Path, map_name: str) -> str:
    """Generate upstream HTML in the isolated snapshot workspace.

    Loenn binds its workspace when imported. A child process prevents that
    setting from leaking into the viewer and confines generated files to output.
    Raises on a rendering failure or timeout; never receives the original map.
    """
    # Use a separate process because Loenn binds its workspace on import.
    # A disposable snapshot keeps its output and path checks away from the game.
    environment = dict(os.environ, LOENN_MCP_WORKSPACE=str(snapshot_root))
    code = (
        "from loenn_mcp.server import render_map_html\n"
        f"print(render_map_html({map_name!r}, output_file='loenn-map.html'))\n"
    )
    subprocess.run(
        [sys.executable, "-X", "utf8", "-"],
        input=code,
        text=True,
        encoding="utf-8",
        env=environment,
        cwd=snapshot_root,
        capture_output=True,
        check=True,
        timeout=60,
    )
    return (snapshot_root / "loenn-map.html").read_text(encoding="utf-8")


def build_prototype(
    workspace: Path, output: Path, map_path: str, source: str = "vanilla"
) -> dict:
    """Render a read-only snapshot through Loenn and the existing room renderer.

    Creates a unique output directory. Raises on unsupported dependencies,
    source changes, rendering failures, or ambiguous room navigation.
    """
    dependency_version = version("loenn-mcp")
    if dependency_version != "5.2.0":
        raise ValueError("This prototype adapter requires loenn-mcp 5.2.0.")
    validate_output(workspace, output)
    source_path = resolve_map_source(workspace, map_path, source)
    source_bytes = source_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / ("loenn-browser-" + uuid4().hex[:12])
    destination.mkdir(exist_ok=False)
    snapshot_root = destination / "source-snapshot"
    snapshot_root.mkdir(exist_ok=False)
    snapshot = snapshot_root / source_path.name
    snapshot.write_bytes(source_bytes)
    map_data = cb.read_map(snapshot)
    room_names = [room["name"] for room in cb.get_rooms(map_data)]
    if not room_names or len(set(room_names)) != len(room_names):
        raise ValueError("The prototype requires uniquely named rooms.")

    loenn_document = render_loenn_map(snapshot_root, source_path.name)
    channel = uuid4().hex
    connected_document = connect_loenn_document(
        loenn_document, room_names, channel
    )
    (destination / "loenn-navigation.html").write_text(
        connected_document, encoding="utf-8"
    )
    layout = extract_layout(map_data, source_path.stem)
    ordered_rooms, order_metadata = order_rooms(layout, source)
    with BytesIO() as stream:
        Image.new("RGBA", (1, 1)).save(stream, "PNG")
        placeholder = "data:image/png;base64," + base64.b64encode(
            stream.getvalue()
        ).decode("ascii")
    # Page zero remains the existing gallery's return control. The Loenn frame
    # is displayed there; no custom whole-map renderer is invoked.
    full_pages = [
        {
            "name": "Whole map",
            "kind": "overview",
            "image": placeholder,
            "size": [1, 1],
            "regions": [],
        }
    ]
    compact_pages = [full_pages[0]]
    rendered_rooms = [
        render_room(layout, room["name"], source_hash)
        for room in ordered_rooms
    ]
    room_data = write_room_images(destination, rendered_rooms)
    full_pages.extend(room_data.full_pages)
    compact_pages.extend(room_data.compact_pages)
    room_manifest = [
        {"room": entry["room"], "png_path": entry["png_path"]}
        for entry in room_data.manifest
    ]
    fragment = make_prototype_fragment(connected_document, full_pages, channel)
    (destination / "index.html").write_text(
        wrap_gallery(fragment), encoding="utf-8"
    )
    compact_fragment = make_prototype_fragment(
        connected_document, compact_pages, channel
    )
    fragment_path = destination / "loenn-room-browser.html"
    fragment_path.write_text(compact_fragment, encoding="utf-8")
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError(
            "Source changed while rendering; generate a fresh prototype."
        )
    manifest = {
        "source": str(source_path),
        "map_sha256": source_hash,
        "source_unchanged": True,
        "loenn_version": dependency_version,
        "room_count": len(room_manifest),
        "rooms": room_manifest,
        "room_order": order_metadata,
        "loenn_room_names": room_names,
        "html_path": str(destination / "index.html"),
        "fragment_path": str(fragment_path),
        "fragment_bytes": len(compact_fragment.encode("utf-8")),
        "prototype_only": True,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--map", required=True)
    parser.add_argument(
        "--source", choices=("mod", "vanilla"), default="vanilla"
    )
    arguments = parser.parse_args()
    result = build_prototype(
        arguments.workspace, arguments.output, arguments.map, arguments.source
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"rooms", "loenn_room_names"}
            },
            indent=2,
        )
    )
