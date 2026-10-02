"""Extract preview frames from a user's local Celeste installation.

The atlas format and trim placement follow Lönn's sprite loader. The PNGs
remain Celeste assets and must not be included in a public source release.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from PIL import Image

def read_string(stream):
    length = 0
    shift = 0
    while True:
        byte = stream.read(1)[0]
        length |= (byte & 127) << shift
        if byte < 128:
            break
        shift += 7
    return stream.read(length).decode("utf-8")


def read_pixels(path):
    with path.open("rb") as stream:
        width, height, alpha = struct.unpack("<ii?", stream.read(9))
        pixels = bytearray()
        while len(pixels) < width*height*4:
            count = stream.read(1)[0]
            opacity = stream.read(1)[0] if alpha else 255
            if opacity:
                blue, green, red = stream.read(3)
                rgba = bytes([min(255, round(c*255/opacity)) for c in (red, green, blue)] + [opacity])
            else:
                rgba = bytes(4)
            pixels.extend(rgba*count)
        assert len(pixels) == width*height*4
        return Image.frombytes("RGBA", (width, height), pixels)


def extract_sprites(celeste_path: Path, output_dir: Path) -> int:
    """Write selected local atlas frames; return the number of extracted PNGs."""
    source = celeste_path / "Content" / "Graphics" / "Atlases"
    if not (source / "Gameplay.meta").is_file():
        raise FileNotFoundError(f"Celeste Gameplay atlas not found in {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    source_pages = []
    with (source / "Gameplay.meta").open("rb") as stream:
        stream.read(4)
        read_string(stream)
        stream.read(4)
        pages, = struct.unpack("<H", stream.read(2))
        for _ in range(pages):
            page = read_string(stream)
            count, = struct.unpack("<h", stream.read(2))
            selected = []
            for _ in range(count):
                name = read_string(stream).replace("\\", "/")
                rectangle = struct.unpack("<8h", stream.read(16))
                if name in {"objects/refill/idle00", "objects/refillTwo/idle00",
                            "collectables/strawberry/normal00", "collectables/strawberry/wings01",
                            "collectables/moonBerry/normal00", "collectables/goldberry/idle00",
                            "collectables/goldberry/wings01", "collectables/cassette/idle00",
                            "collectables/key/idle00", "objects/spring/00",
                            "objects/booster/booster00", "objects/booster/boosterRed00",
                            "objects/badelineboost/idle00", "objects/clouds/cloud00",
                            "objects/clouds/fragile00", "danger/crystal/fg_blue00",
                            "danger/crystal/fg_red00", "danger/crystal/fg_purple00"} or (
                    name.startswith("danger/spikes/") and name.endswith("00")):
                    selected.append((name, rectangle))
            if not selected:
                continue
            page_file = f"{page}.data"
            source_pages.append(page_file)
            atlas = read_pixels(source / page_file)
            for name, (x, y, width, height, dx, dy, frame_width, frame_height) in selected:
                image = Image.new("RGBA", (frame_width, frame_height))
                image.paste(atlas.crop((x, y, x+width, y+height)), (-dx, -dy))
                filename = name.replace("/", "-") + ".png"
                image.save(output_dir / filename)
                records.append({"texture": name, "file": filename, "size": list(image.size),
                                "sha256": hashlib.sha256((output_dir / filename).read_bytes()).hexdigest()})
    if not records:
        raise ValueError("No supported preview frames were found in the Gameplay atlas")
    manifest = {"source": str(source), "source_hashes": {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in ["Gameplay.meta", *source_pages]},
        "references": ["https://github.com/EverestAPI/Resources/wiki/Useful-links",
                       "https://github.com/CelestialCartographers/Loenn/blob/master/src/sprite_loader.lua"],
        "assets": records}
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return len(records)


def main() -> None:
    """Parse install paths and extract the frames required by the viewer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--celeste-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    count = extract_sprites(args.celeste_path, args.output_dir)
    print(f"Extracted {count} preview sprites from the local Celeste atlas.")


if __name__ == "__main__":
    main()
