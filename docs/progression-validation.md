# Progression validation against Berry Camp

Verified on 2026-10-11 with the locally installed Celeste maps. The pinned
reference fixture also matches the displayed room lists on all 27 published
Berry Camp chapter-side pages.

All 824 saved rooms are preserved, including 20 rooms absent from the reference.
The reference covers 804 rooms. Fifteen map sequences match exactly; twelve
differ. Overall pair-order agreement is 95.6%, versus 91.4% for the old generic
natural-name fallback. This aggregate hides weaker cases: Celestial Resort
A-side and Epilogue need further inference work, and Old Site A-side remains
ambiguous. The table below reports them individually.

One geometry/spawn algorithm is used for every map. Reference lists are tests only.
All source rooms are retained. Extra rooms are excluded from reference-order scoring.

| Map | Saved / reference rooms | Exact order | Same positions | Relative order | Extra rooms |
| --- | --- | --- | --- | --- | --- |
| 0-Intro.bin | 7 / 6 | Yes | 6 / 6 | 100.0% | lvl_x1 |
| 1-ForsakenCity.bin | 38 / 38 | No | 24 / 38 | 98.6% | — |
| 1H-ForsakenCity.bin | 16 / 16 | Yes | 16 / 16 | 100.0% | — |
| 1X-ForsakenCity.bin | 3 / 3 | Yes | 3 / 3 | 100.0% | — |
| 2-OldSite.bin | 45 / 45 | No | 17 / 45 | 82.8% | — |
| 2H-OldSite.bin | 17 / 17 | Yes | 17 / 17 | 100.0% | — |
| 2X-OldSite.bin | 3 / 3 | Yes | 3 / 3 | 100.0% | — |
| 3-CelestialResort.bin | 65 / 65 | No | 5 / 65 | 66.4% | — |
| 3H-CelestialResort.bin | 24 / 24 | Yes | 24 / 24 | 100.0% | — |
| 3X-CelestialResort.bin | 4 / 3 | Yes | 3 / 3 | 100.0% | lvl_02-dummy |
| 4-GoldenRidge.bin | 49 / 48 | No | 41 / 48 | 99.4% | lvl_a-05x |
| 4H-GoldenRidge.bin | 20 / 20 | Yes | 20 / 20 | 100.0% | — |
| 4X-GoldenRidge.bin | 3 / 3 | Yes | 3 / 3 | 100.0% | — |
| 5-MirrorTemple.bin | 85 / 85 | No | 32 / 85 | 96.9% | — |
| 5H-MirrorTemple.bin | 25 / 25 | No | 17 / 25 | 95.3% | — |
| 5X-MirrorTemple.bin | 3 / 3 | Yes | 3 / 3 | 100.0% | — |
| 6-Reflection.bin | 64 / 64 | No | 56 / 64 | 99.7% | — |
| 6H-Reflection.bin | 28 / 28 | Yes | 28 / 28 | 100.0% | — |
| 6X-Reflection.bin | 3 / 3 | Yes | 3 / 3 | 100.0% | — |
| 7-Summit.bin | 107 / 95 | No | 83 / 95 | 99.8% | lvl_a-00-intro, lvl_credits-city, lvl_credits-clouds, lvl_credits-dashes, lvl_credits-payphone, lvl_credits-prologue, lvl_credits-resort, lvl_credits-summit, lvl_credits-tree, lvl_credits-walking, lvl_credits-wallslide, lvl_d-05x |
| 7H-Summit.bin | 29 / 28 | Yes | 28 / 28 | 100.0% | lvl_a-00-intro |
| 7X-Summit.bin | 3 / 3 | Yes | 3 / 3 | 100.0% | — |
| 8-Epilogue.bin | 4 / 4 | No | 1 / 4 | 66.7% | — |
| 9-Core.bin | 39 / 39 | No | 29 / 39 | 98.0% | — |
| 9H-Core.bin | 23 / 23 | No | 21 / 23 | 98.8% | — |
| 9X-Core.bin | 4 / 4 | Yes | 4 / 4 | 100.0% | — |
| LostLevels.bin | 113 / 109 | No | 105 / 109 | 99.9% | lvl_e-03-dummy, lvl_e-05b-dummy, lvl_end-cinematic, lvl_end-granny |

Exact order means every reference room is at the expected index.
Relative order measures concordant room pairs; it does not verify a playable route.

Reference: https://raw.githubusercontent.com/berrycamp/berrycamp.github.io/bd24de2d6a022d899adff406ee9aad397106301d/data/celeste.json
