"""Load the small local set of original game frames used by the previewer."""

from functools import lru_cache
from pathlib import Path

from PIL import Image

SPRITES = Path(__file__).parent / "assets/sprites"


@lru_cache(maxsize=32)
def load_sprite(texture: str):
    """Return an RGBA frame, or None when this texture is not installed."""
    path = SPRITES / (texture.replace("/", "-").replace("\\", "-") + ".png")
    if not path.is_file():
        return None
    with Image.open(path) as image:
        return image.convert("RGBA")


def spike_sprites(entity: dict):
    """Return (image, x, y) using Lonn's eight-pixel step and justification.

    Positions are local game pixels. Unsupported custom/tentacle variants
    return an empty list so the caller can use and report a schematic fallback.
    """
    direction = entity["type"].removeprefix("spikes").lower()
    variant = entity.get("properties", {}).get("type", "default")
    image = load_sprite(f"danger/spikes/{variant}_{direction}00")
    if image is None:
        return []
    offset_x, offset_y, justify_x, justify_y = {
        "up": (4, 1, .5, 1), "down": (4, -1, .5, 0),
        "left": (1, 4, 1, .5), "right": (-1, 4, 0, .5),
    }[direction]
    vertical = direction in {"left", "right"}
    length = entity["h" if vertical else "w"] or 8
    return [(image,
             entity["x"]+offset_x-image.width*justify_x+(0 if vertical else step),
             entity["y"]+offset_y-image.height*justify_y+(step if vertical else 0))
            for step in range(0, int(length), 8)]


def object_sprite(entity: dict):
    """Return a fixed-size original frame and top-left in local game pixels.

    Small clouds require nonuniform scaling, so retain their schematic instead.
    Quarter-turns for wall springs preserve every pixel without distortion.
    """
    kind = entity["type"]
    props = entity.get("properties", {})
    texture = {
        "cassette": "collectables/cassette/idle00",
        "key": "collectables/key/idle00",
        "badelineBoost": "objects/badelineboost/idle00",
        "spring": "objects/spring/00",
        "wallSpringLeft": "objects/spring/00",
        "wallSpringRight": "objects/spring/00",
    }.get(kind)
    if kind == "strawberry":
        texture = "collectables/strawberry/wings01" if props.get("winged") else "collectables/strawberry/normal00"
        if props.get("moon"):
            texture = "collectables/moonBerry/normal00"
    elif kind == "goldenBerry":
        texture = "collectables/goldberry/wings01" if props.get("winged") else "collectables/goldberry/idle00"
    elif kind == "refill":
        texture = "objects/refillTwo/idle00" if entity.get("twoDash") else "objects/refill/idle00"
    elif kind == "booster":
        texture = "objects/booster/boosterRed00" if entity.get("red") else "objects/booster/booster00"
    elif kind == "cloud" and not props.get("small"):
        texture = "objects/clouds/fragile00" if props.get("fragile") else "objects/clouds/cloud00"
    elif kind == "spinner" and not props.get("dust"):
        color = props.get("color", "Blue").lower()
        texture = f"danger/crystal/fg_{color}00"
    if not texture:
        return None
    sprite = load_sprite(texture)
    if sprite is None:
        return None
    x, y = entity["x"], entity["y"]
    if kind == "spring":
        return sprite, x-sprite.width/2, y-sprite.height
    if kind == "wallSpringLeft":
        sprite = sprite.transpose(Image.Transpose.ROTATE_270)
        return sprite, x, y-sprite.height/2
    if kind == "wallSpringRight":
        sprite = sprite.transpose(Image.Transpose.ROTATE_90)
        return sprite, x-sprite.width, y-sprite.height/2
    return sprite, x-sprite.width/2, y-sprite.height/2
