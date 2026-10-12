"""Compare inferred room browsing order with Berry Camp's independent lists.

Reference data belongs to tests only. Runtime progression never imports it.
Run with --maps-dir pointing at a local Celeste Content/Maps directory and
--report-dir outside that game installation. No map files are changed.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from celeste_gameplay_viewer.progression import order_rooms
from celeste_gameplay_viewer.viewer import cb, extract_layout

REFERENCE_COMMIT = "bd24de2d6a022d899adff406ee9aad397106301d"
REFERENCE_URL = (
    "https://raw.githubusercontent.com/berrycamp/berrycamp.github.io/"
    + REFERENCE_COMMIT + "/data/celeste.json"
)
DEFAULT_REFERENCE = Path(__file__).resolve().parents[1] / "tests/fixtures/berrycamp-order.json"


class PublishedRoomLinks(HTMLParser):
    """Read first-occurrence room links in the site's displayed browsing order."""

    def __init__(self, page_url: str):
        super().__init__()
        self.prefix = urlparse(page_url).path.rstrip("/") + "/"
        self.rooms = []

    def handle_starttag(self, tag, attributes):
        if tag != "a":
            return
        href = dict(attributes).get("href", "")
        parsed = urlparse(href)
        if not parsed.path.startswith(self.prefix):
            return
        suffix = unquote(parsed.path[len(self.prefix):])
        if not suffix or "/" in suffix:
            return
        name = "lvl_" + suffix
        if name not in self.rooms:
            self.rooms.append(name)


def check_published_reference(reference: Path) -> list[dict]:
    """Compare the pinned fixtures to all public chapter-side room pages.

    This optional development check requires network access. Runtime rendering
    and ordinary unit tests remain offline. Raises if the deployed site differs
    from the pinned reference instead of silently changing test expectations.
    """
    profiles = json.loads(reference.read_text(encoding="utf-8"))["profiles"]

    def check(profile):
        parser = PublishedRoomLinks(profile["url"])
        with urlopen(profile["url"], timeout=30) as response:
            parser.feed(response.read().decode("utf-8"))
        if parser.rooms != profile["expected"]:
            raise ValueError(f"Published order differs for {profile['map']}: {parser.rooms}")
        return {"map": profile["map"], "url": profile["url"],
                "rooms": len(parser.rooms), "matches_fixture": True}

    with ThreadPoolExecutor(max_workers=4) as executor:
        return list(executor.map(check, profiles))


def import_reference(download: Path, destination: Path) -> None:
    """Reduce a downloaded public dataset to independently authored test orders."""
    original = download.read_bytes()
    data = json.loads(original)
    profiles = []
    for chapter in data["chapters"]:
        for side in chapter["sides"]:
            stem = chapter["gameId"]
            if side["id"] != "a":
                marker = "H-" if side["id"] == "b" else "X-"
                stem = stem.replace("-", marker, 1)
            names = ["lvl_" + name for checkpoint in side["checkpoints"]
                     for name in checkpoint["roomOrder"]]
            if len(names) != len(set(names)):
                raise ValueError("Reference contains duplicate room names.")
            profiles.append({
                "map": stem + ".bin", "chapter": chapter["name"],
                "side": side["id"].upper(),
                "url": f"https://berrycamp.github.io/celeste/{chapter['id']}/{side['id']}",
                "advertised_room_count": side["roomCount"], "expected": names,
            })
    fixture = {
        "provenance": {"source": REFERENCE_URL, "commit": REFERENCE_COMMIT,
                       "sha256": hashlib.sha256(original).hexdigest(),
                       "credit": "Berry Camp by wishcresp and contributors",
                       "use": "Independent validation only; never runtime ordering"},
        "profiles": profiles,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(fixture, indent=2), encoding="utf-8")


def compare_orders(actual: list[str], expected: list[str]) -> dict:
    """Measure coverage, exact positions, and relative order independently.

    Extra saved rooms are retained but excluded from the sequence comparison.
    Relative agreement counts how many expected pairs have the same order;
    it is a comparison metric, not a probability of gameplay correctness.
    """
    reference_names = set(expected)
    source_names = set(actual)
    common = [name for name in actual if name in reference_names]
    positions = {name: index for index, name in enumerate(common)}
    present = [name for name in expected if name in source_names]
    pairs = len(present) * (len(present) - 1) // 2
    concordant = sum(positions[first] < positions[second]
                     for index, first in enumerate(present)
                     for second in present[index + 1:])
    differences = [{"index": index + 1, "expected": wanted, "actual": found}
                   for index, (wanted, found) in enumerate(zip(expected, common))
                   if wanted != found]
    return {
        "exact": common == expected, "source_count": len(actual),
        "reference_count": len(expected),
        "missing": sorted(reference_names - source_names),
        "extra": sorted(source_names - reference_names),
        "same_positions": sum(first == second for first, second in zip(common, expected)),
        "concordant_pairs": concordant, "pairs": pairs,
        "relative_agreement": concordant / pairs if pairs else 1.0,
        "differences": differences, "actual": actual, "expected": expected,
    }


def natural_baseline(rooms: list[dict]) -> list[str]:
    """Reproduce the old generic fallback, without any vanilla chapter profile."""
    def key(room):
        return [(0, int(part)) if part.isdigit() else (1, part.lower())
                for part in re.split(r"(\d+)", room["name"])]
    return [room["name"] for room in sorted(rooms, key=key)]


def verify(maps_dir: Path, reference: Path, report_dir: Path) -> dict:
    """Read every reference map, compare its inferred order, and write a report.

    Raises on missing maps, omitted/duplicated output rooms, nondeterministic
    results, source changes, or report output inside the game installation.
    """
    maps_dir = maps_dir.resolve(strict=True)
    game_root = maps_dir.parent.parent
    report_dir = report_dir.resolve()
    if report_dir.is_relative_to(game_root):
        raise ValueError("Reports must be written outside the Celeste installation.")
    fixture = json.loads(reference.read_text(encoding="utf-8"))
    reports = []
    for profile in fixture["profiles"]:
        path = (maps_dir / profile["map"]).resolve(strict=True)
        if not path.is_relative_to(maps_dir) or path.suffix != ".bin":
            raise ValueError("Invalid reference map path.")
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        layout = extract_layout(cb.read_map(path), path.stem)
        ordered, metadata = order_rooms(layout, "vanilla")
        names = [room["name"] for room in ordered]
        if sorted(names) != sorted(room["name"] for room in layout["rooms"]):
            raise AssertionError("Ordering omitted or duplicated a saved room.")
        shuffled, _ = order_rooms({**layout, "rooms": list(reversed(layout["rooms"]))}, "mod")
        if [room["name"] for room in shuffled] != names:
            raise AssertionError("Ordering depends on input order or source kind.")
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        if before != after:
            raise RuntimeError("A source map changed during verification.")
        comparison = compare_orders(names, profile["expected"])
        baseline = compare_orders(natural_baseline(layout["rooms"]), profile["expected"])
        reports.append({**profile, **comparison, "baseline": baseline,
                        "map_sha256": before, "source_unchanged": True,
                        "inference": metadata})
    pairs = sum(report["pairs"] for report in reports)
    report = {
        "reference": fixture["provenance"], "maps": reports,
        "summary": {
            "maps": len(reports), "source_rooms": sum(item["source_count"] for item in reports),
            "reference_rooms": sum(item["reference_count"] for item in reports),
            "extra_rooms": sum(len(item["extra"]) for item in reports),
            "missing_rooms": sum(len(item["missing"]) for item in reports),
            "exact_maps": sum(item["exact"] for item in reports),
            "same_positions": sum(item["same_positions"] for item in reports),
            "relative_agreement": sum(item["concordant_pairs"] for item in reports) / pairs,
            "baseline_relative_agreement": sum(item["baseline"]["concordant_pairs"] for item in reports) / pairs,
            "all_source_maps_unchanged": all(item["source_unchanged"] for item in reports),
        },
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Progression validation against Berry Camp", "",
             "One geometry/spawn algorithm is used for every map. Reference lists are tests only.",
             "All source rooms are retained. Extra rooms are excluded from reference-order scoring.", "",
             "| Map | Saved / reference rooms | Exact order | Same positions | Relative order | Extra rooms |",
             "| --- | --- | --- | --- | --- | --- |"]
    for item in reports:
        lines.append(f"| {item['map']} | {item['source_count']} / {item['reference_count']} | "
                     f"{'Yes' if item['exact'] else 'No'} | {item['same_positions']} / {item['reference_count']} | "
                     f"{item['relative_agreement']:.1%} | {', '.join(item['extra']) or '—'} |")
    lines.extend(["", "Exact order means every reference room is at the expected index.",
                  "Relative order measures concordant room pairs; it does not verify a playable route.",
                  "", f"Reference: {REFERENCE_URL}", ""])
    (report_dir / "results.md").write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maps-dir", type=Path)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--report-dir", type=Path, default=Path("outputs/progression-audit"))
    parser.add_argument("--import-reference", type=Path)
    parser.add_argument("--check-site", action="store_true")
    arguments = parser.parse_args()
    if arguments.import_reference:
        import_reference(arguments.import_reference, arguments.reference)
    if arguments.check_site:
        checks = check_published_reference(arguments.reference)
        arguments.report_dir.mkdir(parents=True, exist_ok=True)
        (arguments.report_dir / "published-reference-check.json").write_text(
            json.dumps(checks, indent=2), encoding="utf-8")
        print(json.dumps({"published_pages_checked": len(checks), "all_match": True}))
    if arguments.maps_dir:
        print(json.dumps(verify(arguments.maps_dir, arguments.reference,
                                arguments.report_dir)["summary"], indent=2))
