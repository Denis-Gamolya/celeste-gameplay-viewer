"""Verify the UI resource contract and separation of image data from summaries."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastmcp import Client

from celeste_gameplay_viewer.mcp_app import RESOURCE_MIME, RESOURCE_URI, make_app_resource
from celeste_gameplay_viewer.mcp_app import render_interactive_map
from celeste_gameplay_viewer.server import mcp


class AppTests(unittest.TestCase):
    def test_resource_is_data_free_and_has_no_external_dependencies(self):
        html = make_app_resource()
        self.assertIn("const initialRooms = [];", html)
        self.assertIn("ui/initialize", html)
        self.assertNotIn("__INSTANCE__", html)
        self.assertNotIn("__ROOM_DATA__", html)
        self.assertNotIn('<script src=', html)
        self.assertNotIn('file://', html)

    def test_images_stay_in_result_metadata_and_fallback_paths_remain(self):
        with tempfile.TemporaryDirectory() as temporary:
            payload_path = Path(temporary) / "gallery-data.json"
            payload = {"schema_version": 1, "source_hash": "a" * 64,
                       "pages": [{"image": "data:image/png;base64,cHJpdmF0ZQ=="}]}
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            manifest = {"gallery_data_path": str(payload_path),
                        "map_sha256": "a" * 64, "room_count": 1,
                        "page_count": 2, "html_path": "index.html"}
            with patch("celeste_gameplay_viewer.mcp_app.render_room_gallery", return_value=manifest):
                result = render_interactive_map(Path(temporary), Path(temporary))
            self.assertEqual(result.meta["celesteGallery"], payload)
            self.assertEqual(result.structured_content, manifest)
            self.assertNotIn("base64", json.dumps(result.structured_content))
            self.assertNotIn("base64", result.content[0].text)


class AppProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_points_to_readable_mcp_app_resource(self):
        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool = next(item for item in tools if item.name == "render_interactive_map")
            self.assertEqual(tool.meta["ui"]["resourceUri"], RESOURCE_URI)
            resources = await client.list_resources()
            resource = next(item for item in resources if str(item.uri) == RESOURCE_URI)
            self.assertEqual(resource.mimeType, RESOURCE_MIME)
            contents = await client.read_resource(RESOURCE_URI)
            self.assertEqual(contents[0].mimeType, RESOURCE_MIME)
            self.assertEqual(contents[0].meta["ui"]["csp"]["connectDomains"], [])
            self.assertIn("ui/notifications/tool-result", contents[0].text)


if __name__ == "__main__":
    unittest.main()
