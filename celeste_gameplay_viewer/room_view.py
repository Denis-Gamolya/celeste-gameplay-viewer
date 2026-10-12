"""Render one room's saved gameplay geometry as an annotated PNG.

Symbols follow Lonn entity definitions, but are schematic and not hitboxes.
Dynamic state, physics, and script behavior are never simulated.
"""

import base64
import hashlib
import math
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fastmcp.tools import ToolResult
from mcp.types import ImageContent, TextContent
from PIL import ImageFont

from .map_geometry import analyze_boundaries, styled_edges
from .map_source import resolve_map_source
from .raster import RasterCanvas
from .render_style import COLORS
from .sprites import load_sprite, object_sprite, spike_sprites
from .viewer import cb, extract_layout

DECORATIVE = {
    "lamp",
    "wire",
    "lightbeam",
    "flutterbird",
    "memorialTextController",
}
VISUAL_TRIGGERS = {
    "cameraOffsetTrigger",
    "cameraTargetTrigger",
    "cameraAdvanceTargetTrigger",
    "bloomFadeTrigger",
    "colorGradeTrigger",
    "lightFadeTrigger",
    "everest/smoothCameraOffsetTrigger",
}
GAMEPLAY_TRIGGERS = {
    "changeRespawnTrigger",
    "respawnTargetTrigger",
    "windTrigger",
    "windAttackTrigger",
    "goldenBerryCollectTrigger",
}
BLOCK_LABELS = {
    "zipMover": "Z",
    "fallingBlock": "F",
    "dashBlock": "D",
    "fakeWall": "H",
    "fakeBlock": "H",
    "coverupWall": "H",
    "moveBlock": "M",
    "cassetteBlock": "C",
}
LEGEND = {
    "player": ("S  Spawn / respawn anchor", COLORS["spawn"]),
    "checkpoint": ("C  Checkpoint", COLORS["checkpoint"]),
    "strawberry": ("Berry sprite: strawberry", "#ff8eb7"),
    "goldenBerry": ("G  Golden berry", "#ffd666"),
    "spikes": ("Spike sprites: hazard", "#d7deeb"),
    "spring": ("Spring sprite: bounce", "#7beba8"),
    "zipMover": ("Z  Zip mover + endpoint", "#eab370"),
    "crumbleBlock": ("Broken bar: crumble", "#eab370"),
    "fallingBlock": ("F  Falling block", "#cfb99c"),
    "dashBlock": ("D  Dash block", "#b7a1ff"),
    "fakeWall": ("", "#9aaec9"),
    "cassetteBlock": ("Solid colors: cassette blocks", "#7cc8ff"),
    "cassette": ("Tape: cassette collectible", "#f091df"),
    "jumpThru": ("Brown bar: jump-through", "#b88552"),
    "refill": ("Crystal sprite: dash refill", "#70e9cf"),
    "spinner": ("Crystal / X: spinner hazard", "#ff6575"),
    "booster": ("Bubble: booster", "#7beba8"),
    "cloud": ("Cloud platform", "#accdff"),
    "moveBlock": ("M  Move block + direction", "#eab370"),
    "badelineBoost": ("Badeline boost sprite", "#ce9bff"),
    "key": ("Key sprite: collectible", "#ffd666"),
}


def select_room(layout: dict, name: str) -> dict:
    """Resolve an exact stored room name, or its unambiguous lvl_-less ID."""
    exact = [room for room in layout["rooms"] if room["name"] == name]
    matches = exact or [
        room
        for room in layout["rooms"]
        if room["name"].removeprefix("lvl_") == name
    ]
    if len(matches) != 1:
        available = ", ".join(room["name"] for room in layout["rooms"])
        raise ValueError(
            f"Unknown or ambiguous room {name!r}. Available: {available}"
        )
    return matches[0]


def symbol_kind(kind: str) -> str:
    """Group verified variants for symbols while preserving raw type names."""
    if kind in {"spikesUp", "spikesDown", "spikesLeft", "spikesRight"}:
        return "spikes"
    if kind in {"spring", "wallSpringLeft", "wallSpringRight"}:
        return "spring"
    if kind in {"fakeWall", "fakeBlock", "coverupWall"}:
        return "fakeWall"
    return kind


def spike_triangles(entity: dict) -> list[list[tuple[float, float]]]:
    """Return eight-pixel schematic spikes pointing outward from their anchor."""
    x, y = entity["x"], entity["y"]
    kind = entity["type"]
    vertical = kind in {"spikesLeft", "spikesRight"}
    length = entity["h" if vertical else "w"] or 8
    triangles = []
    for offset in range(0, int(length), 8):
        span = min(8, length - offset)
        if kind == "spikesUp":
            points = [
                (x + offset, y),
                (x + offset + span / 2, y - 8),
                (x + offset + span, y),
            ]
        elif kind == "spikesDown":
            points = [
                (x + offset, y),
                (x + offset + span / 2, y + 8),
                (x + offset + span, y),
            ]
        elif kind == "spikesLeft":
            points = [
                (x, y + offset),
                (x - 8, y + offset + span / 2),
                (x, y + offset + span),
            ]
        else:
            points = [
                (x, y + offset),
                (x + 8, y + offset + span / 2),
                (x, y + offset + span),
            ]
        triangles.append(points)
    return triangles


def node_points(entity: dict) -> list[tuple[float, float]]:
    """Return node path anchors; zip-mover nodes are block top-left positions."""
    offset_x = entity["w"] / 2 if entity["type"] == "zipMover" else 0
    offset_y = entity["h"] / 2 if entity["type"] == "zipMover" else 0
    return [
        (x + offset_x, y + offset_y)
        for x, y in [(entity["x"], entity["y"]), *entity.get("nodes", [])]
    ]


class RoomDrawing:
    """Draw local game coordinates onto a native-resolution raster canvas.

    Scale is logical image pixels per game pixel; RasterCanvas applies the
    final resolution multiplier. Drawing order is controlled by render_room.
    """

    def __init__(
        self,
        canvas: RasterCanvas,
        left: float,
        top: float,
        plot_top: float,
        scale: float,
        symbol_font,
    ):
        self.canvas = canvas
        self.left = left
        self.top = top
        self.plot_top = plot_top
        self.scale = scale
        self.symbol_font = symbol_font

    def to_image_point(self, x, y):
        """Convert local game pixels to logical image pixels."""
        return (
            36 + (x - self.left) * self.scale,
            self.plot_top + (y - self.top) * self.scale,
        )

    def draw_line(self, points, color, width=1):
        """Draw a path in local game-pixel coordinates."""
        self.canvas.line(
            [self.to_image_point(x, y) for x, y in points],
            fill=color,
            width=width,
        )

    def draw_box(self, x, y, width, height, fill=None, outline=None, stroke=1):
        """Draw a rectangular object in local game pixels."""
        self.canvas.rectangle(
            [
                self.to_image_point(x, y),
                self.to_image_point(x + width, y + height),
            ],
            fill=fill,
            outline=outline,
            width=stroke,
        )

    def draw_label(self, x, y, text, color=COLORS["ink"]):
        """Center a symbol label on a local game-pixel anchor."""
        self.canvas.text(
            self.to_image_point(x, y),
            text,
            font=self.symbol_font,
            fill=color,
            anchor="mm",
        )

    def draw_dotted_path(self, points, color):
        """Draw a saved node or trigger path with constant image-pixel dashes."""
        for start, end in zip(points, points[1:]):
            length = math.dist(start, end)
            if not length:
                continue
            for offset in range(0, math.ceil(length * self.scale), 9):
                first = min(offset / self.scale / length, 1)
                last = min((offset + 4) / self.scale / length, 1)
                self.draw_line(
                    [
                        tuple(
                            start[i] + (end[i] - start[i]) * fraction
                            for i in range(2)
                        )
                        for fraction in (first, last)
                    ],
                    color,
                )

    def draw_diamond(self, x, y, radius, color, text=""):
        """Draw a collectible fallback around a game-pixel anchor."""
        self.canvas.polygon(
            [
                self.to_image_point(x, y - radius),
                self.to_image_point(x + radius, y),
                self.to_image_point(x, y + radius),
                self.to_image_point(x - radius, y),
            ],
            fill=color,
        )
        if text:
            self.draw_label(x, y, text, COLORS["background"])

    def draw_arrow(self, x, y, dx, dy, color):
        """Draw direction with a fixed game-pixel arrowhead."""
        self.draw_line([(x, y), (x + dx, y + dy)], color, 2)
        length = math.hypot(dx, dy)
        unit_x, unit_y = dx / length, dy / length
        tip = (x + dx, y + dy)
        self.draw_line(
            [
                (
                    tip[0] - unit_x * 4 - unit_y * 3,
                    tip[1] - unit_y * 4 + unit_x * 3,
                ),
                tip,
                (
                    tip[0] - unit_x * 4 + unit_y * 3,
                    tip[1] - unit_y * 4 - unit_x * 3,
                ),
            ],
            color,
            2,
        )

    def draw_entity(
        self, entity: dict, unknown_tags: dict, sprite_warnings: list[str]
    ) -> None:
        """Draw one gameplay entity, retaining sprite and schematic fallback rules."""
        entity_type = entity["type"]
        symbol_type = symbol_kind(entity_type)
        x, y, width, height = (entity[key] for key in ("x", "y", "w", "h"))
        properties = entity["properties"]
        color = LEGEND.get(symbol_type, ("", "#f8d78d"))[1]
        sprite_frame = object_sprite(entity)
        if symbol_type == "fakeWall":
            return
        elif symbol_type == "spikes":
            spike_frames = spike_sprites(entity)
            if spike_frames:
                for sprite, sprite_x, sprite_y in spike_frames:
                    self.canvas.sprite(
                        sprite,
                        self.to_image_point(sprite_x, sprite_y),
                        self.scale,
                    )
            else:
                sprite_warnings.append(
                    f"Schematic spike fallback: {properties.get('type', 'default')}"
                )
                for triangle in spike_triangles(entity):
                    self.canvas.polygon(
                        [self.to_image_point(*vertex) for vertex in triangle],
                        fill=color,
                    )
        elif sprite_frame:
            sprite, sprite_x, sprite_y = sprite_frame
            self.canvas.sprite(
                sprite, self.to_image_point(sprite_x, sprite_y), self.scale
            )
        elif entity_type in BLOCK_LABELS:
            width, height = width or 8, height or 8
            color = (
                ("#49aaf0", "#f049be", "#fcdc3a", "#38e04e")[
                    int(properties.get("index", 0)) % 4
                ]
                if entity_type == "cassetteBlock"
                else color
            )
            fill = color if entity_type == "cassetteBlock" else "#333642"
            self.draw_box(
                x, y, width, height, fill=fill, outline=color, stroke=2
            )
            symbol_label = BLOCK_LABELS[entity_type] + (
                str(properties.get("index", 0))
                if entity_type == "cassetteBlock"
                else ""
            )
            if entity_type != "cassetteBlock":
                self.draw_label(
                    x + width / 2, y + height / 2, symbol_label, color
                )
            if entity_type == "moveBlock":
                direction_x, direction_y = {
                    "Left": (-8, 0),
                    "Right": (8, 0),
                    "Up": (0, -8),
                    "Down": (0, 8),
                }.get(entity.get("direction"), (0, 0))
                if direction_x or direction_y:
                    self.draw_arrow(
                        x + width / 2,
                        y + height / 2 + 8,
                        direction_x,
                        direction_y,
                        color,
                    )
        elif entity_type == "crumbleBlock":
            self.draw_box(x, y, width or 8, 8, fill="#554735", outline=color)
            for offset in range(6, int(width or 8), 8):
                self.draw_line(
                    [
                        (x + offset, y),
                        (x + offset - 3, y + 4),
                        (x + offset, y + 8),
                    ],
                    COLORS["background"],
                )
        elif entity_type == "jumpThru":
            self.draw_line([(x, y), (x + width, y)], color, 3)
        elif symbol_type == "spring":
            direction_x, direction_y = {
                "spring": (0, -12),
                "wallSpringLeft": (12, 0),
                "wallSpringRight": (-12, 0),
            }[entity_type]
            self.draw_arrow(x, y, direction_x, direction_y, color)
            self.draw_line(
                (
                    [(x - 6, y), (x + 6, y)]
                    if direction_y
                    else [(x, y - 6), (x, y + 6)]
                ),
                color,
                3,
            )
        elif entity_type == "player":
            self.canvas.anchor_marker(
                self.to_image_point(x, y),
                entity_type,
                7,
                color,
                COLORS["background"],
                11,
            )
        elif entity_type == "refill":
            texture = (
                "objects/refillTwo/idle00"
                if entity.get("twoDash")
                else "objects/refill/idle00"
            )
            sprite = load_sprite(texture)
            if sprite is None:
                raise FileNotFoundError(
                    f"Required refill sprite missing: {texture}"
                )
            self.canvas.sprite(
                sprite,
                self.to_image_point(
                    x - sprite.width / 2, y - sprite.height / 2
                ),
                self.scale,
            )
        elif entity_type in {"checkpoint", "strawberry", "goldenBerry"}:
            symbol_label = {
                "checkpoint": "C",
                "strawberry": "B",
                "goldenBerry": "G",
                "refill": "R",
            }[entity_type]
            if entity_type == "checkpoint":
                self.canvas.anchor_marker(
                    self.to_image_point(x, y),
                    entity_type,
                    max(6 * self.scale, 8),
                    color,
                    COLORS["background"],
                    11,
                )
            else:
                self.draw_diamond(
                    x, y, max(6, 8 / self.scale), color, symbol_label
                )
            if entity_type == "strawberry" and properties.get("winged"):
                self.draw_line(
                    [(x - 12, y - 4), (x - 8, y), (x + 8, y), (x + 12, y - 4)],
                    color,
                )
        elif entity_type == "cassette":
            self.draw_box(
                x - 9, y - 6, 18, 12, fill=color, outline=COLORS["ink"]
            )
            for delta in (-4, 4):
                px, py = self.to_image_point(x + delta, y)
                self.canvas.ellipse(
                    (px - 2, py - 2, px + 2, py + 2), fill=COLORS["background"]
                )
        elif entity_type == "spinner":
            self.draw_diamond(x, y, 5, color)
            self.draw_line([(x - 5, y - 5), (x + 5, y + 5)], color)
            self.draw_line([(x - 5, y + 5), (x + 5, y - 5)], color)
        elif entity_type in {"booster", "badelineBoost"}:
            color = (
                "#ff6575"
                if entity_type == "booster" and entity.get("red")
                else color
            )
            px, py = self.to_image_point(x, y)
            radius = max(9, 8 * self.scale)
            self.canvas.ellipse(
                (px - radius, py - radius, px + radius, py + radius),
                fill=COLORS["background"],
                outline=color,
                width=2,
            )
            self.draw_label(
                x, y, "BB" if entity_type == "badelineBoost" else "O", color
            )
        elif entity_type == "cloud":
            self.draw_box(x - 16, y - 4, 32, 8, fill=color)
        else:
            self.draw_box(x, y, width or 8, height or 8, outline=color)
            self.draw_label(
                x + (width or 8) / 2,
                y + (height or 8) / 2,
                unknown_tags[id(entity)],
                color,
            )


def entity_paint_order(entity: dict) -> int:
    """Paint large blocks first and spawn/checkpoint anchors last."""
    if entity["type"] in BLOCK_LABELS:
        return 0
    if entity["type"] in {"player", "checkpoint"}:
        return 2
    return 1


def draw_triggers(
    drawing: RoomDrawing, triggers: list, trigger_tags: dict
) -> None:
    """Draw trigger regions and saved nodes; respawn regions remain unlabeled."""
    for trigger in triggers:
        x, y, width, height = (trigger[key] for key in ("x", "y", "w", "h"))
        drawing.draw_dotted_path(
            [
                (x, y),
                (x + width, y),
                (x + width, y + height),
                (x, y + height),
                (x, y),
            ],
            "#e0a1ef",
        )
        if id(trigger) in trigger_tags:
            drawing.draw_label(
                x + width / 2,
                y + min(height / 2, 8),
                trigger_tags[id(trigger)],
                "#e0a1ef",
            )
        if trigger.get("nodes"):
            nodes = [(x + width / 2, y + height / 2), *trigger["nodes"]]
            drawing.draw_dotted_path(nodes, "#e0a1ef")
            for node_x, node_y in trigger["nodes"]:
                drawing.draw_diamond(node_x, node_y, 5, "#e0a1ef", "R")


def draw_entity_paths(drawing: RoomDrawing, entities: list) -> None:
    """Draw node paths before owning objects so endpoints remain visible."""
    for entity in entities:
        if entity.get("nodes"):
            nodes = node_points(entity)
            drawing.draw_dotted_path(nodes, "#c5a4e5")
            for node_x, node_y in nodes[1:]:
                pixel_x, pixel_y = drawing.to_image_point(node_x, node_y)
                drawing.canvas.ellipse(
                    (pixel_x - 4, pixel_y - 4, pixel_x + 4, pixel_y + 4),
                    outline="#c5a4e5",
                    width=1,
                )
            if entity["type"] == "zipMover":
                for node_x, node_y in entity["nodes"]:
                    drawing.draw_dotted_path(
                        [
                            (node_x, node_y),
                            (node_x + entity["w"], node_y),
                            (node_x + entity["w"], node_y + entity["h"]),
                            (node_x, node_y + entity["h"]),
                            (node_x, node_y),
                        ],
                        "#eab370",
                    )


def draw_room_boundaries(
    drawing: RoomDrawing, room: dict, layout: dict
) -> None:
    """Paint singly colored edge spans over the finished gameplay drawing."""
    for edge in styled_edges([room], analyze_boundaries(layout["rooms"])):
        if edge["side"] == "left":
            points = [
                (edge["axis"] - room["x"], edge["start"] - room["y"]),
                (edge["axis"] - room["x"], edge["end"] - room["y"]),
            ]
        else:
            points = [
                (edge["start"] - room["x"], edge["axis"] - room["y"]),
                (edge["end"] - room["x"], edge["axis"] - room["y"]),
            ]
        drawing.draw_line(points, COLORS[edge["kind"]], 1.5)


@dataclass
class RoomAnnotations:
    """Filtered gameplay objects and labels used by both drawing and metadata."""

    entities: list[dict]
    triggers: list[dict]
    unknown_tags: dict[int, str]
    warnings: list[str]
    sprite_warnings: list[str]
    trigger_tags: dict[int, str]
    trigger_notes: list[str]
    legends: list[tuple[str, str]]
    note_lines: list[str]


@dataclass
class RoomPlot:
    """Logical image layout and scale for objects measured in local game pixels."""

    left: float
    top: float
    scale: float
    plot_top: int
    footer: int
    height: int


def prepare_room_annotations(room: dict) -> RoomAnnotations:
    """Retain gameplay objects and wrap inspection notes without hiding identity."""
    entities = [
        entity
        for entity in room["entities"]
        if entity["type"] not in DECORATIVE
    ]
    triggers = [
        trigger
        for trigger in room["triggers"]
        if trigger["type"] not in VISUAL_TRIGGERS
    ]
    unknown = [
        entity
        for entity in entities
        if symbol_kind(entity["type"]) not in LEGEND
    ]
    unknown_tags = {
        id(entity): f"U{index+1}" for index, entity in enumerate(unknown)
    }
    warnings = [
        f"U{index+1}: {entity['type']} at ({entity['x']}, {entity['y']})"
        for index, entity in enumerate(unknown)
    ]
    sprite_warnings = []
    labeled_triggers = [
        trigger
        for trigger in triggers
        if trigger["type"] != "changeRespawnTrigger"
    ]
    trigger_tags = {
        id(trigger): f"T{index+1}"
        for index, trigger in enumerate(labeled_triggers)
    }
    trigger_notes = [
        f"{trigger_tags[id(trigger)]}: {trigger['type']}"
        + (
            " [behavior unverified]"
            if trigger["type"] not in GAMEPLAY_TRIGGERS
            else ""
        )
        for trigger in labeled_triggers
    ]
    legend_keys = sorted(
        ({symbol_kind(entity["type"]) for entity in entities} & LEGEND.keys())
        - {"fakeWall"}
    )
    legends = [("Filled gray: solid tiles", "#7b8795")]
    legends += [LEGEND[key] for key in legend_keys]
    if any(entity.get("nodes") for entity in [*entities, *triggers]):
        legends.append(("Dotted paths: saved nodes", "#c5a4e5"))
    if triggers:
        legends.append(("Purple outline: trigger region", "#e0a1ef"))
    if unknown:
        legends.append(("U#: unknown object", "#f8d78d"))
    note_lines = []
    for note in [*trigger_notes, *warnings]:
        # Wrap long modded names rather than hiding their identity in the PNG.
        while len(note) > 85:
            note_lines.append(note[:85])
            note = note[85:]
        note_lines.append(note)
    return RoomAnnotations(
        entities,
        triggers,
        unknown_tags,
        warnings,
        sprite_warnings,
        trigger_tags,
        trigger_notes,
        legends,
        note_lines,
    )


def measure_room_plot(room: dict, annotations: RoomAnnotations) -> RoomPlot:
    """Fit room bounds, outside triggers, nodes, and sprites into the image.

    Extents include objects beyond room bounds. Those are valid saved map data,
    and clipping them would conceal gameplay-relevant information.
    """
    points = [(0, 0), (room["w"], room["h"])]
    for entity in [*annotations.entities, *annotations.triggers]:
        points += [
            (entity["x"] - 12, entity["y"] - 12),
            (
                entity["x"] + max(entity["w"], 12),
                entity["y"] + max(entity["h"], 12),
            ),
        ]
        points += [(x - 12, y - 12) for x, y in entity.get("nodes", [])]
        points += [
            (x + max(entity["w"], 12), y + max(entity["h"], 12))
            for x, y in entity.get("nodes", [])
        ]
        sprite_data = object_sprite(entity)
        if sprite_data:
            sprite, sx, sy = sprite_data
            points += [(sx, sy), (sx + sprite.width, sy + sprite.height)]
    left = min(x for x, _ in points)
    top = min(y for _, y in points)
    right = max(x for x, _ in points)
    bottom = max(y for _, y in points)
    scale = min(664 / (right - left), 1000 / (bottom - top))
    plot_top = 114
    plot_height = math.ceil((bottom - top) * scale)
    footer = plot_top + plot_height + 26
    height = (
        footer
        + math.ceil(len(annotations.legends) / 3) * 23
        + len(annotations.note_lines) * 19
        + 74
    )
    return RoomPlot(left, top, scale, plot_top, footer, height)


def describe_room_render(
    room: dict,
    annotations: RoomAnnotations,
    source_hash: str,
    canvas: RasterCanvas,
) -> dict:
    """Expose original saved objects, counts, warnings, and image dimensions."""
    return {
        "room": room["name"],
        "world_bounds": [room["x"], room["y"], room["w"], room["h"]],
        "map_sha256": source_hash,
        "image_size": list(canvas.image.size),
        "entities": annotations.entities,
        "triggers": annotations.triggers,
        "unknown_entities": annotations.warnings,
        "sprite_warnings": sorted(set(annotations.sprite_warnings)),
        "trigger_notes": annotations.trigger_notes,
        "entity_counts": dict(
            Counter(entity["type"] for entity in annotations.entities)
        ),
        "solid_tile_count": sum(
            tile not in {"0", " "} for row in room["tiles"] for tile in row
        ),
        "excluded_entity_counts": dict(
            Counter(
                entity["type"]
                for entity in room["entities"]
                if entity["type"] in DECORATIVE
            )
        ),
        "excluded_trigger_counts": dict(
            Counter(
                trigger["type"]
                for trigger in room["triggers"]
                if trigger["type"] in VISUAL_TRIGGERS
            )
        ),
        "limitations": [
            "Schematic symbols are not exact hitboxes or dynamic state.",
            "Unknown objects and unclassified triggers are retained, not interpreted.",
            "Saved node paths need not represent traversable movement.",
        ],
    }


def render_room(
    layout: dict, room_name: str, source_hash: str
) -> tuple[bytes, dict]:
    """Return a focused 1472-pixel-wide PNG and complete inspectable metadata.

    Includes solid tiles, symbols, nodes, triggers, and bounds in game pixels.
    Unknown objects stay visible as numbered labels with type/ID/coordinates.
    Known decorative entities and visual triggers are omitted. No file writes.
    """
    room = select_room(layout, room_name)
    annotations = prepare_room_annotations(room)
    plot = measure_room_plot(room, annotations)
    canvas = RasterCanvas(736, plot.height, COLORS["background"], 2)
    font = ImageFont.load_default(size=13)
    small = ImageFont.load_default(size=12)
    title_font = ImageFont.load_default(size=22)
    symbol_font = ImageFont.load_default(size=11)

    drawing = RoomDrawing(
        canvas, plot.left, plot.top, plot.plot_top, plot.scale, symbol_font
    )

    map_title = (
        "Forsaken City A-side"
        if layout["title"] == "1-ForsakenCity"
        else layout["title"]
    )
    title = f"{map_title} | {room['name']}"
    while title_font.getlength(title) > 680:
        title = title[:-4] + "..."
    canvas.text((28, 14), title, font=title_font, fill=COLORS["ink"])
    canvas.text(
        (28, 47),
        f"{room['w']} x {room['h']} game px | "
        f"{len(annotations.entities)} objects | {len(annotations.triggers)} triggers | 8 px tiles",
        font=font,
        fill=COLORS["muted"],
    )
    canvas.text(
        (28, 70),
        "Saved geometry and nodes; schematic symbols, not exact hitboxes",
        font=small,
        fill=COLORS["muted"],
    )
    drawing.draw_box(0, 0, room["w"], room["h"], fill="#191e25")
    hidden_regions = [
        entity
        for entity in annotations.entities
        if symbol_kind(entity["type"]) == "fakeWall"
    ]
    for row_index, row in enumerate(room["tiles"]):
        for column, tile in enumerate(row):
            if tile not in {"0", " "}:
                drawing.draw_box(
                    column * 8,
                    row_index * 8,
                    8,
                    8,
                    fill="#667280",
                    outline="#505c69",
                    stroke=0.4,
                )
    # Reveal hidden passages in the preview without changing source tile data.
    for hidden in hidden_regions:
        drawing.draw_box(
            hidden["x"], hidden["y"], hidden["w"], hidden["h"], fill="#191e25"
        )
    for x in range(0, room["w"] + 1, 64):
        canvas.text(
            drawing.to_image_point(x, -8),
            str(x),
            font=small,
            fill=COLORS["muted"],
            anchor="mm",
        )
    for y in range(0, room["h"] + 1, 64):
        px, py = drawing.to_image_point(0, y)
        canvas.text(
            (px - 8, py), str(y), font=small, fill=COLORS["muted"], anchor="rm"
        )
    draw_triggers(drawing, annotations.triggers, annotations.trigger_tags)
    # Paths precede objects so endpoints do not hide their owning blocks.
    draw_entity_paths(drawing, annotations.entities)
    # Blocks precede smaller objects so a hidden collectible remains visible.
    for entity in sorted(annotations.entities, key=entity_paint_order):
        drawing.draw_entity(
            entity, annotations.unknown_tags, annotations.sprite_warnings
        )
    draw_room_boundaries(drawing, room, layout)
    for index, (text, color) in enumerate(annotations.legends):
        canvas.text(
            (28 + (index % 3) * 233, plot.footer + (index // 3) * 23),
            text,
            font=small,
            fill=color,
        )
    cursor = plot.footer + math.ceil(len(annotations.legends) / 3) * 23 + 8
    for note in annotations.note_lines:
        canvas.text((28, cursor), note, font=small, fill=COLORS["ink"])
        cursor += 19
    canvas.text(
        (28, cursor + 4),
        "Green edge: candidate crossing | Red edge: unpaired air",
        font=small,
        fill=COLORS["muted"],
    )
    canvas.text(
        (28, cursor + 25),
        f"Map SHA-256: {source_hash[:16]}... | Decorations omitted",
        font=small,
        fill=COLORS["muted"],
    )
    metadata = describe_room_render(room, annotations, source_hash, canvas)
    with BytesIO() as stream:
        canvas.image.save(stream, format="PNG")
        return stream.getvalue(), metadata


def make_room_result(
    workspace: Path, room_name: str, map_path: str = "", source: str = "mod"
) -> ToolResult:
    """Read one authorized map and return a room PNG, metadata, and source hash."""
    path = resolve_map_source(workspace, map_path, source)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    layout = extract_layout(cb.read_map(path), path.stem)
    png, metadata = render_room(layout, room_name, before)
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise RuntimeError(
            "Map changed while rendering; request another preview."
        )
    metadata.update(
        {"source": str(path), "png_sha256": hashlib.sha256(png).hexdigest()}
    )
    return ToolResult(
        content=[
            TextContent(
                type="text",
                text=f"{metadata['room']}: {len(metadata['entities'])} objects, "
                f"{len(metadata['triggers'])} triggers; source unchanged. "
                f"{len(metadata['unknown_entities'])} unknown objects retained. SHA-256 {before}.",
            ),
            ImageContent(
                type="image",
                mimeType="image/png",
                data=base64.b64encode(png).decode("ascii"),
            ),
        ],
        structured_content=metadata,
    )
