"""Draw vector primitives directly at high resolution using logical pixels."""

from PIL import Image, ImageDraw, ImageFont


class RasterCanvas:
    """Scale coordinates, strokes, and fonts before rasterizing, not afterward."""

    def __init__(self, width: int, height: int, background: str, factor: int):
        self.factor = factor
        self.image = Image.new("RGB", (width*factor, height*factor), background)
        self.drawing = ImageDraw.Draw(self.image)
        self.metrics = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        self.fonts = {}
        self.marker_fonts = {}

    def _coordinates(self, coordinates):
        return tuple(self._coordinates(value) if isinstance(value, (tuple, list))
                     else value*self.factor for value in coordinates)

    def _shape(self, method, coordinates, **kwargs):
        if "width" in kwargs:
            kwargs["width"] = max(1, round(kwargs["width"]*self.factor))
        getattr(self.drawing, method)(self._coordinates(coordinates), **kwargs)

    def rectangle(self, coordinates, **kwargs):
        self._shape("rectangle", coordinates, **kwargs)

    def ellipse(self, coordinates, **kwargs):
        self._shape("ellipse", coordinates, **kwargs)

    def polygon(self, coordinates, **kwargs):
        self._shape("polygon", coordinates, **kwargs)

    def line(self, coordinates, **kwargs):
        self._shape("line", coordinates, **kwargs)

    def text(self, position, text, font, **kwargs):
        # Retain the font object: temporary font IDs can be reused mid-render.
        key = font
        if key not in self.fonts:
            self.fonts[key] = font.font_variant(size=font.size*self.factor)
        self.drawing.text(self._coordinates(position), text,
                          font=self.fonts[key], **kwargs)

    def textbbox(self, position, text, **kwargs):
        return self.metrics.textbbox(position, text, **kwargs)

    def sprite(self, image, position, scale=1):
        """Composite RGBA pixel art at logical top-left using nearest sampling."""
        size = tuple(max(1, round(value*scale*self.factor)) for value in image.size)
        sprite = image.resize(size, Image.Resampling.NEAREST)
        location = tuple(round(value*self.factor) for value in position)
        self.image.paste(sprite, location, sprite)

    def anchor_marker(self, position, kind, radius, color, background, font_size):
        """Draw the shared S spawn or C checkpoint glyph centered on an anchor."""
        x, y = position
        if kind == "player":
            self.ellipse((x-radius, y-radius, x+radius, y+radius),
                         fill=background, outline=color, width=max(.5, radius/4))
        else:
            self.polygon([(x, y-radius), (x+radius, y), (x, y+radius), (x-radius, y)],
                         fill=color)
        if font_size not in self.marker_fonts:
            self.marker_fonts[font_size] = ImageFont.load_default(size=font_size)
        self.text((x, y), "S" if kind == "player" else "C",
                  font=self.marker_fonts[font_size], anchor="mm",
                  fill=color if kind == "player" else background)
