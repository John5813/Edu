"""«Rahmat» personaj tanlash savolining rasmi: barcha personajlar kollaji (`assets/thanks_anim/menu.jpg`).

Rasm «🎬 Personaj tanlash» tugmasi ustida turadi — mijoz nima tanlashini ko'rib tushunadi (boshqa namuna
rasmlari — `assets/taqdimot/*.jpg` — bilan bir xil ko'rinish). Namunalar (`poster.jpg`) tayyor bo'lgach ishga tushiring:

    python tools/thanks_anim/menu_image.py
"""
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from services.thanks_anim import catalog  # noqa: E402

COLUMNS, TILE_W, GAP = 6, 320, 8
BG = (17, 20, 27)


def main() -> str:
    anims = catalog.available()
    rows = (len(anims) + COLUMNS - 1) // COLUMNS
    tile_h = TILE_W * 9 // 16
    sheet = Image.new("RGB", (COLUMNS * TILE_W + (COLUMNS + 1) * GAP, rows * tile_h + (rows + 1) * GAP), BG)
    for i, anim in enumerate(anims):
        row, col = divmod(i, COLUMNS)
        tile = Image.open(anim.path("poster.jpg")).convert("RGB").resize((TILE_W, tile_h), Image.LANCZOS)
        sheet.paste(tile, (GAP + col * (TILE_W + GAP), GAP + row * (tile_h + GAP)))
    out = os.path.join(catalog.ASSETS, "menu.jpg")
    sheet.save(out, quality=86, optimize=True)
    print("✓", out, sheet.size, f"{os.path.getsize(out) // 1024} KB")
    return out


if __name__ == "__main__":
    main()
