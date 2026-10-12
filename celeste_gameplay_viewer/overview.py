"""Deterministic room topology PNGs from the existing parsed Celeste layout.

World positions are game pixels, with eight pixels per tile. Connections are
geometric candidates only: dynamic entities, hazards, physics, transition
settings, and scripts are deliberately not interpreted here.
"""

import base64
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastmcp.tools import ToolResult
from mcp.types import ImageContent, TextContent
from PIL import ImageFont

from .map_geometry import OPPOSITE_SIDES
from .map_geometry import analyze_boundaries as analyze_boundaries
from .map_geometry import edge_openings as edge_openings
from .map_geometry import styled_edges as styled_edges
from .map_source import resolve_map_source as resolve_overview_source
from .raster import RasterCanvas
from .render_style import COLORS as COLORS
from .room_view import DECORATIVE, LEGEND, symbol_kind
from .sprites import load_sprite, object_sprite
from .viewer import cb, extract_layout

# Keep former imports valid while callers migrate to the shared geometry module.
OPPOSITE = OPPOSITE_SIDES

OTHER_COLLECTIBLES = {
    "cassette",
    "blackGem",
    "heartGem",
    "key",
    "summitgem",
    "refill",
    "birdForsakenCityGem",
}


def marker_kind(entity_type: str):
    """Classify known collectible anchors; scripted heart puzzles use their anchor."""
    if entity_type in {"strawberry", "goldenBerry"}:
        return "strawberry"
    if entity_type in OTHER_COLLECTIBLES:
        return "collectible"
    return {"player": "spawn", "checkpoint": "checkpoint"}.get(entity_type)


def draw_marker(drawing, x, y, kind):
    """Draw compact center-anchored symbols with a contrasting center pin."""
    color = COLORS[kind]
    if kind == "spawn":
        drawing.ellipse(
            (x - 3, y - 3, x + 3, y + 3),
            fill=color,
            outline=COLORS["background"],
            width=0.7,
        )
    elif kind == "checkpoint":
        drawing.polygon(
            [(x, y - 4), (x + 4, y), (x, y + 4), (x - 4, y)],
            fill=color,
            outline=COLORS["background"],
            width=0.7,
        )
    elif kind == "strawberry":
        drawing.polygon(
            [(x - 3.5, y - 3), (x + 3.5, y - 3), (x, y + 4)],
            fill=color,
            outline=COLORS["background"],
            width=0.7,
        )
    else:
        drawing.rectangle(
            (x - 3, y - 3, x + 3, y + 3),
            fill=color,
            outline=COLORS["background"],
            width=0.7,
        )
    drawing.ellipse(
        (x - 0.7, y - 0.7, x + 0.7, y + 0.7), fill=COLORS["background"]
    )


def render_overview(layout: dict, source_hash: str) -> tuple[bytes, dict]:
    """Render one 4416-pixel-wide PNG for whole-map inspection and zooming.

    Geometry, strokes, and text are rasterized at native resolution. No
    regional crops are generated; individual rooms have a separate tool.
    """
    rooms = layout["rooms"]
    if not rooms:
        raise ValueError("The map has no rooms.")
    boundaries = analyze_boundaries(rooms)
    left = min(room["x"] for room in rooms)
    top = min(room["y"] for room in rooms)
    right = max(room["x"] + room["w"] for room in rooms)
    bottom = max(room["y"] + room["h"] for room in rooms)
    width = 1472
    margin = 56
    plot_top = 172
    scale = min((width - 2 * margin) / (right - left), 1650 / (bottom - top))
    plot_height = round((bottom - top) * scale)
    plot_width = (right - left) * scale
    offset = (width - plot_width) / 2
    # Lonn's roomStruct.decode retains data.name verbatim, including lvl_.
    names = [room["name"] for room in rooms]
    label_font = ImageFont.load_default(size=24)
    key = []
    for index, (room, name) in enumerate(zip(rooms, names)):
        if label_font.getlength(name) > room["w"] * scale - 8:
            names[index] = f"#{index + 1}"
            key.append(f"#{index + 1}: {room['name']}")
    footer_top = plot_top + plot_height + 40
    height = footer_top + 194 + len(key) * 30
    if height > 6000:
        raise ValueError("Map is too dense for a readable single overview.")
    drawing = RasterCanvas(width, height, COLORS["background"], factor=3)
    picture = drawing.image
    body_font = ImageFont.load_default(size=26)
    title_font = ImageFont.load_default(size=38)

    def point(x, y):
        return (
            round(offset + (x - left) * scale),
            round(plot_top + (y - top) * scale),
        )

    def text(position, value, font=body_font, fill=COLORS["ink"], **kwargs):
        drawing.text(position, value, font=font, fill=fill, **kwargs)

    def segment(edge):
        if edge["side"] in {"left", "right"}:
            return (
                point(edge["axis"], edge["start"]),
                point(edge["axis"], edge["end"]),
            )
        return (
            point(edge["start"], edge["axis"]),
            point(edge["end"], edge["axis"]),
        )

    title = layout["title"]
    if title == "1-ForsakenCity":
        title = "Forsaken City | A-side"
    if title_font.getlength(title) > width - 2 * margin:
        while title_font.getlength(title + "...") > width - 2 * margin:
            title = title[:-1]
        title += "..."
    text((margin, 24), title, font=title_font)
    passages = boundaries["candidate_passages"]
    pairs = {tuple(sorted(item["room_indices"])) for item in passages}
    spawns = sum(
        entity["type"] == "player"
        for room in rooms
        for entity in room["entities"]
    )
    checkpoints = sum(
        entity["type"] == "checkpoint"
        for room in rooms
        for entity in room["entities"]
    )
    text(
        (margin, 80),
        f"{len(rooms)} rooms   /   {len(pairs)} candidate room links"
        f"   /   {spawns} spawn markers   /   {checkpoints} checkpoints",
    )
    text(
        (margin, 122),
        "Whole map | Full Lonn names | Open the full-resolution image to zoom",
        fill=COLORS["muted"],
    )
    for room in rooms:
        drawing.rectangle(
            [
                point(room["x"], room["y"]),
                point(room["x"] + room["w"], room["y"] + room["h"]),
            ],
            fill=COLORS["room"],
        )
    edges = styled_edges(rooms, boundaries)
    for edge in edges:
        drawing.line(segment(edge), fill=COLORS[edge["kind"]], width=4)
    markers = []
    marker_objects = []
    for index, room in enumerate(rooms):
        # Draw checkpoints after spawns so their distinct shape stays visible.
        entities = sorted(
            room["entities"], key=lambda item: item["type"] == "checkpoint"
        )
        unknown = [
            entity
            for entity in room["entities"]
            if entity["type"] not in DECORATIVE
            and symbol_kind(entity["type"]) not in LEGEND
        ]
        unknown_labels = {
            id(entity): f"U{index+1}" for index, entity in enumerate(unknown)
        }
        for entity in entities:
            kind = marker_kind(entity["type"])
            if kind is None:
                continue
            world_x = room["x"] + entity["x"]
            world_y = room["y"] + entity["y"]
            x, y = point(world_x, world_y)
            glyph = {"player": "S", "checkpoint": "C"}.get(
                entity["type"], unknown_labels.get(id(entity))
            )
            marker_objects.append((room, entity, glyph))
            markers.append(
                {
                    "room": room["name"],
                    "room_index": index,
                    "type": entity["type"],
                    "x": world_x,
                    "y": world_y,
                    "local_x": entity["x"],
                    "local_y": entity["y"],
                    "kind": kind,
                    "label": glyph,
                    "uses_original_sprite": object_sprite(entity) is not None,
                    "pixel_center": [x * 3, y * 3],
                    "note": (
                        "Heart puzzle anchor"
                        if entity["type"] == "birdForsakenCityGem"
                        else "Saved entity position"
                    ),
                }
            )
    label_boxes = []
    for index, (room, name) in enumerate(zip(rooms, names)):
        x, y = point(room["x"] + room["w"] / 2, room["y"] + room["h"] / 2)
        box = drawing.textbbox((x, y), name, font=label_font, anchor="mm")
        label_boxes.append(
            {
                "room": room["name"],
                "label": name,
                "bounds": [coordinate * 3 for coordinate in box],
            }
        )
        drawing.rectangle(
            (box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2),
            fill=COLORS["room"],
        )
        text((x, y), name, font=label_font, anchor="mm")

    # Markers stay above labels and borders; their centers are never displaced.
    for marker, (room, entity, glyph) in zip(markers, marker_objects):
        x, y = point(marker["x"], marker["y"])
        sprite_data = object_sprite(entity)
        if entity["type"] in {"player", "checkpoint"}:
            radius = 3 if entity["type"] == "player" else 4
            drawing.anchor_marker(
                (x, y),
                entity["type"],
                radius,
                COLORS[marker["kind"]],
                COLORS["background"],
                5,
            )
        elif sprite_data:
            sprite, sprite_x, sprite_y = sprite_data
            drawing.sprite(
                sprite,
                point(room["x"] + sprite_x, room["y"] + sprite_y),
                scale,
            )
        else:
            drawing.rectangle(
                (x - 4, y - 4, x + 4, y + 4), outline="#f8d78d", width=0.7
            )
            text(
                (x, y),
                glyph or "?",
                font=ImageFont.load_default(size=5),
                fill="#f8d78d",
                anchor="mm",
            )

    # The legend uses the same geometry as the data marks, plus text labels.
    legend_y = footer_top
    drawing.line(
        [(margin, legend_y + 14), (margin + 36, legend_y + 14)],
        fill=COLORS["passage"],
        width=5,
    )
    text((margin + 50, legend_y), "Candidate entrance / exit")
    drawing.line(
        [(770, legend_y + 14), (806, legend_y + 14)],
        fill=COLORS["unpaired"],
        width=4,
    )
    text((820, legend_y), "Unpaired air edge")
    legend_y += 42
    for x, kind, label in [
        (margin, "player", "Spawn"),
        (300, "checkpoint", "Checkpoint"),
    ]:
        drawing.anchor_marker(
            (x + 12, legend_y + 13),
            kind,
            12,
            COLORS["spawn" if kind == "player" else kind],
            COLORS["background"],
            16,
        )
        text((x + 30, legend_y), label)
    drawing.sprite(
        load_sprite("collectables/strawberry/normal00"), (620, legend_y), 1
    )
    text((654, legend_y), "Strawberry")
    drawing.sprite(
        load_sprite("collectables/cassette/idle00"), (940, legend_y - 3), 1
    )
    text((982, legend_y), "Collectible sprites*")
    text(
        (margin, legend_y + 44),
        "Candidates use touching air edges only; travel direction is unverified.",
        fill=COLORS["muted"],
    )
    text(
        (margin, legend_y + 80),
        "Unpaired edges can be sky or death pits. Hazards and physics are not checked.",
        fill=COLORS["muted"],
    )
    text(
        (margin, legend_y + 116),
        f"*U labels match room views. SHA-256: {source_hash[:16]}...",
        fill=COLORS["muted"],
    )
    for index, line in enumerate(key):
        text((margin, footer_top + 194 + index * 30), line, font=label_font)
    metadata = {
        "title": layout["title"],
        "map_sha256": source_hash,
        "room_count": len(rooms),
        "candidate_room_links": len(pairs),
        "spawn_count": spawns,
        "checkpoint_count": checkpoints,
        "strawberry_count": sum(
            marker["kind"] == "strawberry" for marker in markers
        ),
        "other_collectible_count": sum(
            marker["kind"] == "collectible" for marker in markers
        ),
        "rooms": [
            {key: room[key] for key in ("name", "x", "y", "w", "h")}
            for room in rooms
        ],
        **boundaries,
        "markers": markers,
        "image_size": list(picture.size),
        "room_bounds": [
            {
                "room": room["name"],
                "bounds": [
                    coordinate * 3
                    for coordinate in (
                        *point(room["x"], room["y"]),
                        *point(room["x"] + room["w"], room["y"] + room["h"]),
                    )
                ],
            }
            for room in rooms
        ],
        "styled_edges": edges,
        "pixels_per_game_pixel": scale * 3,
        "label_boxes": label_boxes,
        "limitations": [
            "Candidate passages require >=8 px overlapping air on touching room edges.",
            "No traversal direction, start room, chapter ending, or playability is inferred.",
            "Unpaired air edges may be inaccessible or lethal, not usable map exits.",
            "Dynamic entities, hazards, transition settings, and scripts are not checked.",
        ],
    }
    with BytesIO() as stream:
        picture.save(stream, format="PNG")
        return stream.getvalue(), metadata


def make_overview_result(
    workspace: Path,
    map_path: str = "",
    source: Literal["mod", "vanilla"] = "mod",
) -> ToolResult:
    """Return one high-resolution whole-map PNG and metadata.

    No files are written. Raises if the source changes during the read/render.
    """
    path = resolve_overview_source(workspace, map_path, source)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    layout = extract_layout(cb.read_map(path), path.stem)
    png, metadata = render_overview(layout, before)
    images = [
        ImageContent(
            type="image",
            mimeType="image/png",
            data=base64.b64encode(png).decode("ascii"),
        )
    ]
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise RuntimeError(
            "Map changed while rendering; request a new preview."
        )
    metadata["source"] = str(path)
    metadata["source_kind"] = source
    metadata["png_sha256"] = hashlib.sha256(png).hexdigest()
    return ToolResult(
        content=[
            TextContent(
                type="text",
                text=(
                    f"{path.stem}: {metadata['room_count']} rooms, "
                    f"{metadata['candidate_room_links']} candidate room links, "
                    f"{metadata['spawn_count']} spawns, "
                    f"{metadata['checkpoint_count']} checkpoints. "
                    "Connections are geometric candidates, not verified routes. "
                    f"Source unchanged; SHA-256 {before}."
                ),
            ),
            *images,
        ],
        structured_content=metadata,
    )
