"""Inspect saved map data without inferring physics or changing source files."""

from collections import Counter, defaultdict
import hashlib
from itertools import combinations
from pathlib import Path

from .overview import analyze_boundaries, resolve_overview_source
from .room_view import DECORATIVE, GAMEPLAY_TRIGGERS, LEGEND
from .room_view import VISUAL_TRIGGERS, symbol_kind
from .viewer import cb, children, extract_layout

LOENN = "https://github.com/CelestialCartographers/Loenn/blob/master/src/"
NODE_RULES = {
    "zipMover": (1, 1, LOENN + "entities/zip_mover.lua"),
    "changeRespawnTrigger": (0, 1, LOENN + "triggers/change_respawn.lua"),
}


def object_evidence(room: dict, item: dict, section: str, index: int) -> dict:
    """Locate an object in the retained gameplay list using game-pixel coordinates."""
    return {
        "section": section, "retained_object_index": index, "id": item.get("id"),
        "type": item["type"], "local": [item["x"], item["y"]],
        "world": [room["x"] + item["x"], room["y"] + item["y"]],
    }


def inspect_map_data(map_data: dict, title: str, source_hash: str) -> dict:
    """Return deterministic findings, room inventory, and renderer coverage.

    Coordinates are game pixels. Findings identify source room indices as well
    as names, preserving ambiguous duplicate names. Review items require human
    interpretation; observations are not defects. Raises ValueError for layouts
    the existing parser cannot represent. Does not mutate input or write files.
    """
    layout = extract_layout(map_data, title)
    rooms = layout["rooms"]
    findings = []
    coverage = []

    def add(code, level, indices, message, evidence, recommendation):
        findings.append({
            "finding_id": f"F{len(findings) + 1:03}",
            "code": code, "level": level,
            "rooms": [rooms[index]["name"] for index in indices],
            "room_indices": indices, "message": message,
            "evidence": evidence, "recommendation": recommendation,
        })

    names = defaultdict(list)
    for index, room in enumerate(rooms):
        names[room["name"]].append(index)
    for name, indices in names.items():
        if len(indices) > 1:
            add("duplicate_room_name", "review", indices,
                f"Stored room name {name!r} occurs {len(indices)} times.",
                {"occurrences": len(indices)},
                "Check room names in Lonn; name-based navigation is ambiguous.")

    for first, second in combinations(range(len(rooms)), 2):
        a, b = rooms[first], rooms[second]
        bounds = [max(a["x"], b["x"]), max(a["y"], b["y"]),
                  min(a["x"] + a["w"], b["x"] + b["w"]),
                  min(a["y"] + a["h"], b["y"] + b["h"])]
        if bounds[0] < bounds[2] and bounds[1] < bounds[3]:
            add("overlapping_rooms", "review", [first, second],
                "Room rectangles overlap with positive area.",
                {"world_bounds": bounds},
                "Check whether this overlap is intentional in the room layout.")

    raw_rooms = cb.get_rooms(map_data)
    inventories = []
    for room_index, room in enumerate(rooms):
        indices = [room_index]
        # Vanilla maps reuse IDs across entity and trigger lists.
        # Inspect each list before decorative filtering, in its own room.
        ids = defaultdict(list)
        for section in ("entities", "triggers"):
            for index, item in enumerate(children(raw_rooms[room_index], section)):
                if item.get("id") is not None:
                    ids[(section, item["id"])].append({
                        "section": section, "object_index": index,
                        "type": item["__name"],
                    })
        for (section, identifier), occurrences in ids.items():
            if len(occurrences) > 1:
                add("duplicate_object_id", "review", indices,
                    f"Object ID {identifier} is reused in this room's {section} list.",
                    {"section": section, "id": identifier, "objects": occurrences},
                    "Inspect the listed objects before changing their IDs.")

        entities = [item for item in room["entities"]
                    if item["type"] not in DECORATIVE]
        triggers = [item for item in room["triggers"]
                    if item["type"] not in VISUAL_TRIGGERS]
        counts = Counter(item["type"] for item in entities)
        if not counts["player"]:
            add("no_saved_spawn", "observation", indices,
                "This room has no saved player spawn marker.", {},
                "Check intended entry/respawn behavior; scripts may supply it.")

        for section, items in (("entities", entities), ("triggers", triggers)):
            noun = "entity" if section == "entities" else "trigger"
            unknown = []
            outside_anchors = []
            outside_nodes = []
            for index, item in enumerate(items):
                evidence = object_evidence(room, item, section, index)
                if ((section == "entities" and symbol_kind(item["type"]) not in LEGEND)
                        or (section == "triggers" and item["type"] not in GAMEPLAY_TRIGGERS)):
                    unknown.append(evidence)
                if not (0 <= item["x"] <= room["w"]
                        and 0 <= item["y"] <= room["h"]):
                    outside_anchors.append(evidence)
                for node_index, (x, y) in enumerate(item["nodes"]):
                    if not (0 <= x <= room["w"] and 0 <= y <= room["h"]):
                        outside_nodes.append({**evidence,
                            "node_index": node_index, "node_local": [x, y],
                            "node_world": [room["x"] + x, room["y"] + y]})
                rule = NODE_RULES.get(item["type"])
                if rule and not rule[0] <= len(item["nodes"]) <= rule[1]:
                    add("node_count_mismatch", "review", indices,
                        f"{item['type']} has {len(item['nodes'])} saved nodes; "
                        f"Lonn defines {rule[0]} to {rule[1]}.",
                        {**evidence, "node_count": len(item["nodes"]),
                         "expected_range": list(rule[:2]), "reference": rule[2]},
                        "Check the node count against this entity's definition.")
            if outside_anchors:
                add("anchors_outside_room", "review", indices,
                    f"Outside {noun} anchors: {len(outside_anchors)}.",
                    {"room_size": [room["w"], room["h"]], "objects": outside_anchors},
                    "Check placement and intended transition behavior. An outside "
                    "anchor does not prove the object's entire area is outside.")
            if outside_nodes:
                add("nodes_outside_room", "observation", indices,
                    f"Saved {noun} nodes outside the room: {len(outside_nodes)}.",
                    {"room_size": [room["w"], room["h"]], "nodes": outside_nodes},
                    "Check the path in the room preview; cross-room motion may be intentional.")
            if unknown:
                coverage.append({
                    "room": room["name"], "room_index": room_index,
                    "kind": "generic_symbols" if section == "entities" else "unclassified_triggers",
                    "objects": unknown,
                })
        inventories.append({
            "name": room["name"], "room_index": room_index,
            "entity_counts": dict(sorted(counts.items())),
            "gameplay_or_unclassified_trigger_count": len(triggers),
        })

    boundaries = analyze_boundaries(rooms)
    adjacency = [set() for _ in rooms]
    for passage in boundaries["candidate_passages"]:
        first, second = passage["room_indices"]
        adjacency[first].add(second)
        adjacency[second].add(first)
    remaining = set(range(len(rooms)))
    components = []
    while remaining:
        pending = [min(remaining)]
        component = set()
        while pending:
            index = pending.pop()
            if index not in component:
                component.add(index)
                pending.extend(adjacency[index] - component)
        remaining -= component
        components.append(sorted(component))

    return {
        "schema_version": 1, "title": title, "map_sha256": source_hash,
        "summary": {
            "room_count": len(rooms), "finding_count": len(findings),
            "review_count": sum(item["level"] == "review" for item in findings),
            "observation_count": sum(item["level"] == "observation" for item in findings),
            "coverage_object_count": sum(len(item["objects"]) for item in coverage),
        },
        "findings": findings, "renderer_coverage": coverage, "rooms": inventories,
        "topology": {
            "candidate_room_links": sum(map(len, adjacency)) // 2,
            "geometric_components": components,
            "unpaired_air_edge_count": len(boundaries["unpaired_air_edges"]),
            "interpretation": "Undirected geometry only. Components do not prove "
                              "reachability, progression, or a broken transition.",
        },
        "limitations": [
            "Findings are saved-data checks, not a playability verdict.",
            "Anchor bounds are inclusive; exact border anchors are not flagged.",
            "Node limits are checked only for zipMover and changeRespawnTrigger.",
            "Unknown renderer coverage is not a map defect.",
            "Physics, hitboxes, spawn safety, scripts, and gameplay reachability are not simulated.",
        ],
    }


def inspect_gameplay_map(workspace: Path, map_path: str = "",
                         source: str = "mod") -> dict:
    """Read one scoped map and return findings with its SHA-256; write nothing.

    Uses the same mod/vanilla path restrictions as previews. Raises on invalid
    paths, malformed layouts, or a source change during inspection.
    """
    path = resolve_overview_source(workspace, map_path, source)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = inspect_map_data(cb.read_map(path), path.stem, before)
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise RuntimeError("Map changed while inspecting; request a new report.")
    return {**result, "source": str(path), "source_kind": source}
