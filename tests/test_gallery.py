"""Regression checks for sprite anchors, marker classification, and gallery safety."""

import json
import base64
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image, ImageChops

from celeste_gameplay_viewer.overview import render_overview
from celeste_gameplay_viewer.room_gallery import make_gallery_fragment, render_room_gallery
from celeste_gameplay_viewer.sprites import object_sprite, spike_sprites
from test_room_view import sample_map
from celeste_gameplay_viewer.viewer import extract_layout


class GalleryTests(unittest.TestCase):
    def test_overview_preserves_collectible_positions_and_groups_other_types(self):
        layout = extract_layout(sample_map(), "Fixture")
        room = layout["rooms"][0]
        room["entities"] += [{"type": kind, "x": 3, "y": 5}
                             for kind in ["strawberry", "cassette", "blackGem", "key"]]
        _, metadata = render_overview(layout, "a"*64)
        self.assertEqual(metadata["strawberry_count"], 1)
        self.assertEqual(metadata["other_collectible_count"], 3)
        markers = [item for item in metadata["markers"] if item["kind"] == "collectible"]
        self.assertTrue(all((item["x"], item["y"]) == (-157, 85) for item in markers))

    def test_sprites_keep_original_size_and_spike_anchor(self):
        image, x, y = object_sprite({"type": "refill", "x": 80, "y": 40})
        self.assertEqual((image.size, x, y), ((16, 16), 72, 32))
        sprites = spike_sprites({"type": "spikesUp", "x": 32, "y": 48, "w": 16, "h": 0})
        self.assertEqual([(x, y) for _, x, y in sprites], [(32, 40), (40, 40)])
        self.assertIsNone(object_sprite({"type": "cloud", "x": 0, "y": 0,
                                         "properties": {"small": True}}))

    def test_fragment_escapes_map_names(self):
        fragment = make_gallery_fragment([{"name": "</script><script>bad()", "image": "data:image/png;base64,x"}], "test-gallery")
        self.assertNotIn("</script><script>bad()", fragment)
        self.assertIn("\\u003c/script", fragment)

    def test_gallery_generates_every_room_and_preserves_previous_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "Celeste/Mods/Example"
            (workspace / "Maps").mkdir(parents=True)
            source = workspace / "Maps/test.bin"
            source.write_bytes(b"unchanged")
            with patch("celeste_gameplay_viewer.room_gallery.cb.read_map", return_value=sample_map()):
                first = render_room_gallery(workspace, root / "output")
                second = render_room_gallery(workspace, root / "output")
                with self.assertRaises(ValueError):
                    render_room_gallery(workspace, root / "Celeste/Content/previews")
            self.assertNotEqual(first["html_path"], second["html_path"])
            self.assertEqual(first["room_count"], 1)
            self.assertEqual(first["page_count"], 2)
            self.assertTrue(first["overview_room_click_navigation"])
            self.assertEqual(source.read_bytes(), b"unchanged")
            self.assertTrue(Path(first["rooms"][0]["png_path"]).is_file())
            self.assertTrue(Path(first["fragment_path"]).is_file())
            fragment = Path(first["fragment_path"]).read_text(encoding="utf-8")
            pages = json.loads(fragment.split("const initialRooms = ")[1].split(";\n")[0])
            overview = json.loads(Path(first["overview_path"]).with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(pages[0]["regions"], overview["room_bounds"])
            self.assertEqual(pages[0]["size"], overview["image_size"])
            self.assertEqual({item["room"] for item in pages[0]["regions"]},
                             {page["name"] for page in pages[1:]})
            manifest = json.loads(Path(first["html_path"]).with_name("manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["room_count"], 1)
            payload = json.loads(Path(first["gallery_data_path"]).read_text())
            for page, png_path in zip(payload["pages"],
                                      [first["overview_path"], first["rooms"][0]["png_path"]]):
                with Image.open(BytesIO(base64.b64decode(page["image"].split(",")[1]))) as delivered, \
                     Image.open(png_path) as original:
                    self.assertEqual(delivered.size, original.size)
                    self.assertIsNone(ImageChops.difference(delivered.convert("RGB"),
                                                           original.convert("RGB")).getbbox())
            with Image.open(BytesIO(base64.b64decode(pages[1]["image"].split(",")[1]))) as compact:
                self.assertEqual(compact.width, 736)


if __name__ == "__main__":
    unittest.main()
