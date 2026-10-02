"""Regression checks for boundary candidates, path scope, and PNG stability."""

import base64
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from overview import analyze_boundaries, make_overview_result
from overview import render_overview, resolve_overview_source
from overview import styled_edges


def room(name, x=0, y=0, tiles=None):
    """Build a small room with explicit solid-edge cells for geometry tests."""
    tiles = tiles or ["11", "00", "00", "11"]
    return {"name": name, "x": x, "y": y, "w": len(tiles[0])*8,
            "h": len(tiles)*8, "tiles": tiles,
            "entities": [], "triggers": []}


class BoundaryTests(unittest.TestCase):
    def test_special_edges_replace_regular_edges_on_both_room_sides(self):
        rooms = [room("a"), room("b", 16, 8)]
        edges = styled_edges(rooms, analyze_boundaries(rooms))
        seam = [edge for edge in edges if edge["side"] == "left"
                and edge["axis"] == 16]
        self.assertEqual([(e["start"], e["end"], e["kind"]) for e in seam],
                         [(0, 8, "border"), (8, 16, "unpaired"),
                          (16, 24, "passage"), (24, 32, "unpaired"),
                          (32, 40, "border")])
        for index, edge in enumerate(edges):
            for other in edges[index+1:]:
                if (edge["side"], edge["axis"]) == (other["side"], other["axis"]):
                    self.assertLessEqual(min(edge["end"], other["end"]),
                                         max(edge["start"], other["start"]))

    def test_offset_rooms_share_only_the_overlapping_air_interval(self):
        result = analyze_boundaries([room("a", -16), room("b", 0, 8)])
        self.assertEqual(len(result["candidate_passages"]), 1)
        passage = result["candidate_passages"][0]
        self.assertEqual((passage["axis"], passage["start"], passage["end"]),
                         (0, 16, 24))
        unpaired = [edge for edge in result["unpaired_air_edges"]
                    if edge["room"] == "a" and edge["side"] == "right"]
        self.assertEqual([(edge["start"], edge["end"]) for edge in unpaired],
                         [(8, 16)])

    def test_walls_gaps_corners_and_subtile_slivers_are_not_connections(self):
        first = room("a")
        cases = [room("wall", 16, tiles=["11"]*4),
                 room("gap", 24), room("corner", 16, 32),
                 room("sliver", 16, 12)]
        for other in cases:
            with self.subTest(other=other["name"]):
                self.assertEqual(analyze_boundaries([first, other])[
                    "candidate_passages"], [])

    def test_vertical_crossing_uses_world_x_not_world_y(self):
        first = room("upper", -8, -16, ["10", "10"])
        second = room("lower", 0, 0, ["01", "01"])
        passages = analyze_boundaries([first, second])["candidate_passages"]
        self.assertEqual(len(passages), 1)
        self.assertEqual((passages[0]["side"], passages[0]["axis"],
                          passages[0]["start"], passages[0]["end"]),
                         ("bottom", 0, 0, 8))


class OverviewTests(unittest.TestCase):
    def test_navigation_bounds_match_drawn_rooms_with_negative_coordinates(self):
        layout = {"title": "Bounds", "rooms": [
            room("left", -32, -16), room("right", -16, -8),
        ]}
        _, metadata = render_overview(layout, "a"*64)
        self.assertEqual(metadata["room_bounds"], [
            {"room": "left", "bounds": [228, 516, 2208, 4476]},
            {"room": "right", "bounds": [2208, 1506, 4188, 5466]},
        ])

    def test_navigation_bounds_use_width_limited_scale_and_actual_image_pixels(self):
        layout = {"title": "Wide", "rooms": [
            room("left", -32), room("right", 16),
        ]}
        _, metadata = render_overview(layout, "a"*64)
        self.assertEqual(metadata["room_bounds"], [
            {"room": "left", "bounds": [168, 516, 1188, 2556]},
            {"room": "right", "bounds": [3228, 516, 4248, 2556]},
        ])

    def test_labels_preserve_stored_names_including_vanilla_prefix(self):
        layout = {"title": "Labels", "rooms": [
            room("lvl_10zb"), room("a_01_intro", 32),
        ]}
        _, metadata = render_overview(layout, "a"*64)
        self.assertEqual([label["label"] for label in metadata["label_boxes"]],
                         ["lvl_10zb", "a_01_intro"])

    def test_png_is_deterministic_and_markers_keep_source_coordinates(self):
        first = room("sample", -16, -32)
        first["entities"] = [{"type": "player", "x": 4, "y": 16},
                             {"type": "checkpoint", "x": 8, "y": 16}]
        layout = {"title": "Fixture", "rooms": [first]}
        png, metadata = render_overview(layout, "a"*64)
        self.assertEqual(png, render_overview(layout, "a"*64)[0])
        self.assertEqual(metadata["spawn_count"], 1)
        self.assertEqual(metadata["checkpoint_count"], 1)
        self.assertEqual((metadata["markers"][0]["x"],
                          metadata["markers"][0]["y"]), (-12, -16))
        with Image.open(BytesIO(png)) as image:
            self.assertEqual(image.size[0], 4416)
            image.verify()

    def test_vanilla_scope_is_separate_and_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "Mods" / "MyMod"
            workspace.mkdir(parents=True)
            maps = root / "Content" / "Maps"
            maps.mkdir(parents=True)
            target = maps / "chapter.bin"
            target.touch()
            outside = root / "Content" / "outside.bin"
            outside.touch()
            self.assertEqual(resolve_overview_source(
                workspace, "chapter.bin", "vanilla"), target.resolve())
            with self.assertRaises(ValueError):
                resolve_overview_source(workspace, "../outside.bin", "vanilla")
            with self.assertRaises(ValueError):
                resolve_overview_source(workspace, "", "vanilla")
            with self.assertRaises(ValueError):
                resolve_overview_source(workspace, str(target), "mod")

    def test_real_source_bytes_are_preserved_and_no_preview_file_is_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            maps = root / "Maps"
            maps.mkdir()
            source = maps / "sample.bin"
            source.write_bytes(b"source fixture")
            layout = {"title": "Fixture", "rooms": [room("sample")]}
            with patch("overview.cb.read_map"), patch(
                "overview.extract_layout", return_value=layout
            ):
                result = make_overview_result(root)
            self.assertEqual([block.type for block in result.content],
                             ["text", "image"])
            self.assertTrue(base64.b64decode(result.content[1].data).startswith(
                b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(source.read_bytes(), b"source fixture")
            self.assertEqual(list(root.rglob("*.bin")), [source])
            self.assertEqual(list(root.rglob("*.png")), [])


if __name__ == "__main__":
    unittest.main()
