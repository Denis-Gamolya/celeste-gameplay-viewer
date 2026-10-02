"""Verify evidence, scope, and false-positive boundaries of saved-data checks."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from celeste_gameplay_viewer.findings import inspect_gameplay_map, inspect_map_data
from test_room_view import sample_map
from celeste_gameplay_viewer.viewer import cb, children


class FindingsTests(unittest.TestCase):
    def inspect(self, data):
        return inspect_map_data(data, "Fixture", "a" * 64)

    def test_optional_respawn_node_is_not_required(self):
        data = sample_map()
        trigger = children(cb.get_rooms(data)[0], "triggers")[1]
        trigger.pop("__children")
        self.assertNotIn("node_count_mismatch", [item["code"] for item in self.inspect(data)["findings"]])

    def test_missing_zip_mover_node_has_evidence_and_reference(self):
        data = sample_map()
        mover = children(cb.get_rooms(data)[0], "entities")[2]
        mover.pop("__children")
        finding = next(item for item in self.inspect(data)["findings"]
                       if item["code"] == "node_count_mismatch")
        self.assertEqual(finding["evidence"]["id"], 5)
        self.assertEqual(finding["evidence"]["expected_range"], [1, 1])
        self.assertTrue(finding["evidence"]["reference"].endswith("zip_mover.lua"))

    def test_duplicate_ids_are_room_scoped_and_include_decorations(self):
        data = sample_map()
        room = cb.get_rooms(data)[0]
        second = deepcopy(room)
        second.update(name="second", x=160)
        data["__children"][0]["__children"].append(second)
        self.assertNotIn("duplicate_object_id", [item["code"] for item in self.inspect(data)["findings"]])
        children(room, "entities").append({"__name": "lamp", "id": 4})
        finding = next(item for item in self.inspect(data)["findings"]
                       if item["code"] == "duplicate_object_id")
        self.assertEqual(finding["room_indices"], [0])
        self.assertEqual(finding["evidence"]["id"], 4)
        self.assertIn("lamp", [item["type"] for item in finding["evidence"]["objects"]])

    def test_entity_and_trigger_ids_can_overlap_as_in_vanilla_maps(self):
        data = sample_map()
        trigger = children(cb.get_rooms(data)[0], "triggers")[1]
        trigger["id"] = 4
        self.assertNotIn("duplicate_object_id", [item["code"] for item in self.inspect(data)["findings"]])

    def test_duplicate_names_preserve_both_indices_and_touching_is_not_overlap(self):
        data = sample_map()
        second = deepcopy(cb.get_rooms(data)[0])
        second["x"] = 160
        data["__children"][0]["__children"].append(second)
        report = self.inspect(data)
        self.assertEqual(report["findings"][0]["code"], "duplicate_room_name")
        self.assertEqual(report["findings"][0]["room_indices"], [0, 1])
        self.assertNotIn("overlapping_rooms", [item["code"] for item in report["findings"]])
        second["x"] -= 8
        overlap = next(item for item in self.inspect(data)["findings"]
                       if item["code"] == "overlapping_rooms")
        self.assertEqual(overlap["evidence"]["world_bounds"], [152, 80, 160, 264])

    def test_exact_border_anchors_are_allowed_and_outside_coordinates_are_preserved(self):
        data = sample_map()
        entities = children(cb.get_rooms(data)[0], "entities")
        entities.append({"__name": "player", "id": 20, "x": 320, "y": 184})
        self.assertNotIn("anchors_outside_room", [item["code"] for item in self.inspect(data)["findings"]])
        entities[-1]["x"] = 321
        finding = next(item for item in self.inspect(data)["findings"]
                       if item["code"] == "anchors_outside_room")
        self.assertEqual(finding["evidence"]["objects"][0]["local"], [321, 184])
        self.assertEqual(finding["evidence"]["objects"][0]["world"], [161, 264])

    def test_outside_nodes_are_observations_and_badeline_nodes_are_optional(self):
        data = sample_map()
        entities = children(cb.get_rooms(data)[0], "entities")
        entities.append({"__name": "badelineBoost", "id": 20, "x": 8, "y": 8})
        entities[2]["__children"][0].update(x=336, y=192)
        report = self.inspect(data)
        finding = next(item for item in report["findings"] if item["code"] == "nodes_outside_room")
        self.assertEqual(finding["level"], "observation")
        self.assertEqual(finding["evidence"]["nodes"][0]["node_world"], [176, 272])
        self.assertNotIn("node_count_mismatch", [item["code"] for item in report["findings"]])

    def test_unknown_types_are_coverage_not_map_defects(self):
        report = self.inspect(sample_map())
        self.assertEqual(report["summary"]["finding_count"], 0)
        self.assertEqual(report["summary"]["coverage_object_count"], 2)
        self.assertEqual({item["kind"] for item in report["renderer_coverage"]},
                         {"generic_symbols", "unclassified_triggers"})
        self.assertGreater(report["topology"]["unpaired_air_edge_count"], 0)

    def test_report_is_deterministic_and_leaves_input_intact(self):
        data = sample_map()
        before = deepcopy(data)
        self.assertEqual(self.inspect(data), self.inspect(data))
        self.assertEqual(data, before)

    def test_file_adapter_is_read_only_and_rejects_changed_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / "Maps").mkdir()
            path = workspace / "Maps/test.bin"
            path.write_bytes(b"fixture")
            with patch("celeste_gameplay_viewer.findings.cb.read_map", return_value=sample_map()):
                report = inspect_gameplay_map(workspace)
            self.assertEqual(report["source"], str(path))
            self.assertEqual(path.read_bytes(), b"fixture")
            self.assertEqual(list(workspace.rglob("*.*")), [path])
            with patch("celeste_gameplay_viewer.findings.cb.read_map", return_value=sample_map()), patch(
                    "pathlib.Path.read_bytes", side_effect=[b"before", b"after"]):
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    inspect_gameplay_map(workspace)


if __name__ == "__main__":
    unittest.main()
