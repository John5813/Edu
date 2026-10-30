"""Niqoblarni yig'ish: `rasm.mjs --maska` chizgan `<katalog>/<fan>/<id>/mask.png` (fonsiz RGBA) dan
faqat shaffoflik kanali olinadi va `data/katalog3d/mask/<id>.png` (kulrang, ~1,5 KB) ga yoziladi.

3D taqdimotda niqob 3D ob'ekt ichidagi zaxira rasmni (3D ko'rinmaydigan dasturlar uchun) fonsiz qiladi:
preview rasmi bilan bir xil burchak va kadr, shuning uchun model chetlari aniq kesiladi.

    python tools/katalog3d/maska.py <katalog>
"""
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from services import katalog3d  # noqa: E402


def main(src: str) -> None:
    os.makedirs(katalog3d.MASK_DIR, exist_ok=True)
    done = missing = 0
    for mid, m in katalog3d.katalog().items():
        path = os.path.join(src, os.path.dirname(m["fayl"]), "mask.png")
        if not os.path.isfile(path):
            missing += 1
            continue
        with Image.open(path) as im:
            alpha = im.convert("RGBA").getchannel("A")
        alpha.save(os.path.join(katalog3d.MASK_DIR, mid + ".png"), optimize=True)
        done += 1
    print(f"niqob: {done} ta yozildi, {missing} ta yo'q")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else katalog3d.MODELS_DIR)
