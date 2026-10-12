"""Infer browsing order from saved geometry and spawns, for every map.

Touching rectangles do not establish gameplay reachability. Curated chapter
orders are test references only and are never read by this module.
"""

from collections import Counter
import heapq
from itertools import combinations
import math
import re

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
    tokens = tuple((0, int(part)) if re.fullmatch(r"-?\d+", part)
                   else (1, part) for part in parts if part)
    return phase, tokens, name


def shared_boundary(first: dict, second: dict):
    """Return a touching edge segment in world pixels, or None.

    Require at least one tile of overlap. Corners, gaps, and overlapping room
    interiors do not establish adjacency. Ignore solid tiles because moving
    entities and scripts can open routes that static tiles conceal.
    """
    horizontal = (max(first["x"], second["x"]),
                  min(first["x"] + first["w"], second["x"] + second["w"]))
    vertical = (max(first["y"], second["y"]),
                min(first["y"] + first["h"], second["y"] + second["h"]))
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


def order_rooms(layout: dict, source: str) -> tuple[list[dict], dict]:
    """Infer an order while preserving every supplied room exactly once.

    Args:
        layout: Extracted names, world-pixel rectangles, and entities. Name-only
            rooms are retained with the natural-name fallback.
        source: Reported provenance; vanilla and mod use identical logic.

    Returns:
        Original room objects in browsing order and inference evidence. Each
        component starts at a beginning label, a non-ending golden berry room,
        or the lowest natural name. A spawn-weighted shortest-path tree groups
        smaller branches before the longer continuation. No files or inputs
        are modified. Scripts and alternate branch orders remain unverified.
    """
    rooms = layout["rooms"]
    names = [str(room.get("name", "Unnamed")) for room in rooms]
    keys = [room_name_key(name) for name in names]
    usable = [all(isinstance(room.get(field), (int, float))
                  and math.isfinite(room[field]) for field in ("x", "y", "w", "h"))
              and room["w"] > 0 and room["h"] > 0 for room in rooms]
    neighbors = [[] for _ in rooms]
    for first, second in combinations(range(len(rooms)), 2):
        if not usable[first] or not usable[second]:
            continue
        boundary = shared_boundary(rooms[first], rooms[second])
        if boundary:
            neighbors[first].append((second, entry_cost(rooms[second], boundary)))
            neighbors[second].append((first, entry_cost(rooms[first], boundary)))

    def seed_key(index):
        beginning = keys[index][0] == 0
        golden = keys[index][0] != 2 and any(
            entity.get("type") == "goldenBerry"
            for entity in rooms[index].get("entities", []))
        priority = 0 if beginning else 1 if golden else 2
        return priority, keys[index], index

    remaining = set(range(len(rooms)))
    ordered_indices = []
    components = []
    parent_evidence = []
    while remaining:
        root = min(remaining, key=seed_key)
        distances = {root: 0.0}
        parents = {}
        queue = [(0.0, keys[root], root)]
        while queue:
            distance, _, current = heapq.heappop(queue)
            if distance != distances[current]:
                continue
            for target, cost in sorted(neighbors[current], key=lambda item: keys[item[0]]):
                if target not in remaining:
                    continue
                candidate = distance + cost
                if candidate < distances.get(target, math.inf):
                    distances[target] = candidate
                    parents[target] = current
                    heapq.heappush(queue, (candidate, keys[target], target))
        children = {index: [] for index in distances}
        for child, parent in parents.items():
            children[parent].append(child)
            parent_evidence.append({"room": names[child], "parent": names[parent]})
        # Positive path costs put children after parents. Count subtrees
        # backwards without recursion, including very long custom maps.
        sizes = {index: 1 for index in distances}
        for index in sorted(distances, key=distances.get, reverse=True):
            if index in parents:
                sizes[parents[index]] += sizes[index]
        stack = [root]
        while stack:
            current = stack.pop()
            ordered_indices.append(current)
            branches = sorted(children[current], key=lambda index: (sizes[index], keys[index]))
            stack.extend(reversed(branches))
        components.append({"start": names[root], "room_count": len(distances)})
        remaining.difference_update(distances)

    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    return [rooms[index] for index in ordered_indices], {
        "basis": "Inferred spawn-weighted room adjacency; progression unverified",
        "algorithm": "spawn-adjacency-v1", "source": source,
        "room_count": len(rooms), "components": components,
        "candidate_links": sum(len(items) for items in neighbors) // 2,
        "parent_links": parent_evidence,
        "rooms_without_geometry": [names[index] for index in range(len(rooms)) if not usable[index]],
        "rooms_without_spawns": [names[index] for index in range(len(rooms))
                                 if usable[index] and not spawn_anchor(rooms[index])[2]],
        "duplicate_names": duplicates,
        "limitations": [
            "Touching rectangles are candidates, not verified traversable passages.",
            "The first saved spawn may not be the actual gameplay entrance.",
            "Scripts, teleports, and alternate branch orders are not inferred.",
            "Disconnected components and missing geometry use name conventions.",
        ],
    }
