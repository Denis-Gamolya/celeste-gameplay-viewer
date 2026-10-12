"""Write rendered room artifacts and assemble matching browser pages."""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .serialization import encode_image


@dataclass
class RoomGalleryData:
    """Parallel native/compact pages plus the saved PNG manifest, in room order."""

    full_pages: list[dict]
    compact_pages: list[dict]
    manifest: list[dict]


def write_room_images(
    destination: Path, rendered: Iterable[tuple[bytes, dict]]
) -> RoomGalleryData:
    """Save each room PNG/JSON and encode its two browser delivery variants.

    The caller owns a new output directory and source-preservation checks.
    Returns room-only pages; each caller supplies its own whole-map entry page.
    """
    full_pages = []
    compact_pages = []
    manifest = []
    for index, (png, metadata) in enumerate(rendered, start=1):
        image_path = destination / f"room-{index:03}.png"
        image_path.write_bytes(png)
        image_path.with_suffix(".json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        manifest.append(
            {
                "room": metadata["room"],
                "png_path": str(image_path),
                "png_sha256": hashlib.sha256(png).hexdigest(),
            }
        )
        page = {"name": metadata["room"], "kind": "room"}
        full_pages.append(
            {**page, "image": encode_image(png, "lossless_webp")}
        )
        compact_pages.append(
            {**page, "image": encode_image(png, "inline_webp")}
        )
    return RoomGalleryData(full_pages, compact_pages, manifest)
