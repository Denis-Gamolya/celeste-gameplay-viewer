"""Resolve authorized source maps and keep generated output outside Celeste."""

import hashlib
from pathlib import Path


def resolve_map(workspace: Path, map_path: str = "") -> Path:
    """Resolve a .bin inside workspace; infer it only if exactly one exists.

    Raises ValueError for ambiguous maps, traversal, or non-map paths.
    """
    workspace = workspace.resolve(strict=True)
    if not map_path:
        candidates = sorted((workspace / "Maps").rglob("*.bin"))
        if len(candidates) != 1:
            raise ValueError(
                f"Specify map_path; found {len(candidates)} maps in Maps/."
            )
        path = candidates[0].resolve(strict=True)
    else:
        path = (workspace / map_path).resolve(strict=True)
    if not path.is_relative_to(workspace):
        raise ValueError("Map must be within the configured workspace.")
    if path.suffix.lower() != ".bin" or not path.is_file():
        raise ValueError("Map must be an existing .bin file.")
    return path


def resolve_map_source(workspace: Path, map_path: str, source: str) -> Path:
    """Resolve mod input or vanilla input inside its distinct read-only root.

    Vanilla files must be under Content/Maps in the same Celeste installation
    as the configured mod. No MCP editing workspace or configuration changes.
    Raises ValueError for unknown sources, traversal, or missing vanilla paths.
    """
    if source == "mod":
        return resolve_map(workspace, map_path)
    if source != "vanilla":
        raise ValueError("Source must be mod or vanilla.")
    if not map_path:
        raise ValueError("Specify a vanilla map, e.g. 1-ForsakenCity.bin.")
    workspace = workspace.resolve(strict=True)
    mods = next(
        (
            parent
            for parent in workspace.parents
            if parent.name.lower() == "mods"
        ),
        None,
    )
    if mods is None:
        raise ValueError("Configured workspace is not inside a Mods folder.")
    return resolve_map(mods.parent / "Content" / "Maps", map_path)


def validate_preview_output(workspace: Path, output_dir: Path) -> None:
    """Reject preview output inside the mod or its Celeste installation.

    Resolve paths before checking containment, including symlinks. This shared
    guard applies to both the shipped gallery and the Loenn prototype.
    """
    workspace = workspace.resolve(strict=True)
    forbidden_roots = [workspace]
    mods = next(
        (
            parent
            for parent in workspace.parents
            if parent.name.lower() == "mods"
        ),
        None,
    )
    if mods is not None:
        forbidden_roots.append(mods.parent)
    if any(
        output_dir.resolve().is_relative_to(root) for root in forbidden_roots
    ):
        raise ValueError(
            "Preview output must be outside the Celeste installation."
        )


def hash_file(path: Path) -> str:
    """Return SHA-256 of the file's current bytes without modifying it."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
