# Berry Camp progression reference

`berrycamp-order.json` contains the independently curated room orders from
[Berry Camp](https://berrycamp.github.io/), by wishcresp and contributors.
The fixture records its upstream commit, source URL, and source-data hash.
Only checkpoint room identifiers and chapter metadata are retained; it includes
no room artwork, tiles, or game binaries.

This file is validation data. The runtime progression module never reads it.
The runtime must not be changed to select these lists as vanilla overrides.
Missing source rooms, extra saved rooms, exact sequence matches, and pair-order
agreement are reported separately by `tools/verify_progression.py`.

Refresh deliberately by downloading `data/celeste.json` at a reviewed upstream
commit into ignored outputs, updating the import tool's provenance if needed,
and running `python tools/verify_progression.py --import-reference <download>`.
The source repository publishes under the MIT license, retained here as
`LICENSE-berrycamp.txt`.
