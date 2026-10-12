# Viewer architecture and maintenance

The project is a Python package that serves an offline HTML/JavaScript browser
through FastMCP. The Windows installer copies explicit runtime files into an
isolated installation. The Loenn navigation experiment remains a development
tool; it consumes HTML from the separately installed `loenn-mcp` dependency.

## Responsibilities

| Module | Responsibility |
| --- | --- |
| `map_source.py` | Resolve authorized mod/vanilla paths, protect output boundaries, and hash source files. |
| `viewer.py` | Extract retained map objects and tiles, plus the existing schematic HTML view. |
| `map_geometry.py` | Analyze tile-edge openings and partition boundary styles. |
| `progression.py` | Build a spawn-weighted graph, choose component starts, browse trees, and describe inferred ordering. |
| `render_style.py` | Shared preview palette. |
| `raster.py` | Native-resolution drawing primitives and sprite compositing. |
| `room_view.py` | Prepare annotations, measure the plot, draw gameplay objects, and return room PNGs and metadata. |
| `overview.py` | Retained standalone overview renderer and MCP image result. |
| `serialization.py` | Safe script JSON and explicit PNG/lossless/compact image encoding. |
| `gallery_data.py` | Save room PNG/JSON artifacts and assemble native/compact room pages. |
| `room_gallery.py` | Compose the overview, room pages, document shell, and existing manifest. |
| `mcp_app.py` / `server.py` | Package browser delivery and expose stable MCP tools/resources. |
| `findings.py` | Inspect saved data and renderer coverage without simulating gameplay. |

```text
map_source ──> viewer extraction ──> progression
                    │                   │ browsing order only
                    ├──> room_view <────┘
                    └──> overview
                           │ PNG + metadata
                           ▼
                     gallery_data <── serialization
                           │ native / compact room pages
                           ▼
                     room_gallery <── HTML + controller + shell assets
                           │ manifest / browser payload
                           ▼
                       mcp_app ──> server ──> Codex

map_geometry + render_style ──> renderers / inspection
tools/prototype_loenn_browser ──> same room pipeline + upstream Loenn HTML
```

The text diagram stays readable in GitHub, terminals, and editors without a
diagram renderer. It records dependency direction and shared responsibilities,
not a gameplay route. Update it when a module's ownership changes.

## Browser assets and contracts

`room-gallery.html` owns markup and scoped styles. `room-gallery.js` owns
selection, native image zoom/pan, pointer handling, and saved selection.
`gallery-shell.html` provides the standalone document. Python embeds the
controller and page data inline, preserving offline and MCP App delivery.
`mcp-app-bridge.js` handles host initialization, metadata validation, and size
notifications. Prototype-specific navigation stays under `tools/prototype-assets`.

MCP tool names, resource identifiers, dictionary keys, image dimensions,
warnings, and room identity are external contracts. Refactoring internal names
must not silently change them. Former geometry/source imports from `overview`
and `viewer.resolve_map` remain compatible, while new code imports shared
helpers from their owning modules.

The room renderer intentionally draws node paths before objects, large blocks
before collectibles, and spawn/checkpoint anchors last. Fake walls clear the
preview's tile fill only. Change-respawn regions remain visible without labels.
The first saved spawn guides browsing order, not verified gameplay progression.

## Naming and formatting

Python follows [PEP 8](https://peps.python.org/pep-0008/): `snake_case` functions
and variables, `PascalCase` classes, and `UPPER_SNAKE_CASE` constants. JavaScript
uses descriptive `lowerCamelCase` locals/functions; existing DOM attributes use
kebab case. Native map fields and protocol keys retain their required spelling.
Short `x`/`y` names are reserved for local coordinate calculations.

[Black](https://black.readthedocs.io/en/stable/the_black_code_style/current_style.html)
formats Python to 79 columns. Ruff checks imports, unused/undefined names, and
basic syntax/style errors. Pyright checks types and protocol response variants
against the checkout's `.venv`, including development tools and tests.
All three are development-only dependencies recorded in
`requirements-dev.txt` and configured in `pyproject.toml`.
The existing flat package is retained; the [Flask package](https://github.com/pallets/flask/tree/main/src/flask)
is a mature reference for explicit module responsibilities, not a framework
dependency or a source-code template for this project.

Comments explain units, ordering invariants, source/output boundaries, host
state behavior, and the Loenn initialization workaround. Public functions and
complex drawing/traversal systems have docstrings. Avoid narrating obvious
assignments or adding abstractions without a concrete shared responsibility.

## Verification

Run the unit suite with `CELESTE_TEST_MAPS` set for all 27 base-map comparisons.
Use `tools/verify_progression.py` for detailed ordering reports. Renderer
refactors can use `tools/check_rendering.py --capture` before editing, then run
without `--capture` against the same hash snapshot. It compares both PNG bytes
and inspectable metadata, and verifies that source maps remain unchanged.
Snapshots stay under ignored `outputs/`; game artwork and binaries are never
golden assets in the repository.

Browser regressions cover click identity, return state, zoom, host-state
updates, mobile focus, and offline delivery. Test installer changes with an
isolated directory and `-SkipCodexRegistration` before updating an active install.
