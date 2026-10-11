"""Generate StoryKeep PWA icons on the app's real palette.

Palette (converted from src/app/globals.css oklch tokens):
  page bg   oklch(0.965 0.018 88)  -> warm cream
  top bar   oklch(0.985 0.010 88)  -> lighter cream
  primary   oklch(0.52 0.130 42)   -> terracotta
  rail ink  oklch(0.23 0.020 55)   -> dark brown ink

Outputs into frontend/public/icons/:
  icon-192.png, icon-512.png, icon-maskable-512.png
and frontend/public/apple-touch-icon.png (180x180).

Run with the Pillow venv python:
  /opt/data/cache/scratch/pilvenv/bin/python scripts/generate_pwa_icons.py
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "public")
ICON_DIR = os.path.join(OUT_DIR, "icons")

CREAM = (248, 243, 230)        # page background  oklch(0.965 0.018 88)
PRIMARY = (165, 74, 36)        # terracotta       oklch(0.52 0.13 42)
INK = (36, 27, 20)             # dark brown ink   oklch(0.23 0.02 55)
CREAM_SOFT = (253, 250, 243)   # top-bar cream    oklch(0.985 0.01 88)

SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"


def rounded_plate(size, radius_ratio, color):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = int(size * radius_ratio)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=color)
    return img


def draw_monogram(img, size, letter_color, font_ratio):
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(SERIF_BOLD, int(size * font_ratio))
    bbox = d.textbbox((0, 0), "S", font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = (size - w) / 2 - bbox[0]
    y = (size - h) / 2 - bbox[1]
    d.text((x, y), "S", font=font, fill=letter_color)


def standard_icon(size, path):
    """Cream plate, rounded corners, terracotta 'S' monogram."""
    img = rounded_plate(size, 0.22, CREAM)
    draw_monogram(img, size, PRIMARY, 0.62)
    # thin ink hairline frame keeps the mark crisp at small sizes
    d = ImageDraw.Draw(img)
    inset = int(size * 0.045)
    d.rounded_rectangle(
        [inset, inset, size - 1 - inset, size - 1 - inset],
        radius=int(size * 0.16),
        outline=INK + (110,),
        width=max(2, size // 128),
    )
    img.save(path, "PNG")
    print("wrote", path, img.size)


def maskable_icon(size, path):
    """Full-bleed terracotta plate (safe-zone padding baked in), cream 'S'."""
    img = Image.new("RGBA", (size, size), PRIMARY + (255,))
    draw_monogram(img, size, CREAM_SOFT, 0.44)  # smaller = inside 80% safe zone
    img.save(path, "PNG")
    print("wrote", path, img.size)


def apple_touch_icon(size, path):
    """iOS squashes corners; opaque square with rounded mask is standard."""
    img = rounded_plate(size, 0.0, CREAM)
    draw_monogram(img, size, PRIMARY, 0.60)
    img.save(path, "PNG")
    print("wrote", path, img.size)


def main():
    os.makedirs(ICON_DIR, exist_ok=True)
    standard_icon(192, os.path.join(ICON_DIR, "icon-192.png"))
    standard_icon(512, os.path.join(ICON_DIR, "icon-512.png"))
    maskable_icon(512, os.path.join(ICON_DIR, "icon-maskable-512.png"))
    apple_touch_icon(180, os.path.join(OUT_DIR, "apple-touch-icon.png"))


if __name__ == "__main__":
    main()
