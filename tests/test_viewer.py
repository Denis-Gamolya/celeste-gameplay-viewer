"""Focused checks for map preservation, filtering, and embedded data safety."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from celeste_gameplay_viewer import viewer


def make_map(tiles="\n1"):
    return {
        "__children": [
            {
                "__name": "levels",
                "__children": [
                    {
                        "__name": "level",
                        "name": "test",
                        "x": -80,
                        "y": 32,
                        "width": 16,
                        "height": 24,
                        "__children": [
                            {"__name": "solids", "innerText": tiles},
                            {
                                "__name": "entities",
                                "__children": [
                                    {"__name": "lamp"},
                                    {
                                        "__name": "Custom/unknown",
                                        "x": 4,
                                        "y": 8,
                                        "__children": [
                                            {
                                                "__name": "node",
                                                "x": 32,
                                                "y": 48,
                                            }
                                        ],
                                    },
                                ],
                            },
                            {
                                "__name": "triggers",
                                "__children": [
                                    {"__name": "colorGradeTrigger"},
                                    {
                                        "__name": "windAttackTrigger",
                                        "width": 8,
                                        "height": 8,
                                    },
                                    {
                                        "__name": "Custom/unknownTrigger",
                                        "width": 8,
                                        "height": 8,
                                    },
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }


class ViewerTests(unittest.TestCase):
    def test_partial_edge_tiles_preserve_exact_room_dimensions(self):
        data = make_map("111\n101\n111")
        raw_room = data["__children"][0]["__children"][0]
        raw_room["width"] = 18
        raw_room["height"] = 22
        room = viewer.extract_layout(data, "partial tiles")["rooms"][0]
        self.assertEqual((room["w"], room["h"]), (18, 22))
        self.assertEqual(room["tiles"], ["111", "101", "111"])

    def test_blank_rows_and_trailing_air_keep_their_positions(self):
        layout = viewer.extract_layout(make_map(), "test")
        self.assertEqual(layout["rooms"][0]["tiles"], ["00", "10", "00"])

    def test_unknown_objects_are_preserved_and_visuals_excluded(self):
        layout = viewer.extract_layout(make_map(), "test")
        room = layout["rooms"][0]
        self.assertEqual(len(room["entities"]), 1)
        self.assertEqual(room["entities"][0]["nodes"], [[32, 48]])
        self.assertEqual(
            [t["verified"] for t in room["triggers"]], [True, False]
        )
        self.assertEqual(len(layout["warnings"]), 2)
        self.assertEqual(layout["excluded_entities"], {"lamp": 1})

    def test_script_like_names_cannot_escape_embedded_json(self):
        layout = viewer.extract_layout(
            make_map(), "</script><script>alert(1)</script>"
        )
        fragment = viewer.make_fragment(layout, "testid")
        self.assertNotIn("</script><script>alert(1)", fragment)
        self.assertIn("\\u003c/script\\u003e", fragment)
        self.assertEqual(fragment.count("</script>"), 1)

    def test_map_path_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "mod"
            workspace.mkdir()
            (root / "outside.bin").write_bytes(b"outside")
            with self.assertRaises(ValueError):
                viewer.resolve_map(workspace, "../outside.bin")

    def test_empty_and_oversized_tile_maps_fail_clearly(self):
        with self.assertRaises(ValueError):
            viewer.extract_layout({}, "empty")
        with self.assertRaises(ValueError):
            viewer.extract_layout(make_map("111"), "wide")

    def test_render_writes_unique_outputs_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "mod"
            maps = workspace / "Maps"
            maps.mkdir(parents=True)
            source = maps / "example.bin"
            source.write_bytes(b"unchanged source")
            with patch.object(viewer.cb, "read_map", return_value=make_map()):
                first = viewer.render_map(workspace, root / "output")
                second = viewer.render_map(workspace, root / "output")
                with self.assertRaises(ValueError):
                    viewer.render_map(workspace, workspace / "output")
            self.assertEqual(source.read_bytes(), b"unchanged source")
            self.assertNotEqual(first["html_path"], second["html_path"])
            self.assertTrue(Path(first["fragment_path"]).is_file())
            self.assertEqual(first["room_count"], 1)

    def test_autodiscovery_rejects_ambiguous_map_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            maps = root / "Maps"
            maps.mkdir()
            (maps / "one.bin").touch()
            (maps / "two.bin").touch()
            with self.assertRaisesRegex(ValueError, "found 2 maps"):
                viewer.resolve_map(root)


if __name__ == "__main__":
    unittest.main()
