"""Build a browser regression page from a real gallery-data.json snapshot.

Run with the snapshot path and an output HTML path, then open the output in
a browser. The page reports assertions in #regression-result and sets
body[data-state-check] to passed or failed. No source map is opened or edited.
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from celeste_gameplay_viewer.room_gallery import make_gallery_fragment, wrap_gallery


def prepare(snapshot: Path, output: Path) -> None:
    """Write the shared gallery and a host-state simulator for browser checks."""
    pages = json.loads(snapshot.read_text(encoding="utf-8"))["pages"]
    setup = """<script>
window.testErrors = [];
window.addEventListener('error', event => window.testErrors.push(event.message));
window.addEventListener('unhandledrejection', event => window.testErrors.push(String(event.reason)));
window.testSaveMode = 'promise';
window.testSaveState = state => {
  if (window.testSaveMode === 'throw') throw Error('Persistence unavailable');
  if (window.testSaveMode === 'reject') return Promise.reject(Error('Persistence unavailable'));
  window.openai.widgetState = state;
  if (window.testSaveMode === 'promise') return Promise.resolve();
};
window.openai = {widgetState: null, setWidgetState: window.testSaveState};
</script>"""
    check = Path(__file__).with_name("gallery_state_check.js").read_text(encoding="utf-8")
    fragment = make_gallery_fragment(pages, "gallery-state-regression")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(wrap_gallery(setup + fragment + "<script>" + check + "</script>"),
                      encoding="utf-8")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]), Path(sys.argv[2]))
