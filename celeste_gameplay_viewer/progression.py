"""Infer browsing order from saved geometry and spawns, for every map.

Touching rectangles do not establish gameplay reachability. Curated chapter
orders are test references only and are never read by this module.
"""

import heapq
import math
import re
from collections import Counter
from dataclasses import dataclass
from itertools import combinations

TILE_SIZE = 8


def room_name_key(name: str) -> tuple:
    """Sort numeric fragments naturally, including a leading negative ID.

    A hyphen inside ``a-02`` separates tokens rather than negating the number.
    Beginning and ending labels help order disconnected components.
    """
    name = name.removeprefix("lvl_").casefold()
    if name.startswith(("start", "intro", "begin", "outside")):
        phase = 0
    elif name.startswith(("end", "after", "credits", "space")):
        phase = 2
    else:
        phase = 1
    parts = re.split(r"(\d+)", name)
    if name.startswith("-") and len(parts) > 1:
        parts[0] = ""
        parts[1] = "-" + parts[1]
    tokens = tuple(
        (0, int(part)) if re.fullmatch(r"-?\d+", part) else (1, part)
        for part in parts
        if part
    )
    return phase, tokens, name


def shared_boundary(first: dict, second: dict):
    """Return a touching edge segment in world pixels, or None.

    Require at least one tile of overlap. Corners, gaps, and overlapping room
    interiors do not establish adjacency. Ignore solid tiles because moving
    entities and scripts can open routes that static tiles conceal.
    """
    horizontal = (
        max(first["x"], second["x"]),
        min(first["x"] + first["w"], second["x"] + second["w"]),
    )
    vertical = (
        max(first["y"], second["y"]),
        min(first["y"] + first["h"], second["y"] + second["h"]),
    )
    if first["x"] + first["w"] == second["x"]:
        if vertical[1] - vertical[0] >= TILE_SIZE:
            return second["x"], vertical[0], second["x"], vertical[1]
    if second["x"] + second["w"] == first["x"]:
        if vertical[1] - vertical[0] >= TILE_SIZE:
            return first["x"], vertical[0], first["x"], vertical[1]
    if first["y"] + first["h"] == second["y"]:
        if horizontal[1] - horizontal[0] >= TILE_SIZE:
            return horizontal[0], second["y"], horizontal[1], second["y"]
    if second["y"] + second["h"] == first["y"]:
        if horizontal[1] - horizontal[0] >= TILE_SIZE:
            return horizontal[0], first["y"], horizontal[1], first["y"]
    return None


def spawn_anchor(room: dict) -> tuple[float, float, bool]:
    """Return the first saved player spawn in world pixels, or the room center.

    The Boolean distinguishes a saved spawn from the geometric fallback;
    neither guarantees the actual entrance.
    """
    for entity in room.get("entities", []):
        if entity.get("type") == "player":
            return room["x"] + entity["x"], room["y"] + entity["y"], True
    return room["x"] + room["w"] / 2, room["y"] + room["h"] / 2, False


def entry_cost(target: dict, boundary: tuple) -> float:
    """Prefer entering near the target spawn; return a positive heuristic cost.

    Cost is one step plus spawn-to-edge distance in tile widths. Positive
    costs allow Dijkstra's algorithm to build a cycle-free browsing tree.
    """
    spawn_x, spawn_y, _ = spawn_anchor(target)
    left, top, right, bottom = boundary
    nearest_x = max(left, min(right, spawn_x))
    nearest_y = max(top, min(bottom, spawn_y))
    return 1 + math.hypot(spawn_x - nearest_x, spawn_y - nearest_y) / TILE_SIZE


@dataclass
class RoomGraph:
    """Saved room identity and directed, spawn-weighted adjacency by index.

    Indices preserve distinct room objects even when their stored names collide.
    Name keys determine stable ties; geometry flags keep incomplete rooms visible.
    """

    names: list[str]
    name_keys: list[tuple]
    has_geometry: list[bool]
    connections: list[list[tuple[int, float]]]


@dataclass
class BrowsingTree:
    """One connected component rooted at an inferred starting room."""

    start: int
    distances: dict[int, float]
    parents: dict[int, int]


def _has_room_geometry(room: dict) -> bool:
    """Accept finite world coordinates and positive dimensions."""
    numeric_bounds = all(
        isinstance(room.get(field), (int, float))
        and math.isfinite(room[field])
        for field in ("x", "y", "w", "h")
    )
    return numeric_bounds and room["w"] > 0 and room["h"] > 0


def build_room_graph(rooms: list[dict]) -> RoomGraph:
    """Connect touching rectangles and score each destination's entrance."""
    names = [str(room.get("name", "Unnamed")) for room in rooms]
    name_keys = [room_name_key(name) for name in names]
    has_geometry = [_has_room_geometry(room) for room in rooms]
    connections = [[] for _ in rooms]
    for first, second in combinations(range(len(rooms)), 2):
        if not has_geometry[first] or not has_geometry[second]:
            continue
        boundary = shared_boundary(rooms[first], rooms[second])
        if boundary is not None:
            connections[first].append(
                (second, entry_cost(rooms[second], boundary))
            )
            connections[second].append(
                (first, entry_cost(rooms[first], boundary))
            )
    return RoomGraph(names, name_keys, has_geometry, connections)


def choose_component_start(
    rooms: list[dict], graph: RoomGraph, available: set[int]
) -> int:
    """Prefer beginning labels, then non-ending golden berries, then names."""

    def seed_key(index):
        beginning = graph.name_keys[index][0] == 0
        golden = graph.name_keys[index][0] != 2 and any(
            entity.get("type") == "goldenBerry"
            for entity in rooms[index].get("entities", [])
        )
        priority = 0 if beginning else 1 if golden else 2
        return priority, graph.name_keys[index], index

    return min(available, key=seed_key)


def build_browsing_tree(
    graph: RoomGraph, available: set[int], start: int
) -> BrowsingTree:
    """Run Dijkstra over remaining rooms without interpreting gameplay physics.

    Positive costs guarantee parent paths are cycle-free. Stale heap entries
    are discarded when a better path was already found.
    """
    distances = {start: 0.0}
    parents = {}
    queue = [(0.0, graph.name_keys[start], start)]
    while queue:
        distance, _, current = heapq.heappop(queue)
        if distance != distances[current]:
            continue
        connections = sorted(
            graph.connections[current],
            key=lambda item: graph.name_keys[item[0]],
        )
        for target, cost in connections:
            if target not in available:
                continue
            candidate = distance + cost
            if candidate < distances.get(target, math.inf):
                distances[target] = candidate
                parents[target] = current
                heapq.heappush(
                    queue, (candidate, graph.name_keys[target], target)
                )
    return BrowsingTree(start, distances, parents)


def browse_tree(tree: BrowsingTree, name_keys: list[tuple]) -> list[int]:
    """Return parent-first depth-first order, visiting smaller branches first."""
    children = {index: [] for index in tree.distances}
    for child, parent in tree.parents.items():
        children[parent].append(child)

    # Positive path costs put children after parents. Count backwards and
    # traverse iteratively so long custom maps do not hit a recursion limit.
    subtree_sizes = {index: 1 for index in tree.distances}
    for index in sorted(tree.distances, key=tree.distances.get, reverse=True):
        if index in tree.parents:
            subtree_sizes[tree.parents[index]] += subtree_sizes[index]
    ordered = []
    stack = [tree.start]
    while stack:
        current = stack.pop()
        ordered.append(current)
        branches = sorted(
            children[current],
            key=lambda index: (subtree_sizes[index], name_keys[index]),
        )
        stack.extend(reversed(branches))
    return ordered


def describe_order(
    rooms: list[dict],
    graph: RoomGraph,
    components: list[dict],
    parent_links: list[dict],
    source: str,
) -> dict:
    """Report evidence and missing information without claiming a playable route."""
    duplicates = sorted(
        name for name, count in Counter(graph.names).items() if count > 1
    )
    return {
        "basis": "Inferred spawn-weighted room adjacency; progression unverified",
        "algorithm": "spawn-adjacency-v1",
        "source": source,
        "room_count": len(rooms),
        "components": components,
        "candidate_links": sum(len(items) for items in graph.connections) // 2,
        "parent_links": parent_links,
        "rooms_without_geometry": [
            name
            for name, usable in zip(graph.names, graph.has_geometry)
            if not usable
        ],
        "rooms_without_spawns": [
            graph.names[index]
            for index, room in enumerate(rooms)
            if graph.has_geometry[index] and not spawn_anchor(room)[2]
        ],
        "duplicate_names": duplicates,
        "limitations": [
            "Touching rectangles are candidates, not verified traversable passages.",
            "The first saved spawn may not be the actual gameplay entrance.",
            "Scripts, teleports, and alternate branch orders are not inferred.",
            "Disconnected components and missing geometry use name conventions.",
        ],
    }


def order_rooms(layout: dict, source: str) -> tuple[list[dict], dict]:
    """Infer browsing order while preserving every supplied room exactly once.

    Args:
        layout: Extracted room names, world-pixel rectangles, and entities.
            Incomplete rooms remain visible through the natural-name fallback.
        source: Reported provenance; vanilla and mod use identical rules.

    Returns:
        Original room objects in browsing order and evidence explaining it.
        This controls dropdown and Previous/Next order, not map placement or
        click-to-room identity. Does not mutate the layout or write files.
    """
    rooms = layout["rooms"]
    graph = build_room_graph(rooms)
    available = set(range(len(rooms)))
    ordered_indices = []
    components = []
    parent_links = []
    while available:
        start = choose_component_start(rooms, graph, available)
        tree = build_browsing_tree(graph, available, start)
        ordered_indices.extend(browse_tree(tree, graph.name_keys))
        components.append(
            {"start": graph.names[start], "room_count": len(tree.distances)}
        )
        parent_links.extend(
            {"room": graph.names[child], "parent": graph.names[parent]}
            for child, parent in tree.parents.items()
        )
        available.difference_update(tree.distances)
    ordered = [rooms[index] for index in ordered_indices]
    return ordered, describe_order(
        rooms, graph, components, parent_links, source
    )
