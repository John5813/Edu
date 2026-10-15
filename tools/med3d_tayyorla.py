"""Bir martalik tayyorlash: human-atlas ma'lumotidan sahna guruhlarini GLB ga aylantiradi.

Hostda emas, oldindan ishlatiladi (og'ir ish — bir marta). Natija `assets/med3d/<sahna>/` ga yoziladi:
har guruh uchun `<guruh>.glb` va `scene.json` (chegara qutisi, yorliq nuqtalari uchun namunalar).
Bot ishlayotganda faqat shu tayyor fayllar o'qiladi.

    git clone --depth 1 https://github.com/ashemag/human-atlas
    python tools/med3d_tayyorla.py human-atlas/public/models            # hamma sahnalar
    python tools/med3d_tayyorla.py human-atlas/public/models skull      # bitta sahna

Ma'lumot: BodyParts3D 4.0 (DBCLS), CC BY 4.0 — manba har slaydda ko'rsatiladi.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from services.med3d import ASSETS_DIR                     # noqa: E402
from services.med3d.atlas import Atlas                     # noqa: E402
from services.med3d.catalog import SCENES, group_parts     # noqa: E402
from services.med3d.glb import Primitive, write_glb        # noqa: E402

GROUP_SAMPLES, LABEL_SAMPLES = 2000, 400


def _sample(points: np.ndarray, limit: int, seed: int) -> list:
    if len(points) > limit:
        points = points[np.random.default_rng(seed).choice(len(points), limit, replace=False)]
    return np.round(points, 4).tolist()


def _merge(meshes):
    pos, nrm, idx, base = [], [], [], 0
    for p, n, i in meshes:
        pos.append(p)
        nrm.append(n)
        idx.append(i + base)
        base += len(p)
    return np.vstack(pos), np.vstack(nrm), np.concatenate(idx)


def build_scene(atlas: Atlas, key: str, out_root: str = ASSETS_DIR) -> dict:
    spec = SCENES[key]
    names = {n for g in spec["groups"] for n in group_parts(key, g)}
    meshes = {n: atlas.mesh(n) for n in sorted(names)}
    every = np.vstack([m[0] for m in meshes.values()])
    lo, hi = every.min(axis=0), every.max(axis=0)
    center = (lo + hi) / 2                     # sahna markazi koordinata boshiga ko'chiriladi
    lo, hi = lo - center, hi - center

    out_dir = os.path.join(out_root, key)
    os.makedirs(out_dir, exist_ok=True)
    groups = {}
    for seed, (gkey, group) in enumerate(spec["groups"].items()):
        prims = []
        for color, part_names in group["materials"]:
            p, n, i = _merge([meshes[x] for x in part_names])
            prims.append(Primitive(p - center, n, i, color, name="tooth" if color[0] > 0.95 else "bone"))
        data = write_glb(prims, anchors=(lo, hi), name=gkey)
        with open(os.path.join(out_dir, f"{gkey}.glb"), "wb") as fh:
            fh.write(data)
        points = np.vstack([meshes[x][0] for x in group_parts(key, gkey)]) - center
        groups[gkey] = {"uz": group["uz"], "file": f"{gkey}.glb", "bytes": len(data),
                        "samples": _sample(points, GROUP_SAMPLES, seed)}

    labels = {}
    for seed, (lkey, (uz, part_names)) in enumerate(spec["labels"].items()):
        owner = next(g for g in spec["groups"] if part_names[0] in group_parts(key, g))
        points = np.vstack([meshes[x][0] for x in part_names]) - center
        labels[lkey] = {"uz": uz, "group": owner, "samples": _sample(points, LABEL_SAMPLES, 100 + seed)}

    doc = {"id": key, "uz": spec["uz"], "source": f"{atlas.version} (DBCLS), CC BY 4.0",
           "bbox_min": np.round(lo, 5).tolist(), "bbox_max": np.round(hi, 5).tolist(),
           "groups": groups, "labels": labels}
    with open(os.path.join(out_dir, "scene.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    return doc


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    atlas = Atlas(argv[0])
    for key in argv[1:] or list(SCENES):
        doc = build_scene(atlas, key)
        sizes = ", ".join(f"{g}: {v['bytes'] / 1e6:.1f} MB" for g, v in doc["groups"].items())
        print(f"{key}: {sizes}; yorliqlar: {len(doc['labels'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
