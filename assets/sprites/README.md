# Local game frames

`install.ps1` extracts the few preview frames this viewer uses from your own
Celeste installation. They are ignored by Git and must not be included in a
public release. Celeste artwork belongs to its respective owners; the MIT
license for this repository applies only to the viewer's original code.

The extractor writes `manifest.json` with atlas and PNG hashes. Its atlas
format and trim placement follow [Lönn's sprite loader](https://github.com/CelestialCartographers/Loenn/blob/master/src/sprite_loader.lua).
