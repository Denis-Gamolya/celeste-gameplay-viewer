"""Create an in-memory PNG for testing client image delivery, without maps."""

import base64
from io import BytesIO

from fastmcp.tools import ToolResult
from mcp.types import ImageContent, TextContent
from PIL import Image, ImageDraw, ImageFont


def make_image_probe() -> ToolResult:
    """Return text and a 480 by 160 PNG as top-level MCP content blocks.

    The fixed P1-CELESTE label and different shapes let the user distinguish
    rendered pixels from a text-only description. No files, map data, network,
    fonts on disk, or environment variables are accessed by this function.
    Client display remains unverified until the user sees the actual image.
    """
    picture = Image.new("RGB", (480, 160), "#f4f5f7")
    drawing = ImageDraw.Draw(picture)
    heading = ImageFont.load_default(size=24)
    label = ImageFont.load_default(size=17)
    drawing.text((20, 15), "Celeste preview: image test", fill="#17212b",
                 font=heading)
    drawing.rectangle((24, 65, 66, 107), fill="#2474c6")
    drawing.polygon([(117, 65), (141, 107), (93, 107)], fill="#df7b24")
    drawing.text((164, 71), "P1-CELESTE", fill="#17212b", font=heading)
    drawing.text((20, 130), "PNG from the Windows MCP server", fill="#17212b",
                 font=label)
    with BytesIO() as stream:
        picture.save(stream, format="PNG")
        encoded = base64.b64encode(stream.getvalue()).decode("ascii")
    return ToolResult(content=[
        TextContent(
            type="text",
            text=("Phase 1 image delivery test. The PNG contains P1-CELESTE, "
                  "a blue square, and an orange triangle. Confirm that the "
                  "image itself is visible in chat; text alone is not a pass."),
        ),
        ImageContent(type="image", data=encoded, mimeType="image/png"),
    ])
