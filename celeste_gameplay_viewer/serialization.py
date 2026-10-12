"""Encode browser data without changing its meaning or delivery quality."""

import base64
import json
from io import BytesIO
from typing import Literal

from PIL import Image

INLINE_IMAGE_WIDTH = 736
INLINE_IMAGE_QUALITY = 55
ImageEncoding = Literal["png", "lossless_webp", "inline_webp"]


def encode_script_json(value) -> str:
    """Encode JSON for a script body without allowing HTML closing tags.

    HTML parsers recognize closing script tags even inside JavaScript strings.
    Escape markup characters after serialization, preserving decoded values.
    """
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return (
        encoded.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def encode_image(png: bytes, encoding: ImageEncoding = "png") -> str:
    """Return a data URL in PNG, lossless WebP, or compact inline WebP.

    PNG and lossless WebP preserve native dimensions and pixels. Only inline
    WebP is resized and lossy. This function writes no files.
    """
    if encoding == "png":
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    if encoding not in {"lossless_webp", "inline_webp"}:
        raise ValueError(f"Unsupported image encoding: {encoding}")
    with Image.open(BytesIO(png)) as image, BytesIO() as output:
        if encoding == "inline_webp":
            height = round(image.height * INLINE_IMAGE_WIDTH / image.width)
            image = image.resize(
                (INLINE_IMAGE_WIDTH, height), Image.Resampling.LANCZOS
            )
        image.save(
            output,
            "WEBP",
            quality=INLINE_IMAGE_QUALITY,
            lossless=encoding == "lossless_webp",
            method=6,
        )
        return "data:image/webp;base64," + base64.b64encode(
            output.getvalue()
        ).decode("ascii")
