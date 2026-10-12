"""Build a browser regression page from a real gallery-data.json snapshot.

Run with the snapshot path and an output HTML path, then open the output in
a browser. The page reports assertions in #regression-result and sets
body[data-state-check] to passed or failed. No source map is opened or edited.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from celeste_gameplay_viewer.room_gallery import (
    make_gallery_fragment,
    wrap_gallery,
)
from celeste_gameplay_viewer.serialization import encode_script_json


def prepare(snapshot: Path, output: Path) -> None:
    """Write the shared gallery and a host-state simulator for browser checks."""
    pages = json.loads(snapshot.read_text(encoding="utf-8"))["pages"]
    if len(pages) < 2:
        raise ValueError("The browser regression requires at least one room.")
    settings = {
        "initialRoom": pages[min(2, len(pages) - 1)]["name"],
        "delayedRoom": pages[1]["name"],
    }
    setup = (
        "<script>window.galleryTestSettings = "
        + encode_script_json(settings)
        + ";</script>"
    )
    setup += """<script>
window.testErrors = [];
window.addEventListener('error', event => window.testErrors.push(event.message));
window.addEventListener('unhandledrejection', event => window.testErrors.push(String(event.reason)));
window.testSaveMode = 'promise';
window.testSaveState = state => {
  if (window.testSaveMode === 'throw') throw Error('Persistence unavailable');
  if (window.testSaveMode === 'reject') return Promise.reject(Error('Persistence unavailable'));
  window.openai.widgetState = state;
  window.savedNavigation = state;
  if (window.testSaveMode === 'promise') return Promise.resolve();
};
window.openai = {
  widgetState: {modelContent: {room: window.galleryTestSettings.initialRoom}, privateContent: null},
  setWidgetState: window.testSaveState,
};
</script>"""
    check = (
        Path(__file__)
        .with_name("gallery-state-check.js")
        .read_text(encoding="utf-8")
    )
    fragment = make_gallery_fragment(pages, "gallery-state-regression")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        wrap_gallery(setup + fragment + "<script>" + check + "</script>"),
        encoding="utf-8",
    )


if __name__ == "__main__":
    prepare(Path(sys.argv[1]), Path(sys.argv[2]))
