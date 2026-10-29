"""Yuklangan katalogni tekshirish: katalog.json dagi har model diskda bormi va GLB to'g'rimi.

    python tools/katalog3d/tekshir.py data/katalog3d/katalog.json data/katalog3d_modellar
"""
import json
import os
import sys


def main():
    katalog_json, models_dir = sys.argv[1:3]
    modellar = json.load(open(katalog_json, encoding="utf-8"))["modellar"]
    yoq, buzuq, hajm = [], [], 0
    for m in modellar:
        path = os.path.join(models_dir, m["fayl"])
        if not os.path.isfile(path):
            yoq.append(m["id"])
            continue
        with open(path, "rb") as fh:
            if fh.read(4) != b"glTF":
                buzuq.append(m["id"])
        hajm += os.path.getsize(path)
    print(f"katalog: {len(modellar)} ta, diskda: {len(modellar) - len(yoq)} ta, {hajm / 1e9:.1f} GB")
    if yoq:
        print(f"yo'q ({len(yoq)}): {', '.join(yoq[:20])}{' ...' if len(yoq) > 20 else ''}")
    if buzuq:
        print(f"buzuq ({len(buzuq)}): {', '.join(buzuq[:20])}")
    sys.exit(1 if buzuq else 0)


if __name__ == "__main__":
    main()
