"""Analyze saved tile-edge openings in world game-pixel coordinates.

Candidate passages are nondirectional and do not prove traversability. Styling
uses disjoint spans so special edges do not cover a second regular border.
"""

from itertools import combinations

OPPOSITE_SIDES = {
    "left": "right",
    "right": "left",
    "top": "bottom",
    "bottom": "top",
}


def styled_edges(rooms: list[dict], boundaries: dict) -> list[dict]:
    """Partition shared boundaries into disjoint, singly colored intervals.

    Green passages take priority over red unpaired air, then normal borders.
    Subtract special spans before drawing; no normal stroke is painted under
    a special edge, including a neighbor's solid-facing boundary.
    """
    lines = {}
    for room in rooms:
        for side, axis, start, end in (
            ("left", room["x"], room["y"], room["y"] + room["h"]),
            ("right", room["x"] + room["w"], room["y"], room["y"] + room["h"]),
            ("top", room["y"], room["x"], room["x"] + room["w"]),
            (
                "bottom",
                room["y"] + room["h"],
                room["x"],
                room["x"] + room["w"],
            ),
        ):
            key = ("left" if side in {"left", "right"} else "top", axis)
            lines.setdefault(key, []).append((start, end, "border"))
    for field, kind in (
        ("unpaired_air_edges", "unpaired"),
        ("candidate_passages", "passage"),
    ):
        for edge in boundaries[field]:
            key = (
                "left" if edge["side"] in {"left", "right"} else "top",
                edge["axis"],
            )
            if key in lines:
                lines[key].append((edge["start"], edge["end"], kind))
    segments = []
    rank = {"border": 0, "unpaired": 1, "passage": 2}
    for (side, axis), intervals in sorted(lines.items()):
        points = sorted(
            {point for start, end, _ in intervals for point in (start, end)}
        )
        for start, end in zip(points, points[1:]):
            active = [
                kind
                for low, high, kind in intervals
                if low <= start and end <= high
            ]
            if "border" not in active:
                continue
            kind = max(active, key=rank.__getitem__)
            if (
                segments
                and segments[-1]["side"] == side
                and segments[-1]["axis"] == axis
                and segments[-1]["end"] == start
                and segments[-1]["kind"] == kind
            ):
                segments[-1]["end"] = end
            else:
                segments.append(
                    {
                        "side": side,
                        "axis": axis,
                        "start": start,
                        "end": end,
                        "kind": kind,
                    }
                )
    return segments


def edge_openings(room: dict, index: int) -> list[dict]:
    """Return maximal air intervals along room edges in world pixels.

    Intervals are half-open [start, end). Only air in the solid tile layer
    counts; an interval can still be obstructed or lethal during gameplay.
    """
    tiles = room["tiles"]
    edges = {
        "left": (room["x"], room["y"], [row[0] for row in tiles]),
        "right": (
            room["x"] + room["w"],
            room["y"],
            [row[-1] for row in tiles],
        ),
        "top": (room["y"], room["x"], tiles[0]),
        "bottom": (room["y"] + room["h"], room["x"], tiles[-1]),
    }
    openings = []
    for side, (axis, origin, cells) in edges.items():
        start = None
        for position in range(len(cells) + 1):
            air = position < len(cells) and cells[position] in {"0", " "}
            if air and start is None:
                start = origin + position * 8
            if not air and start is not None:
                openings.append(
                    {
                        "room_index": index,
                        "room": room["name"],
                        "side": side,
                        "axis": axis,
                        "start": start,
                        "end": origin + position * 8,
                    }
                )
                start = None
    return openings


def analyze_boundaries(rooms: list[dict]) -> dict:
    """Find facing air edges with at least eight pixels of overlap.

    Returns nondirectional candidate passages and unmatched air intervals.
    No gap bridging, corner-only links, or named start/end guesses are made.
    Unmatched edges may be death pits, sky, scripted exits, or inaccessible.
    """
    openings = [
        edge
        for index, room in enumerate(rooms)
        for edge in edge_openings(room, index)
    ]
    covered = [[] for _ in openings]
    passages = []
    for (first_index, first), (second_index, second) in combinations(
        enumerate(openings), 2
    ):
        if (
            first["room_index"] == second["room_index"]
            or first["axis"] != second["axis"]
            or OPPOSITE_SIDES[first["side"]] != second["side"]
        ):
            continue
        start = max(first["start"], second["start"])
        end = min(first["end"], second["end"])
        if end - start < 8:
            continue
        passages.append(
            {
                "rooms": [first["room"], second["room"]],
                "room_indices": [first["room_index"], second["room_index"]],
                "side": first["side"],
                "axis": first["axis"],
                "start": start,
                "end": end,
                "width_px": end - start,
            }
        )
        covered[first_index].append((start, end))
        covered[second_index].append((start, end))
    unmatched = []
    for opening, intervals in zip(openings, covered):
        cursor = opening["start"]
        for start, end in sorted(intervals):
            if start > cursor:
                unmatched.append({**opening, "start": cursor, "end": start})
            cursor = max(cursor, end)
        if cursor < opening["end"]:
            unmatched.append({**opening, "start": cursor})
    return {"candidate_passages": passages, "unpaired_air_edges": unmatched}
