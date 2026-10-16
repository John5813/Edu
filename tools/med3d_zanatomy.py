"""Z-Anatomy bosh mushaklarini atlasimizga qo'shish (bir martalik tayyorlash).

BodyParts3D'da (erkak atlas) chaynov va yuz mushaklari yo'q. Z-Anatomy (CC BY-SA 4.0, BodyParts3D asosida)
ularni to'liq beradi: chaynov, chakka, qanotsimon mushaklar, mimika mushaklari, ko'z olmasi mushaklari va
boshqalar. Ishlash tartibi:

    blender -b Z-Anatomy/Startup.blend --python tools/med3d_zanatomy_blender.py -- /tmp/za head
    python tools/med3d_zanatomy.py /tmp/za head          # yoki: joints (boylamlar), nerves (nervlar), extra

Ikkinchi qadam Blender koordinatalarini atlasnikiga o'tkazadi (Z yuqori → Y yuqori, -Y old → +Z old),
so'ng skelet suyaklari bo'yicha masshtab va siljishni hisoblaydi (eng kichik kvadratlar) va har qismni eng yaqin
uchta suyak bo'yicha yana mahalliy tuzatadi — boylam o'z suyaklariga aniq tegib turadi. Natija
`assets/med3d/zanatomy/` — atlas formatidagi qo'shimcha katalog (`atlas-za-<to'plam>.json` + `za-<to'plam>.bin`):
`Atlas` ularni erkak tanasiga qo'shib o'qiydi. Qismlar tizimi: za-muscular, za-joint, za-nervous; boylam nomida
Z-Anatomy to'plami (bo'g'im) kvadrat qavsda turadi: "Left anterior cruciate ligament [Knee joint; ...]".
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from services.med3d import ZA_DIR, manba  # noqa: E402
from services.med3d.simplify import simplify  # noqa: E402

SYSTEMS = {"head": "za-muscular", "joints": "za-joint", "nerves": "za-nervous", "extra": "za-organ"}
KINDS = {"head": "muscle", "joints": "joint", "nerves": "nerve", "extra": "organ"}
# Z-Anatomy suyak nomi → atlasdagi nomi (nomlar farq qiladiganlari)
RENAME = {"atlas (c1)": "atlas", "axis (c2)": "axis", "navicular bone": "navicular bone of foot",
          "triquetrum bone": "triquetral", "manubrium of sternum": "manubrium"}
for _w in ("scaphoid", "lunate", "pisiform", "hamate", "trapezium", "trapezoid", "capitate"):
    RENAME[_w + " bone"] = _w
for _n, _w in enumerate(("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
                         "eleventh", "twelfth"), 1):
    RENAME[f"vertebra t{_n}"] = f"{_w} thoracic vertebra"
    if _n <= 7:
        RENAME[f"vertebra c{_n}"] = f"{_w} cervical vertebra"
    if _n <= 5:
        RENAME[f"vertebra l{_n}"] = f"{_w} lumbar vertebra"
GENERIC = {"3: Joints", "Trunk", "Left lower limb", "Right lower limb", "Left upper limb", "Right upper limb",
           "Left foot", "Right foot", "Left hand", "Right hand", "Back", "Thorax", "Abdomen", "Neck", "Head",
           "Nerves", "Peripheral nervous system", "Central nervous system"}
# Nervlar Z-Anatomy'da egri chiziqdan yasalgan zich naychalar (~1.1 mln uchburchak): har biri shu ulushgacha
# soddalashtiriladi — shakli o'zgarmaydi, fayl ~4 baravar kichrayadi.
NERVE_SHARE = 0.25


def atlas_name(name: str, by_lower: dict):
    """Z-Anatomy suyagi → atlasdagi qism nomi (yo'q bo'lsa None)."""
    side = ""
    if re.search(r"\.[lr]$", name):
        side, name = ("left " if name[-1] == "l" else "right "), name[:-2]
    base = RENAME.get(name.lower(), name.lower())
    for cand in (side + base, base):
        if cand in by_lower:
            return by_lower[cand]
    return None


def _read(raw_dir: str, which: str):
    with open(os.path.join(raw_dir, f"za_raw_{which}.json")) as fh:
        meta = json.load(fh)
    buf = open(os.path.join(raw_dir, f"za_raw_{which}.bin"), "rb").read()
    out = []
    for p in meta["parts"]:
        pos = np.frombuffer(buf, "<f4", p["n"] * 3, p["pos"]).reshape(-1, 3)
        nrm = np.frombuffer(buf, "<f4", p["n"] * 3, p["nrm"]).reshape(-1, 3)
        idx = np.frombuffer(buf, "<u4", p["m"], p["idx"]).astype(np.uint32)
        swap = lambda a: np.stack([a[:, 0], a[:, 2], -a[:, 1]], axis=1)   # noqa: E731
        out.append(dict(name=p["name"], kind=p["kind"], cols=p.get("cols", []), pos=swap(pos), nrm=swap(nrm), idx=idx))
    return out


def fit(parts, atlas) -> tuple:
    """atlas = s · za + t (s — bitta masshtab, t — siljish): suyaklar chegaralari bo'yicha. Qaytaradi: s, t, xato,
    va mahalliy tuzatish uchun juftliklar [(za markazi, atlas markazi)]."""
    by_lower = {name.lower(): name for name in atlas.by_name}
    rows, rhs, pairs = [], [], []
    for p in parts:
        target = atlas_name(p["name"], by_lower) if p["kind"] == "bone" else None
        if not target:
            continue
        ref = atlas.mesh(target)[0]
        pairs.append((p["pos"].mean(0), ref.mean(0)))
        for za, at in ((p["pos"].min(0), ref.min(0)), (p["pos"].max(0), ref.max(0)), (p["pos"].mean(0), ref.mean(0))):
            for axis in range(3):
                row = [za[axis], 0.0, 0.0, 0.0]
                row[1 + axis] = 1.0
                rows.append(row)
                rhs.append(at[axis])
    sol, *_ = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)
    err = np.abs(np.array(rows) @ sol - np.array(rhs)).mean()
    return float(sol[0]), sol[1:].astype(np.float32), float(err), pairs


def local_shift(center, scale, shift, pairs, k: int = 3, radius: float = 0.15) -> np.ndarray:
    """Eng yaqin k ta suyakning qoldiq xatosi o'rtachasi (uzoqroqlari kuchsizroq hisoblanadi)."""
    if not pairs:
        return np.zeros(3, np.float32)
    za = np.array([a for a, _ in pairs]) * scale + shift
    at = np.array([b for _, b in pairs])
    dist = np.linalg.norm(za - (center * scale + shift), axis=1)
    near = np.argsort(dist)[:k]
    near = [i for i in near if dist[i] < radius]
    if not near:
        return np.zeros(3, np.float32)
    w = 1.0 / (dist[near] + 0.01)
    return ((at[near] - za[near]) * w[:, None]).sum(0) / w.sum()


def nice_name(name: str) -> str:
    if re.search(r"\.[lr]$", name):
        base, side = name[:-2], name[-1]
        return f"{'Left' if side == 'l' else 'Right'} {base[0].lower()}{base[1:]}"
    return name


def main(argv) -> int:
    raw_dir, which = argv[0], (argv[1] if len(argv) > 1 else "head")
    parts = _read(raw_dir, which)
    atlas = manba.atlas("male")
    scale, shift, err, pairs = fit(parts, atlas)
    print(f"moslash: {len(pairs)} suyak, masshtab {scale:.4f}, siljish {np.round(shift, 4)}, "
          f"o'rtacha xato {err * 1000:.1f} mm")
    os.makedirs(ZA_DIR, exist_ok=True)
    catalog, off, seen = [], 0, set()
    binname = f"za-{which}.bin"
    with open(os.path.join(ZA_DIR, binname), "wb") as fh:
        for p in parts:
            if p["kind"] != KINDS[which]:
                continue
            if which == "nerves" and len(p["idx"]) > 3000:
                q, nn, ii = simplify(p["pos"], p["nrm"], p["idx"], max(800, int(len(p["idx"]) // 3 * NERVE_SHARE)))
                p = dict(p, pos=q, nrm=nn, idx=ii.astype(np.uint32))
            fix = local_shift(p["pos"].mean(0), scale, shift, pairs)
            pos = (p["pos"] * scale + shift + fix).astype("<f4")
            nrm = p["nrm"] / np.maximum(np.linalg.norm(p["nrm"], axis=1, keepdims=True), 1e-9)
            nrm = np.round(nrm * 32767).astype("<i2")
            name = nice_name(p["name"])
            groups = [c for c in p["cols"] if c not in GENERIC and not c[:2].rstrip(":").isdigit()]
            if which != "head" and groups:
                name += " [" + "; ".join(groups) + "]"
            pid = "ZA-" + re.sub(r"[^a-z0-9]+", "-", nice_name(p["name"]).lower()).strip("-")
            while pid in seen:
                pid += "-x"
            seen.add(pid)
            rec = {"id": pid, "name": name, "system": SYSTEMS[which], "chunk": 0,
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
    doc = {"version": "Z-Anatomy (CC BY-SA 4.0)", "chunks": [{"url": binname}], "parts": catalog}
    with open(os.path.join(ZA_DIR, f"atlas-za-{which}.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=0)
    print(f"{len(catalog)} qism, {off / 1e6:.1f} MB →", ZA_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
