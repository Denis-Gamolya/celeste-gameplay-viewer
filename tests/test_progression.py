"""Verify general room ordering and compare real chapters with independent data."""

import hashlib
import json
import os
from pathlib import Path
import random
import unittest

from celeste_gameplay_viewer.progression import order_rooms, room_name_key
from celeste_gameplay_viewer.progression import shared_boundary
from celeste_gameplay_viewer.room_gallery import make_gallery_fragment
from celeste_gameplay_viewer.viewer import cb, extract_layout
from tools.verify_progression import compare_orders, natural_baseline
from tools.verify_progression import PublishedRoomLinks

REFERENCE = Path(__file__).with_name("fixtures") / "berrycamp-order.json"


def room(name, x, y, spawn=(8, 48)):
    return {"name": name, "x": x, "y": y, "w": 64, "h": 64,
            "entities": [{"type": "player", "x": spawn[0], "y": spawn[1]}]}


class ProgressionTests(unittest.TestCase):
    def test_geometry_overrides_misleading_numeric_names(self):
        rooms = [room("lvl_start", 0, 0), room("lvl_10", 64, 0),
                 room("lvl_2", 128, 0)]
        ordered, metadata = order_rooms({"title": "Custom", "rooms": rooms}, "mod")
        self.assertEqual([item["name"] for item in ordered],
                         ["lvl_start", "lvl_10", "lvl_2"])
        self.assertEqual(metadata["candidate_links"], 2)
        self.assertIn("unverified", metadata["basis"])

    def test_small_side_branch_stays_before_long_continuation(self):
        rooms = [room("lvl_start", 0, 0), room("lvl_hub", 64, 0),
                 room("lvl_side", 64, -64, (32, 56)),
                 room("lvl_main1", 128, 0), room("lvl_main2", 192, 0)]
        ordered, _ = order_rooms({"rooms": rooms}, "mod")
        self.assertEqual([item["name"] for item in ordered],
                         ["lvl_start", "lvl_hub", "lvl_side", "lvl_main1", "lvl_main2"])

    def test_title_source_and_input_order_do_not_select_special_profiles(self):
        rooms = [room("lvl_start", 0, 0), room("lvl_10", 64, 0),
                 room("lvl_2", 128, 0)]
        first, _ = order_rooms({"title": "1-ForsakenCity", "rooms": rooms}, "vanilla")
        second, _ = order_rooms({"title": "Unrelated", "rooms": rooms[::-1]}, "mod")
        self.assertEqual(first, second)

    def test_cycles_disconnected_and_spawnless_rooms_are_all_retained(self):
        rooms = [room("lvl_start", 0, 0), room("lvl_1", 64, 0),
                 room("lvl_2", 64, 64), room("lvl_3", 0, 64),
                 room("lvl_end", 500, 500), {"name": "lvl_missing"}]
        rooms[2]["entities"] = []
        ordered, metadata = order_rooms({"rooms": rooms}, "mod")
        self.assertCountEqual(map(id, ordered), map(id, rooms))
        self.assertEqual(len(ordered), len(rooms))
        self.assertEqual(len(metadata["components"]), 3)
        self.assertEqual(metadata["rooms_without_spawns"], ["lvl_2"])
        self.assertEqual(metadata["rooms_without_geometry"], ["lvl_missing"])

    def test_missing_geometry_has_a_natural_order_fallback(self):
        rooms = [{"name": name} for name in ["room_10", "room_2", "room_1"]]
        ordered, _ = order_rooms({"rooms": rooms}, "mod")
        self.assertEqual([item["name"] for item in ordered],
                         ["room_1", "room_2", "room_10"])

    def test_natural_keys_distinguish_signed_ids_from_separators(self):
        names = ["lvl_2", "lvl_-1", "lvl_0", "lvl_a-10", "lvl_a-2"]
        self.assertEqual(sorted(names, key=room_name_key),
                         ["lvl_-1", "lvl_0", "lvl_2", "lvl_a-2", "lvl_a-10"])

    def test_corners_gaps_and_overlapping_interiors_are_not_connections(self):
        origin = room("a", 0, 0)
        for other in (room("b", 64, 64), room("c", 72, 0), room("d", 32, 0)):
            self.assertIsNone(shared_boundary(origin, other))
        self.assertIsNotNone(shared_boundary(origin, room("e", 64, 0)))

    def test_duplicate_names_do_not_collapse_room_objects(self):
        rooms = [room("same", 0, 0), room("same", 64, 0)]
        ordered, metadata = order_rooms({"rooms": rooms}, "mod")
        self.assertCountEqual(map(id, ordered), map(id, rooms))
        self.assertEqual(metadata["duplicate_names"], ["same"])

    def test_named_start_takes_priority_over_a_later_golden_berry(self):
        rooms = [room("lvl_start", 0, 0), room("lvl_00", 64, 0),
                 room("lvl_end-golden", 128, 0)]
        rooms[-1]["entities"].append({"type": "goldenBerry"})
        ordered, _ = order_rooms({"rooms": rooms}, "mod")
        self.assertEqual(ordered[0]["name"], "lvl_start")

    def test_gallery_keeps_overview_first(self):
        fragment = make_gallery_fragment([
            {"name": "Whole map", "kind": "overview", "image": "overview-data"},
            {"name": "lvl_1", "kind": "room", "image": "room-data"},
        ], "fixture")
        self.assertLess(fragment.index('"name":"Whole map"'), fragment.index('"name":"lvl_1"'))

    def test_reference_covers_every_chapter_and_side_without_duplicate_rooms(self):
        fixture = json.loads(REFERENCE.read_text(encoding="utf-8"))
        self.assertEqual(len(fixture["profiles"]), 27)
        self.assertEqual(len({profile["chapter"] for profile in fixture["profiles"]}), 11)
        for profile in fixture["profiles"]:
            self.assertEqual(len(profile["expected"]), len(set(profile["expected"])))

    def test_reference_comparison_separates_order_from_room_coverage(self):
        comparison = compare_orders(["a", "extra", "c", "b"], ["a", "b", "c"])
        self.assertEqual(comparison["extra"], ["extra"])
        self.assertEqual(comparison["missing"], [])
        self.assertFalse(comparison["exact"])
        self.assertEqual(comparison["same_positions"], 1)
        self.assertEqual(comparison["relative_agreement"], 2 / 3)

    def test_published_reference_parser_ignores_navigation_and_repeated_links(self):
        parser = PublishedRoomLinks("https://berrycamp.github.io/celeste/site/a")
        parser.feed('<a href="/celeste/site/b">B</a><a href="/celeste/site/a/start">Start</a>'
                    '<a href="/celeste/site/a/0">0</a><a href="/celeste/site/a/start">Start</a>')
        self.assertEqual(parser.rooms, ["lvl_start", "lvl_0"])


@unittest.skipUnless(os.environ.get("CELESTE_TEST_MAPS"), "Set CELESTE_TEST_MAPS for real-map comparisons.")
class BaseGameProgressionTests(unittest.TestCase):
    def test_all_chapters_preserve_coverage_and_improve_the_name_only_baseline(self):
        fixture = json.loads(REFERENCE.read_text(encoding="utf-8"))
        maps = Path(os.environ["CELESTE_TEST_MAPS"])
        concordant = baseline = pairs = 0
        for profile in fixture["profiles"]:
            with self.subTest(map=profile["map"]):
                path = maps / profile["map"]
                before = hashlib.sha256(path.read_bytes()).hexdigest()
                layout = extract_layout(cb.read_map(path), path.stem)
                ordered, _ = order_rooms(layout, "vanilla")
                names = [item["name"] for item in ordered]
                self.assertCountEqual(names, [item["name"] for item in layout["rooms"]])
                shuffled = list(layout["rooms"])
                random.Random(7).shuffle(shuffled)
                repeated, _ = order_rooms({"title": "Custom", "rooms": shuffled}, "mod")
                self.assertEqual(names, [item["name"] for item in repeated])
                comparison = compare_orders(names, profile["expected"])
                self.assertEqual(comparison["missing"], [])
                if profile["side"] == "C":
                    self.assertTrue(comparison["exact"])
                concordant += comparison["concordant_pairs"]
                pairs += comparison["pairs"]
                baseline += compare_orders(natural_baseline(layout["rooms"]),
                                           profile["expected"])["concordant_pairs"]
                self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertGreater(concordant, baseline)
        self.assertGreater(concordant / pairs, 0.95)


if __name__ == "__main__":
    unittest.main()
