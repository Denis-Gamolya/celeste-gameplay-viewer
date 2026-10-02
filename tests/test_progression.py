"""Check progression coverage, fallback ordering, and overview-first browsing."""

import unittest

from progression import CITY_A_ORDER, order_rooms
from room_gallery import make_gallery_fragment


class ProgressionTests(unittest.TestCase):
    def test_city_profile_covers_every_room_and_keeps_branches_in_sequence(self):
        rooms = [{"name": "lvl_"+name} for name in reversed(CITY_A_ORDER)]
        ordered, metadata = order_rooms({"title": "1-ForsakenCity", "rooms": rooms}, "vanilla")
        names = [room["name"] for room in ordered]
        self.assertEqual(len(names), 38)
        self.assertEqual(len(set(names)), 38)
        self.assertEqual(names[:6], ["lvl_1", "lvl_2", "lvl_3", "lvl_4", "lvl_3b", "lvl_5"])
        self.assertLess(names.index("lvl_6"), names.index("lvl_s1"))
        self.assertLess(names.index("lvl_s1"), names.index("lvl_9b"))
        self.assertEqual(names[-1], "lvl_end")
        self.assertIn("reference", metadata)

    def test_unknown_maps_have_explicit_natural_order_fallback(self):
        rooms = [{"name": name} for name in ["room_10", "room_2", "room_1"]]
        ordered, metadata = order_rooms({"title": "Custom", "rooms": rooms}, "mod")
        self.assertEqual([room["name"] for room in ordered], ["room_1", "room_2", "room_10"])
        self.assertIn("unverified", metadata["basis"])

    def test_gallery_keeps_overview_first(self):
        fragment = make_gallery_fragment([
            {"name": "Whole map", "kind": "overview", "image": "overview-data"},
            {"name": "lvl_1", "kind": "room", "image": "room-data"},
        ], "fixture")
        self.assertLess(fragment.index('"name":"Whole map"'), fragment.index('"name":"lvl_1"'))


if __name__ == "__main__":
    unittest.main()
