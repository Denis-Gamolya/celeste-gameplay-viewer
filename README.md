# Celeste Gameplay Viewer

Render Celeste maps as a whole-map overview and an interactive, zoomable room
browser in Codex. The viewer shows tiles, spawns, collectibles, gameplay
entities, triggers, and candidate room connections. It reads `.bin` maps and
writes previews outside the mod project; it does not edit maps or determine
whether a route is playable.

This repository contains the standalone viewer only. It does **not** include
or expose the map-editing tools from `loenn-mcp` or the combined
`celeste-mapping-toolkit`. Install an editor MCP separately if you want to
change maps through chat.

## Windows installation

Requirements: Windows PowerShell, Python 3.10 or newer, Codex, an installed
copy of Celeste, and a mod project under `Celeste\Mods` containing at least
one `.bin` map in `Maps`. An internet connection is needed for the initial
PyPI dependency install.

Download or clone this repository, then run from its folder:

```powershell
.\install.ps1 `
  -CelestePath 'D:\SteamLibrary\steamapps\common\Celeste' `
  -ModPath 'D:\SteamLibrary\steamapps\common\Celeste\Mods\YourMod'
```

Replace the two paths with your own. Choose the mod project's root, not the
entire `Mods` folder. The installer copies only viewer source into
`%LOCALAPPDATA%\CelesteGameplayViewer`, creates an isolated Python environment,
installs dependencies from PyPI, extracts the few sprites needed for previews
from **your local Celeste installation**, verifies a read-only map response,
and registers `celeste-gameplay-viewer` as a separate Codex MCP server. It
does not remove or change any other MCP registration. Restart the Codex MCP
connection after installation, then ask for `render_interactive_map`.

The viewer and map editor remain independent:

```text
Celeste mod Maps/*.bin ──read──> celeste-gameplay-viewer ──> Codex previews
                                  │
                                  └── PyPI dependency: loenn-mcp map parser

Optional separate loenn-mcp server ──edit──> Celeste mod Maps/*.bin
```

This text diagram is version controlled, readable in terminals, and explains
the runtime boundary without depending on a diagram renderer. The source
uses one importable Python package, while `run_server.py` is the small stdio
entry point Codex launches.

## Using the viewer

Ask Codex to call `render_interactive_map` for the whole map and room browser.
The whole-map image links to individual rooms. You can also ask for
`render_map_overview`, `render_room_preview`, `render_all_rooms`, or
`inspect_gameplay_map`. The `map_path` argument is relative to the selected
mod project. If that project contains exactly one map, it may be omitted.

Previews and extracted sprites are stored in the install folder, outside the
mod project. The installer checks the map hash before and after its smoke
test. For a local test without changing Codex configuration, pass
`-SkipCodexRegistration` and an optional `-InstallDir`.

## Development

### Inferred room progression

`progression.py` uses the same geometry and spawn algorithm for every map.
It contains no chapter-specific room lists and never loads Berry Camp's orders
at runtime. Each room appears once, including dummy, cinematic, and credits
rooms that a community guide may omit.

```text
Saved room bounds + first spawns
          │
          ▼
Touching-edge candidates ──> start/name hints for each component
          │
          ▼
Spawn-weighted shortest-path tree
          │
          ▼
Small branches before long continuations ──> dropdown / Previous / Next

Berry Camp's independent order lists ──> validation report only
```

Positive edge costs make the browsing tree cycle-free. Iterative traversal
avoids a recursion limit on long custom maps. Deterministic natural names break
ties and organize disconnected rooms. A missing spawn uses the room center.
The resulting metadata reports component starts, candidate/parent links,
missing evidence, and limitations. It does not claim a verified playable route;
scripted transitions and authored branch preferences can differ.

The algorithm uses Python's standard-library [heapq priority queue](https://docs.python.org/3/library/heapq.html).
[Berry Camp](https://berrycamp.github.io/) supplies independent test references
for 27 maps across all 11 listed chapters. Tests retain those references under
`tests/fixtures/`, following the repository's existing `unittest` workflow.
The [chapter-by-chapter results](docs/progression-validation.md) record exact
matches separately from pair-order agreement and source-room coverage.

Reproduce the read-only comparison with:

```powershell
python tools/verify_progression.py `
  --maps-dir 'D:\SteamLibrary\steamapps\common\Celeste\Content\Maps'
$env:CELESTE_TEST_MAPS = 'D:\SteamLibrary\steamapps\common\Celeste\Content\Maps'
python -m unittest discover -s tests -p 'test_*.py' -q
```

Use `python tools/verify_progression.py --check-site` for an optional network
check of the pinned fixture against all 27 published chapter-side pages.

The map extractor accepts partial edge tiles because vanilla Resort B-side
and Summit credits include room dimensions that are not multiples of eight.
Exact world bounds are preserved; no game files are changed.

### Loenn whole-map connection prototype

Step 1 is a development prototype. It leaves the installed MCP tool and the
current overview renderer in place. The proposed browsing flow is:

```text
Source .bin (read only) ──> disposable output snapshot
                            ├── installed loenn-mcp ──> whole-map HTML
                            └── viewer room renderer ──> all room images

Loenn room index ──> full saved room name ──> existing room browser
                                              └── Whole map returns to Loenn
```

Generate a Forsaken City sample with the viewer's Python environment:

```powershell
python tools/prototype_loenn_browser.py `
  --workspace 'D:\SteamLibrary\steamapps\common\Celeste\Mods\YourMod' `
  --output 'outputs/loenn-prototype' `
  --map '1-ForsakenCity.bin' --source vanilla
```

Open the returned `index.html`. It embeds full-resolution lossless room
images; the smaller fragment is an optional compressed preview. Source hashes
are checked after rendering. Generated Loenn HTML and map snapshots are under
ignored `outputs/`; upstream server source is never copied into this repo.

The adapter currently targets the pinned `loenn-mcp==5.2.0`. That version's
generated HTML initializes the minimap too early; the adapter defers its first
draw in the generated document only. Room indices are checked against the
unfiltered source order. The [upstream renderer](https://github.com/Magedeline/loenn-mcp)
and [MDN iframe documentation](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe)
informed the isolated `srcdoc` frame and source-checked message bridge. This
preserves upstream zoom, search, and pan without mixing its styles with the
room browser. A development browser check is available as
`node tests/loenn-prototype-check.cjs <index.html> [playwright-module] [browser-executable]`.

This prototype does not yet change the public MCP result format or installer;
those follow after the preview is accepted.

The repository keeps runtime code together and separates development tools:

```text
celeste_gameplay_viewer/  Python modules and HTML/JS preview assets
tests/                    Automated viewer and browser checks
tools/                    Sprite extraction and install verification
run_server.py             Small Codex stdio entry point
install.ps1               Windows installer
requirements.txt          Separately installed PyPI dependencies
```

`tools/extract_sprites.py` decodes selected frames from an installed Celeste
atlas; generated PNGs and their manifest are ignored by Git. Never commit
those generated files.

After installing dependencies in a local virtual environment, run:

```powershell
python -m unittest discover -s tests -p 'test_*.py' -q
```

The package-at-root layout follows the [Python Packaging User Guide's flat-layout convention](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/).
It keeps the existing script-based installer simple; a `src/` layout would
require an extra package installation step. The stdio entry point follows the
official [FastMCP quickstart](https://github.com/PrefectHQ/fastmcp/blob/main/docs/getting-started/quickstart.mdx)
and the maintained [FastMCP repository](https://github.com/PrefectHQ/fastmcp)
is the reference example. Codex stores
MCP registrations in `~/.codex/config.toml`; the installer uses `codex mcp add`
and preserves a backup before changing that file.

## Credits and third-party components

- [Berry Camp](https://berrycamp.github.io/), by wishcresp and contributors,
  supplies the independent room-order validation data. Its reference lists are
  used only in tests and reports, never to override the inference algorithm.

- [`loenn-mcp`](https://github.com/Magedeline/loenn-mcp) by Maggy Studio is a
  separately installed, MIT-licensed PyPI dependency used here to read the
  Celeste `.bin` format. Its editing server and source code are not packaged
  in this repository.
- [Lönn](https://github.com/CelestialCartographers/Loenn) by Celestial
  Cartographers informed the atlas-frame extraction method and Celeste map
  conventions. This repository does not include Lönn.
- [FastMCP](https://github.com/PrefectHQ/fastmcp) provides the MCP server and
  client implementation as a separately installed dependency.
- Celeste artwork is extracted locally from each user's own game copy for
  previews. Those PNGs are not part of this repository or its MIT license.

This project is an independent fan-made tool and is not affiliated with
Extremely OK Games, the Celeste team, Lönn, or Maggy Studio.
