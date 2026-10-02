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
layout stays flat to match the existing small Python project and FastMCP's
documented `server.py` stdio entry-point pattern.

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

The source files and HTML assets are the viewer. `tools/extract_sprites.py`
decodes selected frames from an installed Celeste atlas; generated PNGs and
their manifest are ignored by Git. Never commit those generated files.

After installing dependencies in a local virtual environment, run:

```powershell
python -m unittest discover -s tests -p 'test_*.py' -q
```

The structure and installer follow the [Python Packaging User Guide](https://packaging.python.org/en/latest/flow/)
for isolated environments and the official [FastMCP quickstart](https://github.com/PrefectHQ/fastmcp/blob/main/docs/getting-started/quickstart.mdx)
for a stdio server. The maintained [FastMCP repository](https://github.com/PrefectHQ/fastmcp)
is the reference example for this small source-and-tests layout. Codex stores
MCP registrations in `~/.codex/config.toml`; the installer uses `codex mcp add`
and preserves a backup before changing that file.

## Credits and third-party components

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
