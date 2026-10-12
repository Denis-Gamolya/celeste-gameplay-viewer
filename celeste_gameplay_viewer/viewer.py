"""Render Celeste gameplay layouts without changing source maps.

Coordinates and dimensions use game pixels; solid tiles are eight pixels wide.
The CLI and MCP server share this module and its deterministic extraction rules.
"""

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from uuid import uuid4

from loenn_mcp import celeste_bin as cb

from .map_source import resolve_map as resolve_map
from .serialization import encode_script_json

ASSETS = Path(__file__).parent / "assets"
VISUAL_ENTITIES = frozenset({"lamp"})
VISUAL_TRIGGERS = frozenset(
    {
        "bloomFadeTrigger",
        "colorGradeTrigger",
        "lightFadeTrigger",
    }
)
GAMEPLAY_TRIGGERS = frozenset({"windAttackTrigger", "windTrigger"})
SUPPORTED_ENTITIES = frozenset(
    {
        "player",
        "strawberry",
        "spinner",
        "booster",
        "refill",
        "cloud",
        "moveBlock",
        "jumpThru",
        "badelineBoost",
    }
)


def children(element: dict, section_name: str) -> list[dict]:
    """Return the contents of a map section, or an empty list if absent."""
    section = cb.find_child(element, section_name)
    return section.get("__children", []) if section else []


def extract_layout(map_data: dict, title: str) -> dict:
    """Extract tile grids, gameplay objects, nodes, and trigger rectangles.

    Known decorative content is excluded. Unclassified triggers and unsupported
    entities remain visible, with their type names reported in warnings.
    """
    rooms = []
    warnings = set()
    excluded_entities = Counter()
    excluded_triggers = Counter()
    for room in cb.get_rooms(map_data):
        width = int(room.get("width", 0))
        height = int(room.get("height", 0))
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid tile dimensions in {room.get('name')}.")
        solids = cb.find_child(room, "solids") or {}
        # Blank rows and omitted trailing air are meaningful in Celeste maps.
        rows = solids.get("innerText", "").splitlines()
        # Vanilla rooms can end with partial tiles. Keep the actual bounds and
        # retain the final tile row or column rather than rejecting the room.
        columns = (width + 7) // 8
        row_count = (height + 7) // 8
        if len(rows) > row_count or any(len(row) > columns for row in rows):
            raise ValueError(
                f"Tiles exceed room bounds in {room.get('name')}."
            )
        rows = [row.ljust(columns, "0") for row in rows]
        rows += ["0" * columns] * (row_count - len(rows))
        entities = []
        for entity in children(room, "entities"):
            kind = entity["__name"]
            if kind in VISUAL_ENTITIES:
                excluded_entities[kind] += 1
                continue
            if kind not in SUPPORTED_ENTITIES:
                warnings.add(f"Generic marker for entity: {kind}")
            entities.append(
                {
                    "id": entity.get("id"),
                    "type": kind,
                    "x": entity.get("x", 0),
                    "y": entity.get("y", 0),
                    "w": entity.get("width", 0),
                    "h": entity.get("height", 0),
                    "red": entity.get("red", False),
                    "twoDash": entity.get("twoDash", False),
                    "direction": entity.get("direction"),
                    "nodes": [
                        [node.get("x", 0), node.get("y", 0)]
                        for node in entity.get("__children", [])
                        if node.get("__name") == "node"
                    ],
                    "properties": {
                        key: value
                        for key, value in entity.items()
                        if key not in {"__name", "__children"}
                    },
                }
            )
        triggers = []
        for trigger in children(room, "triggers"):
            kind = trigger["__name"]
            if kind in VISUAL_TRIGGERS:
                excluded_triggers[kind] += 1
                continue
            known = kind in GAMEPLAY_TRIGGERS
            if not known:
                warnings.add(f"Trigger classification unverified: {kind}")
            triggers.append(
                {
                    "id": trigger.get("id"),
                    "type": kind,
                    "x": trigger.get("x", 0),
                    "y": trigger.get("y", 0),
                    "w": trigger.get("width", 0),
                    "h": trigger.get("height", 0),
                    "verified": known,
                    "nodes": [
                        [node.get("x", 0), node.get("y", 0)]
                        for node in trigger.get("__children", [])
                        if node.get("__name") == "node"
                    ],
                    "properties": {
                        key: value
                        for key, value in trigger.items()
                        if key not in {"__name", "__children"}
                    },
                }
            )
        rooms.append(
            {
                "name": room.get("name", "Unnamed"),
                "x": room.get("x", 0),
                "y": room.get("y", 0),
                "w": width,
                "h": height,
                "tiles": rows,
                "entities": entities,
                "triggers": triggers,
            }
        )
    if not rooms:
        raise ValueError("The map has no rooms.")
    return {
        "title": title,
        "rooms": rooms,
        "warnings": sorted(warnings),
        "excluded_entities": dict(excluded_entities),
        "excluded_triggers": dict(excluded_triggers),
    }


def make_fragment(layout: dict, instance_id: str) -> str:
    """Embed map data safely into the local, self-contained HTML template."""
    payload = encode_script_json(layout)
    template = (ASSETS / "layout.html").read_text(encoding="utf-8")
    template = template.replace("__INSTANCE__", instance_id)
    fragment = template.replace("__GAMEPLAY_DATA__", payload)
    if len(fragment.encode("utf-8")) >= 1_000_000:
        raise ValueError("Map preview exceeds the inline size limit of 1 MB.")
    return fragment


def render_map(workspace: Path, output_dir: Path, map_path: str = "") -> dict:
    """Read a map and write unique HTML, inline HTML, and JSON output files.

    Source maps are never written. Outputs must be outside the mod workspace.
    Returns file paths, an inline display reference, counts, and limitations.
    """
    workspace = workspace.resolve(strict=True)
    source = resolve_map(workspace, map_path)
    output_dir = output_dir.resolve()
    if output_dir.is_relative_to(workspace):
        raise ValueError("Output directory must be outside the map workspace.")
    digest_before = hashlib.sha256(source.read_bytes()).hexdigest()
    layout = extract_layout(cb.read_map(source), source.stem)
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest_before:
        raise RuntimeError("Map changed while reading; render it again.")
    identifier = uuid4().hex[:12]
    slug = re.sub(r"[^a-z0-9]+", "-", source.stem.lower()).strip("-") or "map"
    base = f"{slug}-{identifier}"
    fragment = make_fragment(layout, identifier)
    wrapper = (ASSETS / "standalone.html").read_text(encoding="utf-8")
    standalone = wrapper.replace("<!-- FRAGMENT -->", fragment)
    output_dir.mkdir(parents=True, exist_ok=True)
    contents = {
        "fragment_path": (f"{base}.fragment.html", fragment),
        "html_path": (f"{base}.html", standalone),
        "data_path": (f"{base}.json", json.dumps(layout, indent=2)),
    }
    result = {}
    for key, (filename, content) in contents.items():
        destination = output_dir / filename
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(content)
        result[key] = destination.as_posix()
    counts = Counter(
        entity["type"]
        for room in layout["rooms"]
        for entity in room["entities"]
    )
    result.update(
        {
            "source": source.as_posix(),
            "source_sha256": digest_before,
            "room_count": len(layout["rooms"]),
            "entities": dict(counts),
            "trigger_count": sum(
                len(room["triggers"]) for room in layout["rooms"]
            ),
            "warnings": layout["warnings"],
            "note": "Positions and solid tiles are exact; object symbols are schematic, not collision hitboxes.",
            "visualization": "visualize"
            + json.dumps({"path": result["fragment_path"]})
            + "",
        }
    )
    return result


def main() -> None:
    """Parse command-line paths, render the map, and print a JSON result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map_path", nargs="?", default="")
    parser.add_argument(
        "--workspace", default=os.environ.get("LOENN_MCP_WORKSPACE")
    )
    parser.add_argument(
        "--output-dir", default=os.environ.get("CELESTE_VIEWER_OUTPUT")
    )
    args = parser.parse_args()
    if not args.workspace or not args.output_dir:
        parser.error(
            "Set --workspace and --output-dir, or their environment variables."
        )
    try:
        result = render_map(
            Path(args.workspace), Path(args.output_dir), args.map_path
        )
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"Render failed: {error}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
