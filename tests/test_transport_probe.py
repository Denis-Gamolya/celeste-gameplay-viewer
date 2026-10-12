"""Verify the image probe's PNG bytes and MCP content-block serialization."""

import base64
import unittest
from io import BytesIO

from fastmcp import Client
from PIL import Image

from celeste_gameplay_viewer.server import mcp
from celeste_gameplay_viewer.transport_probe import make_image_probe


class ProbeTests(unittest.TestCase):
    def test_probe_contains_small_valid_png_and_accessible_text(self):
        result = make_image_probe()
        self.assertEqual(
            [item.type for item in result.content], ["text", "image"]
        )
        self.assertIn("P1-CELESTE", result.content[0].text)
        block = result.content[1]
        self.assertEqual(block.mimeType, "image/png")
        raw = base64.b64decode(block.data, validate=True)
        self.assertLess(len(raw), 20_000)
        with Image.open(BytesIO(raw)) as picture:
            picture.verify()
        with Image.open(BytesIO(raw)) as picture:
            self.assertEqual(picture.size, (480, 160))
            self.assertEqual(picture.format, "PNG")
            self.assertEqual(picture.getpixel((40, 80)), (36, 116, 198))
            self.assertEqual(picture.getpixel((117, 90)), (223, 123, 36))


class ProbeProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_keeps_image_as_top_level_content(self):
        async with Client(mcp) as client:
            catalog = await client.list_tools()
            tool = next(
                item for item in catalog if item.name == "test_image_delivery"
            )
            self.assertTrue(tool.annotations.readOnlyHint)
            result = await client.call_tool("test_image_delivery", {})
            self.assertEqual(
                [item.type for item in result.content], ["text", "image"]
            )
            self.assertFalse(result.is_error)


if __name__ == "__main__":
    unittest.main()
