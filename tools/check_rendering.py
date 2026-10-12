"""Capture or compare image/metadata fingerprints during renderer refactors.

Snapshots contain hashes only and stay in ignored outputs. This development
check reads local maps without editing them and requires no golden game assets
in version control. Use --capture before a refactor, then run again without it.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from celeste_gameplay_viewer.overview import render_overview
from celeste_gameplay_viewer.room_view import render_room
from celeste_gameplay_viewer.viewer import cb, extract_layout


def digest_render(png: bytes, metadata: dict) -> dict:
    """Fingerprint both pixels and the inspectable description of a render."""
    encoded = json.dumps(
        metadata, sort_keys=True, separators=(",", ":")
    ).encode()
    return {
        "png": hashlib.sha256(png).hexdigest(),
        "metadata": hashlib.sha256(encoded).hexdigest(),
    }


def fingerprint_maps(maps_dir: Path) -> dict:
    """Read and render all maps; fail if a source changes during the check."""
    fingerprints = {}
    for path in sorted(maps_dir.glob("*.bin")):
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        layout = extract_layout(cb.read_map(path), path.stem)
        images = {
            room["name"]: digest_render(
                *render_room(layout, room["name"], source_hash)
            )
            for room in layout["rooms"]
        }
        fingerprints[path.name] = {
            "source_hash": source_hash,
            "rooms": images,
            "overview": digest_render(*render_overview(layout, source_hash)),
        }
        if hashlib.sha256(path.read_bytes()).hexdigest() != source_hash:
            raise RuntimeError(f"Source changed during rendering: {path.name}")
        print(f"Checked {path.name}: {len(images)} rooms", flush=True)
    return fingerprints


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maps-dir", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--capture", action="store_true")
    arguments = parser.parse_args()
    fingerprints = fingerprint_maps(arguments.maps_dir)
    if arguments.capture:
        arguments.snapshot.parent.mkdir(parents=True, exist_ok=True)
        arguments.snapshot.write_text(
            json.dumps(fingerprints, indent=2), encoding="utf-8"
        )
        print("Baseline captured.")
        return
    previous = json.loads(arguments.snapshot.read_text(encoding="utf-8"))
    if fingerprints != previous:
        differences = [
            name
            for name in fingerprints
            if fingerprints[name] != previous.get(name)
        ]
        raise AssertionError(f"Render fingerprints changed: {differences}")
    print("All rendered images and metadata match the baseline.")


if __name__ == "__main__":
    main()
