"""Z-Anatomy bosh mushaklarini atlasimizga qo'shish (bir martalik tayyorlash).

BodyParts3D'da (erkak atlas) chaynov va yuz mushaklari yo'q. Z-Anatomy (CC BY-SA 4.0, BodyParts3D asosida)
ularni to'liq beradi: chaynov, chakka, qanotsimon mushaklar, mimika mushaklari, ko'z olmasi mushaklari va
boshqalar. Ishlash tartibi:

    blender -b Z-Anatomy/Startup.blend --python tools/med3d_zanatomy_blender.py -- /tmp/za
    python tools/med3d_zanatomy.py /tmp/za

Ikkinchi qadam Blender koordinatalarini atlasnikiga o'tkazadi (Z yuqori → Y yuqori, -Y old → +Z old),
so'ng bosh suyagi suyaklari bo'yicha masshtab va siljishni hisoblab (eng kichik kvadratlar) mushaklarni
erkak atlas skeletiga aniq joylaydi. Natija `assets/med3d/zanatomy/` — atlas formatidagi qo'shimcha katalog
(`atlas-za.json` + `za-0.bin`): `Atlas` uni erkak tanasiga qo'shib o'qiydi, qismlar tizimi — "za-muscular".
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from services.med3d import ZA_DIR, manba  # noqa: E402

# Z-Anatomy suyagi → erkak atlasdagi nomi (moslash uchun)
BONE_PAIRS = {"Mandible": "Mandible", "Frontal bone": "Frontal bone", "Occipital bone": "Occipital bone",
              "Sphenoid bone": "Sphenoid bone"}
for side, word in (("l", "Left"), ("r", "Right")):
    for bone in ("temporal bone", "parietal bone", "zygomatic bone", "maxilla", "nasal bone"):
        BONE_PAIRS[f"{bone[0].upper()}{bone[1:]}.{side}"] = f"{word} {bone}"


def _read(raw_dir: str):
    with open(os.path.join(raw_dir, "za_raw.json")) as fh:
        meta = json.load(fh)
    buf = open(os.path.join(raw_dir, "za_raw.bin"), "rb").read()
    out = []
    for p in meta["parts"]:
        pos = np.frombuffer(buf, "<f4", p["n"] * 3, p["pos"]).reshape(-1, 3)
        nrm = np.frombuffer(buf, "<f4", p["n"] * 3, p["nrm"]).reshape(-1, 3)
        idx = np.frombuffer(buf, "<u4", p["m"], p["idx"]).astype(np.uint32)
        swap = lambda a: np.stack([a[:, 0], a[:, 2], -a[:, 1]], axis=1)   # noqa: E731
        out.append(dict(name=p["name"], kind=p["kind"], pos=swap(pos), nrm=swap(nrm), idx=idx))
    return out


def fit(parts, atlas) -> tuple:
    """atlas = s · za + t (s — bitta masshtab, t — siljish): suyaklar chegaralari bo'yicha."""
    rows, rhs = [], []
    for p in parts:
        target = BONE_PAIRS.get(p["name"])
        if p["kind"] != "bone" or not target or target not in atlas.by_name:
            continue
        ref = atlas.mesh(target)[0]
        for za, at in ((p["pos"].min(0), ref.min(0)), (p["pos"].max(0), ref.max(0)),
                       (p["pos"].mean(0), ref.mean(0))):
            for axis in range(3):
                row = [za[axis], 0.0, 0.0, 0.0]
                row[1 + axis] = 1.0
                rows.append(row)
                rhs.append(at[axis])
    sol, *_ = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)
    err = np.abs(np.array(rows) @ sol - np.array(rhs)).mean()
    return float(sol[0]), sol[1:].astype(np.float32), float(err)


def nice_name(name: str) -> str:
    base, side = name[:-2], name[-1]
    return f"{'Left' if side == 'l' else 'Right'} {base[0].lower()}{base[1:]}"


def main(argv) -> int:
    raw_dir = argv[0]
    parts = _read(raw_dir)
    atlas = manba.atlas("male")
    scale, shift, err = fit(parts, atlas)
    print(f"moslash: masshtab {scale:.4f}, siljish {np.round(shift, 4)}, o'rtacha xato {err * 1000:.1f} mm")
    os.makedirs(ZA_DIR, exist_ok=True)
    catalog, off = [], 0
    with open(os.path.join(ZA_DIR, "za-0.bin"), "wb") as fh:
        for p in parts:
            if p["kind"] != "muscle":
                continue
            pos = (p["pos"] * scale + shift).astype("<f4")
            nrm = p["nrm"] / np.maximum(np.linalg.norm(p["nrm"], axis=1, keepdims=True), 1e-9)
            nrm = np.round(nrm * 32767).astype("<i2")
            rec = {"id": "ZA-" + re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-"),
                   "name": nice_name(p["name"]), "system": "za-muscular", "chunk": 0,
                   "vertexCount": len(pos), "indexCount": len(p["idx"]),
                   "bounds": [pos.min(0).round(5).tolist(), pos.max(0).round(5).tolist()]}
            for key, arr in (("positions", pos), ("normals", nrm), ("indices", p["idx"].astype("<u4"))):
                pad = -off % 4
                fh.write(b"\0" * pad)
                off += pad
                rec[key] = off
                fh.write(arr.tobytes())
                off += arr.nbytes
            catalog.append(rec)
    doc = {"version": "Z-Anatomy (CC BY-SA 4.0)", "chunks": [{"url": "za-0.bin"}], "parts": catalog}
    with open(os.path.join(ZA_DIR, "atlas-za.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=0)
    print(f"{len(catalog)} qism, {off / 1e6:.1f} MB →", ZA_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
