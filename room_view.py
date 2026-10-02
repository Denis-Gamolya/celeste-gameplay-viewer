"""Render one room's saved gameplay geometry as an annotated PNG.

Symbols follow Lonn entity definitions, but are schematic and not hitboxes.
Dynamic state, physics, and script behavior are never simulated.
"""

import base64
from collections import Counter
import hashlib
from io import BytesIO
import math
from pathlib import Path

from fastmcp.tools import ToolResult
from mcp.types import ImageContent, TextContent
from PIL import ImageFont

from overview import COLORS, analyze_boundaries, resolve_overview_source, styled_edges
from raster import RasterCanvas
from sprites import load_sprite, object_sprite, spike_sprites
from viewer import cb, extract_layout

DECORATIVE = {"lamp", "wire", "lightbeam", "flutterbird", "memorialTextController"}
VISUAL_TRIGGERS = {
    "cameraOffsetTrigger", "cameraTargetTrigger", "cameraAdvanceTargetTrigger",
    "bloomFadeTrigger", "colorGradeTrigger", "lightFadeTrigger",
    "everest/smoothCameraOffsetTrigger",
}
GAMEPLAY_TRIGGERS = {"changeRespawnTrigger", "respawnTargetTrigger",
                     "windTrigger", "windAttackTrigger", "goldenBerryCollectTrigger"}
BLOCK_LABELS = {"zipMover": "Z", "fallingBlock": "F", "dashBlock": "D",
                "fakeWall": "H", "fakeBlock": "H", "coverupWall": "H",
                "moveBlock": "M", "cassetteBlock": "C"}
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
    matches = exact or [room for room in layout["rooms"]
                        if room["name"].removeprefix("lvl_") == name]
    if len(matches) != 1:
        available = ", ".join(room["name"] for room in layout["rooms"])
        raise ValueError(f"Unknown or ambiguous room {name!r}. Available: {available}")
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
        span = min(8, length-offset)
        if kind == "spikesUp":
            points = [(x+offset, y), (x+offset+span/2, y-8), (x+offset+span, y)]
        elif kind == "spikesDown":
            points = [(x+offset, y), (x+offset+span/2, y+8), (x+offset+span, y)]
        elif kind == "spikesLeft":
            points = [(x, y+offset), (x-8, y+offset+span/2), (x, y+offset+span)]
        else:
            points = [(x, y+offset), (x+8, y+offset+span/2), (x, y+offset+span)]
        triangles.append(points)
    return triangles


def node_points(entity: dict) -> list[tuple[float, float]]:
    """Return node path anchors; zip-mover nodes are block top-left positions."""
    offset_x = entity["w"]/2 if entity["type"] == "zipMover" else 0
    offset_y = entity["h"]/2 if entity["type"] == "zipMover" else 0
    return [(x+offset_x, y+offset_y)
            for x, y in [(entity["x"], entity["y"]), *entity.get("nodes", [])]]


def render_room(layout: dict, room_name: str, source_hash: str) -> tuple[bytes, dict]:
    """Return a focused 1472-pixel-wide PNG and complete inspectable metadata.

    Includes solid tiles, symbols, nodes, triggers, and bounds in game pixels.
    Unknown objects stay visible as numbered labels with type/ID/coordinates.
    Known decorative entities and visual triggers are omitted. No file writes.
    """
    room = select_room(layout, room_name)
    entities = [entity for entity in room["entities"] if entity["type"] not in DECORATIVE]
    triggers = [trigger for trigger in room["triggers"]
                if trigger["type"] not in VISUAL_TRIGGERS]
    unknown = [entity for entity in entities if symbol_kind(entity["type"]) not in LEGEND]
    unknown_tags = {id(entity): f"U{index+1}" for index, entity in enumerate(unknown)}
    warnings = [f"U{index+1}: {entity['type']} at ({entity['x']}, {entity['y']})"
                for index, entity in enumerate(unknown)]
    sprite_warnings = []
    labeled_triggers = [trigger for trigger in triggers
                        if trigger["type"] != "changeRespawnTrigger"]
    trigger_tags = {id(trigger): f"T{index+1}"
                    for index, trigger in enumerate(labeled_triggers)}
    trigger_notes = [f"{trigger_tags[id(trigger)]}: {trigger['type']}"
                     + (" [behavior unverified]" if trigger["type"] not in GAMEPLAY_TRIGGERS else "")
                     for trigger in labeled_triggers]
    legend_keys = sorted(({symbol_kind(entity["type"]) for entity in entities} & LEGEND.keys()) - {"fakeWall"})
    legends = [("Filled gray: solid tiles", "#7b8795")]
    legends += [LEGEND[key] for key in legend_keys]
    if any(entity.get("nodes") for entity in [*entities, *triggers]):
        legends.append(("Dotted paths: saved nodes", "#c5a4e5"))
    if triggers:
        legends.append(("Purple outline: trigger region", "#e0a1ef"))
    if unknown:
        legends.append(("U#: unknown object", "#f8d78d"))
    points = [(0, 0), (room["w"], room["h"])]
    for entity in [*entities, *triggers]:
        points += [(entity["x"]-12, entity["y"]-12),
                   (entity["x"]+max(entity["w"], 12), entity["y"]+max(entity["h"], 12))]
        points += [(x-12, y-12) for x, y in entity.get("nodes", [])]
        points += [(x+max(entity["w"], 12), y+max(entity["h"], 12))
                   for x, y in entity.get("nodes", [])]
        sprite_data = object_sprite(entity)
        if sprite_data:
            sprite, sx, sy = sprite_data
            points += [(sx, sy), (sx+sprite.width, sy+sprite.height)]
    left = min(x for x, _ in points)
    top = min(y for _, y in points)
    right = max(x for x, _ in points)
    bottom = max(y for _, y in points)
    scale = min(664/(right-left), 1000/(bottom-top))
    plot_top = 114
    plot_height = math.ceil((bottom-top)*scale)
    footer = plot_top+plot_height+26
    note_lines = []
    for note in [*trigger_notes, *warnings]:
        # Wrap long modded names rather than hiding their identity in the PNG.
        while len(note) > 85:
            note_lines.append(note[:85])
            note = note[85:]
        note_lines.append(note)
    height = footer+math.ceil(len(legends)/3)*23+len(note_lines)*19+74
    canvas = RasterCanvas(736, height, COLORS["background"], 2)
    font = ImageFont.load_default(size=13)
    small = ImageFont.load_default(size=12)
    title_font = ImageFont.load_default(size=22)
    symbol_font = ImageFont.load_default(size=11)

    def point(x, y):
        return (36+(x-left)*scale, plot_top+(y-top)*scale)

    def line(points, color, width=1):
        canvas.line([point(x, y) for x, y in points], fill=color, width=width)

    def box(x, y, width, height, fill=None, outline=None, stroke=1):
        canvas.rectangle([point(x, y), point(x+width, y+height)],
                         fill=fill, outline=outline, width=stroke)

    def label(x, y, text, color=COLORS["ink"]):
        canvas.text(point(x, y), text, font=symbol_font, fill=color, anchor="mm")

    def dotted(points, color):
        for start, end in zip(points, points[1:]):
            length = math.dist(start, end)
            if not length:
                continue
            for offset in range(0, math.ceil(length*scale), 9):
                first = min(offset/scale/length, 1)
                last = min((offset+4)/scale/length, 1)
                line([tuple(start[i]+(end[i]-start[i])*fraction for i in range(2))
                      for fraction in (first, last)], color)

    def diamond(x, y, radius, color, text=""):
        canvas.polygon([point(x, y-radius), point(x+radius, y),
                        point(x, y+radius), point(x-radius, y)], fill=color)
        if text:
            label(x, y, text, COLORS["background"])

    def arrow(x, y, dx, dy, color):
        line([(x, y), (x+dx, y+dy)], color, 2)
        length = math.hypot(dx, dy)
        unit_x, unit_y = dx/length, dy/length
        tip = (x+dx, y+dy)
        line([(tip[0]-unit_x*4-unit_y*3, tip[1]-unit_y*4+unit_x*3), tip,
              (tip[0]-unit_x*4+unit_y*3, tip[1]-unit_y*4-unit_x*3)], color, 2)

    map_title = "Forsaken City A-side" if layout["title"] == "1-ForsakenCity" else layout["title"]
    title = f"{map_title} | {room['name']}"
    while title_font.getlength(title) > 680:
        title = title[:-4] + "..."
    canvas.text((28, 14), title, font=title_font, fill=COLORS["ink"])
    canvas.text((28, 47), f"{room['w']} x {room['h']} game px | "
                f"{len(entities)} objects | {len(triggers)} triggers | 8 px tiles",
                font=font, fill=COLORS["muted"])
    canvas.text((28, 70), "Saved geometry and nodes; schematic symbols, not exact hitboxes",
                font=small, fill=COLORS["muted"])
    box(0, 0, room["w"], room["h"], fill="#191e25")
    hidden_regions = [entity for entity in entities if symbol_kind(entity["type"]) == "fakeWall"]
    for row_index, row in enumerate(room["tiles"]):
        for column, tile in enumerate(row):
            if tile not in {"0", " "}:
                box(column*8, row_index*8, 8, 8, fill="#667280", outline="#505c69", stroke=0.4)
    # Reveal hidden passages in the preview without changing source tile data.
    for hidden in hidden_regions:
        box(hidden["x"], hidden["y"], hidden["w"], hidden["h"], fill="#191e25")
    for x in range(0, room["w"]+1, 64):
        canvas.text(point(x, -8), str(x), font=small, fill=COLORS["muted"], anchor="mm")
    for y in range(0, room["h"]+1, 64):
        px, py = point(0, y)
        canvas.text((px-8, py), str(y), font=small, fill=COLORS["muted"], anchor="rm")
    for trigger in triggers:
        x, y, w, h = (trigger[key] for key in ("x", "y", "w", "h"))
        dotted([(x, y), (x+w, y), (x+w, y+h), (x, y+h), (x, y)], "#e0a1ef")
        if id(trigger) in trigger_tags:
            label(x+w/2, y+min(h/2, 8), trigger_tags[id(trigger)], "#e0a1ef")
        if trigger.get("nodes"):
            nodes = [(x+w/2, y+h/2), *trigger["nodes"]]
            dotted(nodes, "#e0a1ef")
            for nx, ny in trigger["nodes"]:
                diamond(nx, ny, 5, "#e0a1ef", "R")
    # Paths precede objects so endpoints do not hide their owning blocks.
    for entity in entities:
        if entity.get("nodes"):
            nodes = node_points(entity)
            dotted(nodes, "#c5a4e5")
            for nx, ny in nodes[1:]:
                px, py = point(nx, ny)
                canvas.ellipse((px-4, py-4, px+4, py+4), outline="#c5a4e5", width=1)
            if entity["type"] == "zipMover":
                for nx, ny in entity["nodes"]:
                    dotted([(nx, ny), (nx+entity["w"], ny),
                            (nx+entity["w"], ny+entity["h"]),
                            (nx, ny+entity["h"]), (nx, ny)], "#eab370")
    # Blocks precede smaller objects so a hidden collectible remains visible.
    def paint_order(entity):
        if entity["type"] in BLOCK_LABELS:
            return 0
        if entity["type"] in {"player", "checkpoint"}:
            return 2
        return 1

    for entity in sorted(entities, key=paint_order):
        kind = entity["type"]
        group = symbol_kind(kind)
        x, y, w, h = (entity[key] for key in ("x", "y", "w", "h"))
        props = entity["properties"]
        color = LEGEND.get(group, ("", "#f8d78d"))[1]
        sprite_data = object_sprite(entity)
        if group == "fakeWall":
            continue
        elif group == "spikes":
            sprites = spike_sprites(entity)
            if sprites:
                for sprite, sx, sy in sprites:
                    canvas.sprite(sprite, point(sx, sy), scale)
            else:
                sprite_warnings.append(f"Schematic spike fallback: {props.get('type', 'default')}")
                for triangle in spike_triangles(entity):
                    canvas.polygon([point(*vertex) for vertex in triangle], fill=color)
        elif sprite_data:
            sprite, sx, sy = sprite_data
            canvas.sprite(sprite, point(sx, sy), scale)
        elif kind in BLOCK_LABELS:
            w, h = w or 8, h or 8
            color = ("#49aaf0", "#f049be", "#fcdc3a", "#38e04e")[int(props.get("index", 0)) % 4] if kind == "cassetteBlock" else color
            fill = color if kind == "cassetteBlock" else "#333642"
            box(x, y, w, h, fill=fill, outline=color, stroke=2)
            code = BLOCK_LABELS[kind] + (str(props.get("index", 0)) if kind == "cassetteBlock" else "")
            if kind != "cassetteBlock":
                label(x+w/2, y+h/2, code, color)
            if kind == "moveBlock":
                dx, dy = {"Left": (-8, 0), "Right": (8, 0),
                          "Up": (0, -8), "Down": (0, 8)}.get(entity.get("direction"), (0, 0))
                if dx or dy:
                    arrow(x+w/2, y+h/2+8, dx, dy, color)
        elif kind == "crumbleBlock":
            box(x, y, w or 8, 8, fill="#554735", outline=color)
            for offset in range(6, int(w or 8), 8):
                line([(x+offset, y), (x+offset-3, y+4), (x+offset, y+8)], COLORS["background"])
        elif kind == "jumpThru":
            line([(x, y), (x+w, y)], color, 3)
        elif group == "spring":
            dx, dy = {"spring": (0, -12), "wallSpringLeft": (12, 0),
                      "wallSpringRight": (-12, 0)}[kind]
            arrow(x, y, dx, dy, color)
            line([(x-6, y), (x+6, y)] if dy else [(x, y-6), (x, y+6)], color, 3)
        elif kind == "player":
            canvas.anchor_marker(point(x, y), kind, 7, color, COLORS["background"], 11)
        elif kind == "refill":
            texture = "objects/refillTwo/idle00" if entity.get("twoDash") else "objects/refill/idle00"
            sprite = load_sprite(texture)
            if sprite is None:
                raise FileNotFoundError(f"Required refill sprite missing: {texture}")
            canvas.sprite(sprite, point(x-sprite.width/2, y-sprite.height/2), scale)
        elif kind in {"checkpoint", "strawberry", "goldenBerry"}:
            code = {"checkpoint": "C", "strawberry": "B", "goldenBerry": "G", "refill": "R"}[kind]
            if kind == "checkpoint":
                canvas.anchor_marker(point(x, y), kind, max(6*scale, 8), color, COLORS["background"], 11)
            else:
                diamond(x, y, max(6, 8/scale), color, code)
            if kind == "strawberry" and props.get("winged"):
                line([(x-12, y-4), (x-8, y), (x+8, y), (x+12, y-4)], color)
        elif kind == "cassette":
            box(x-9, y-6, 18, 12, fill=color, outline=COLORS["ink"])
            for delta in (-4, 4):
                px, py = point(x+delta, y)
                canvas.ellipse((px-2, py-2, px+2, py+2), fill=COLORS["background"])
        elif kind == "spinner":
            diamond(x, y, 5, color)
            line([(x-5, y-5), (x+5, y+5)], color)
            line([(x-5, y+5), (x+5, y-5)], color)
        elif kind in {"booster", "badelineBoost"}:
            color = "#ff6575" if kind == "booster" and entity.get("red") else color
            px, py = point(x, y)
            radius = max(9, 8*scale)
            canvas.ellipse((px-radius, py-radius, px+radius, py+radius),
                           fill=COLORS["background"], outline=color, width=2)
            label(x, y, "BB" if kind == "badelineBoost" else "O", color)
        elif kind == "cloud":
            box(x-16, y-4, 32, 8, fill=color)
        else:
            box(x, y, w or 8, h or 8, outline=color)
            label(x+(w or 8)/2, y+(h or 8)/2, unknown_tags[id(entity)], color)
    for edge in styled_edges([room], analyze_boundaries(layout["rooms"])):
        if edge["side"] == "left":
            points = [(edge["axis"]-room["x"], edge["start"]-room["y"]),
                      (edge["axis"]-room["x"], edge["end"]-room["y"])]
        else:
            points = [(edge["start"]-room["x"], edge["axis"]-room["y"]),
                      (edge["end"]-room["x"], edge["axis"]-room["y"])]
        line(points, COLORS[edge["kind"]], 1.5)
    for index, (text, color) in enumerate(legends):
        canvas.text((28+(index % 3)*233, footer+(index//3)*23), text,
                    font=small, fill=color)
    cursor = footer+math.ceil(len(legends)/3)*23+8
    for note in note_lines:
        canvas.text((28, cursor), note, font=small, fill=COLORS["ink"])
        cursor += 19
    canvas.text((28, cursor+4), "Green edge: candidate crossing | Red edge: unpaired air", font=small, fill=COLORS["muted"])
    canvas.text((28, cursor+25), f"Map SHA-256: {source_hash[:16]}... | Decorations omitted", font=small, fill=COLORS["muted"])
    metadata = {
        "room": room["name"], "world_bounds": [room["x"], room["y"], room["w"], room["h"]],
        "map_sha256": source_hash, "image_size": list(canvas.image.size),
        "entities": entities, "triggers": triggers, "unknown_entities": warnings,
        "sprite_warnings": sorted(set(sprite_warnings)),
        "trigger_notes": trigger_notes, "entity_counts": dict(Counter(e["type"] for e in entities)),
        "solid_tile_count": sum(tile not in {"0", " "} for row in room["tiles"] for tile in row),
        "excluded_entity_counts": dict(Counter(e["type"] for e in room["entities"] if e["type"] in DECORATIVE)),
        "excluded_trigger_counts": dict(Counter(t["type"] for t in room["triggers"] if t["type"] in VISUAL_TRIGGERS)),
        "limitations": ["Schematic symbols are not exact hitboxes or dynamic state.",
                        "Unknown objects and unclassified triggers are retained, not interpreted.",
                        "Saved node paths need not represent traversable movement."]}
    with BytesIO() as stream:
        canvas.image.save(stream, format="PNG")
        return stream.getvalue(), metadata


def make_room_result(workspace: Path, room_name: str, map_path: str = "", source: str = "mod") -> ToolResult:
    """Read one authorized map and return a room PNG, metadata, and source hash."""
    path = resolve_overview_source(workspace, map_path, source)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    layout = extract_layout(cb.read_map(path), path.stem)
    png, metadata = render_room(layout, room_name, before)
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise RuntimeError("Map changed while rendering; request another preview.")
    metadata.update({"source": str(path), "png_sha256": hashlib.sha256(png).hexdigest()})
    return ToolResult(content=[
        TextContent(type="text", text=f"{metadata['room']}: {len(metadata['entities'])} objects, "
                    f"{len(metadata['triggers'])} triggers; source unchanged. "
                    f"{len(metadata['unknown_entities'])} unknown objects retained. SHA-256 {before}."),
        ImageContent(type="image", mimeType="image/png", data=base64.b64encode(png).decode("ascii")),
    ], structured_content=metadata)
