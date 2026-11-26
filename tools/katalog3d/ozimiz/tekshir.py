"""Har qanday fonda ko'rinishni tekshirish: har model preview'i oq va to'q ko'k fonda yonma-yon (bitta jadval rasmi).

    python tools/katalog3d/ozimiz/tekshir.py ozimiz_kimyo natija.png
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
KAT = os.path.join(ROOT, "data", "katalog3d")
LIGHT, DARK = (246, 246, 244), (8, 20, 48)


def sheet(json_name, out_path, cell=170, cols=6):
    ms = json.load(open(os.path.join(KAT, json_name + ".json"), encoding="utf-8"))["modellar"]
    rows = (len(ms) + cols - 1) // cols
    W, H = cols * cell * 2, rows * (cell + 22)
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except OSError:
        font = ImageFont.load_default()
    for k, m in enumerate(ms):
        prev = Image.open(os.path.join(KAT, "preview", m["id"] + ".jpg")).convert("RGB").resize((cell, cell))
        mask = Image.open(os.path.join(KAT, "mask", m["id"] + ".png")).convert("L").resize((cell, cell))
        x, y = (k % cols) * cell * 2, (k // cols) * (cell + 22)
        for j, bg in enumerate((LIGHT, DARK)):
            tile = Image.new("RGB", (cell, cell), bg)
            tile.paste(prev, (0, 0), mask)
            img.paste(tile, (x + j * cell, y))
        d.text((x + 4, y + cell + 4), f"{k + 1}. {m['nom_uz'][:44]}", fill=(0, 0, 0), font=font)
    img.save(out_path)
    return len(ms)


if __name__ == "__main__":
    print(sheet(sys.argv[1], sys.argv[2]))
