"""Checks for preserved source geometry, filtering, and explicit unknowns."""

import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image

from celeste_gameplay_viewer.raster import RasterCanvas
from celeste_gameplay_viewer.room_view import (
    node_points,
    render_room,
    select_room,
    spike_triangles,
)
from celeste_gameplay_viewer.viewer import extract_layout


def sample_map():
    """Use real binary-element shapes, including respawn nodes and properties."""
    return {
        "__children": [
            {
                "__name": "levels",
                "__children": [
                    {
                        "__name": "level",
                        "name": "lvl_test",
                        "x": -160,
                        "y": 80,
                        "width": 320,
                        "height": 184,
                        "__children": [
                            {"__name": "solids", "innerText": "11\n1"},
                            {
                                "__name": "entities",
                                "__children": [
                                    {"__name": "wire", "x": 8, "y": 8},
                                    {
                                        "__name": "player",
                                        "id": 4,
                                        "x": 16,
                                        "y": 32,
                                    },
                                    {
                                        "__name": "zipMover",
                                        "id": 5,
                                        "x": 32,
                                        "y": 64,
                                        "width": 24,
                                        "height": 16,
                                        "__children": [
                                            {
                                                "__name": "node",
                                                "x": 160,
                                                "y": 40,
                                            }
                                        ],
                                    },
                                    {
                                        "__name": "Custom/Unknown",
                                        "id": 6,
                                        "x": 88,
                                        "y": 88,
                                    },
                                ],
                            },
                            {
                                "__name": "triggers",
                                "__children": [
                                    {
                                        "__name": "cameraTargetTrigger",
                                        "x": 0,
                                        "y": 0,
                                    },
                                    {
                                        "__name": "changeRespawnTrigger",
                                        "id": 7,
                                        "x": 32,
                                        "y": 80,
                                        "width": 16,
                                        "height": 24,
                                        "__children": [
                                            {
                                                "__name": "node",
                                                "x": 48,
                                                "y": 96,
                                            }
                                        ],
                                    },
                                    {
                                        "__name": "Custom/UnknownTrigger",
                                        "id": 8,
                                        "x": 56,
                                        "y": 80,
                                        "width": 16,
                                        "height": 24,
                                    },
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }


class RoomViewTests(unittest.TestCase):
    def test_room_lookup_uses_exact_name_or_unambiguous_runtime_alias(self):
        layout = extract_layout(sample_map(), "Fixture")
        self.assertEqual(select_room(layout, "test")["name"], "lvl_test")
        self.assertEqual(select_room(layout, "lvl_test")["name"], "lvl_test")
        with self.assertRaisesRegex(ValueError, "Available: lvl_test"):
            select_room(layout, "missing")

    def test_respawn_nodes_ids_and_attributes_survive_extraction(self):
        layout = extract_layout(sample_map(), "Fixture")
        trigger = layout["rooms"][0]["triggers"][1]
        self.assertEqual(trigger["nodes"], [[48, 96]])
        self.assertEqual(trigger["id"], 7)
        self.assertEqual(trigger["properties"]["height"], 24)

    def test_zip_path_uses_centers_at_both_ends(self):
        layout = extract_layout(sample_map(), "Fixture")
        mover = layout["rooms"][0]["entities"][2]
        self.assertEqual(node_points(mover), [(44, 72), (172, 48)])

    def test_spikes_face_outward_and_keep_saved_run_length(self):
        for direction, axis, expected in [
            ("Up", 1, 12),
            ("Down", 1, 28),
            ("Left", 0, 12),
            ("Right", 0, 28),
        ]:
            with self.subTest(direction=direction):
                triangles = spike_triangles(
                    {
                        "type": "spikes" + direction,
                        "x": 20,
                        "y": 20,
                        "w": 16,
                        "h": 16,
                    }
                )
                self.assertEqual(len(triangles), 2)
                self.assertEqual(triangles[0][1][axis], expected)

    def test_png_preserves_gameplay_and_unknowns_while_omitting_visuals(self):
        layout = extract_layout(sample_map(), "Fixture")
        png, metadata = render_room(layout, "test", "a" * 64)
        self.assertEqual(metadata["world_bounds"], [-160, 80, 320, 184])
        self.assertEqual(metadata["solid_tile_count"], 3)
        self.assertEqual(metadata["excluded_entity_counts"], {"wire": 1})
        self.assertEqual(
            metadata["excluded_trigger_counts"], {"cameraTargetTrigger": 1}
        )
        self.assertEqual(
            metadata["entity_counts"],
            {"player": 1, "zipMover": 1, "Custom/Unknown": 1},
        )
        self.assertIn("Custom/Unknown", metadata["unknown_entities"][0])
        self.assertIn("behavior unverified", metadata["trigger_notes"][0])
        self.assertEqual(metadata["triggers"][0]["nodes"], [[48, 96]])
        self.assertEqual(png, render_room(layout, "test", "a" * 64)[0])
        with Image.open(BytesIO(png)) as picture:
            self.assertEqual(picture.size[0], 1472)
            picture.verify()

    def test_respawn_outline_and_nodes_remain_without_labels(self):
        layout = extract_layout(sample_map(), "Fixture")
        with (
            patch.object(
                RasterCanvas,
                "text",
                autospec=True,
                side_effect=RasterCanvas.text,
            ) as draw_text,
            patch.object(
                RasterCanvas,
                "line",
                autospec=True,
                side_effect=RasterCanvas.line,
            ) as draw_line,
        ):
            _, metadata = render_room(layout, "test", "a" * 64)
        text = [call.args[2] for call in draw_text.call_args_list]
        self.assertFalse(any("changeRespawn" in value for value in text))
        self.assertIn("T1", text)
        self.assertNotIn("T2", text)
        self.assertEqual(
            metadata["trigger_notes"],
            ["T1: Custom/UnknownTrigger [behavior unverified]"],
        )
        self.assertEqual(metadata["triggers"][0]["nodes"], [[48, 96]])
        outlines = [
            call
            for call in draw_line.call_args_list
            if call.kwargs.get("fill") == "#e0a1ef"
        ]
        self.assertTrue(outlines)

    def test_collectible_inside_later_block_stays_visible(self):
        raw = sample_map()
        entities = raw["__children"][0]["__children"][0]["__children"][1]
        entities["__children"] = [
            {"__name": "strawberry", "id": 1, "x": 80, "y": 80},
            {
                "__name": "dashBlock",
                "id": 2,
                "x": 64,
                "y": 64,
                "width": 48,
                "height": 48,
            },
            {
                "__name": "fakeWall",
                "id": 3,
                "x": 56,
                "y": 56,
                "width": 64,
                "height": 64,
            },
        ]
        png, _ = render_room(extract_layout(raw, "Fixture"), "test", "a" * 64)
        with Image.open(BytesIO(png)) as picture:
            # Inspect only the room plot, excluding the berry-colored legend.
            colors = picture.crop((72, 228, 1400, 900)).getcolors(1_000_000)
            self.assertTrue(
                any(
                    color[0] > 180
                    and color[1] < 100
                    and color[2] < 130
                    and count > 100
                    for count, color in colors
                )
            )


if __name__ == "__main__":
    unittest.main()
