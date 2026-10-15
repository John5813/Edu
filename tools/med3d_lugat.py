"""Organlar lug'atini yasaydi: `services/med3d/lugat.py` qoidalari ikkala atlasga qo'llanadi.

Natija `assets/med3d/lugat.json`: har tana va organ uchun atlas qism id lari, uchburchaklar soni,
chegara qutisi va yorliq/kamera uchun nuqta namunalari. Bot shu fayl bilan ishlaydi; 3D modelni esa
so'rov paytida atlasdan yig'adi.

    python tools/med3d_lugat.py            # lug'atni yasash (atlas kerak bo'lsa yuklanadi)
    python tools/med3d_lugat.py --yukla    # faqat atlasni serverga yuklab qo'yish
    python tools/med3d_lugat.py --hisobot  # qaysi organ qaysi tanada nechta qismdan iborat
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from services.med3d import ASSETS_DIR, manba        # noqa: E402
from services.med3d.lugat import BY_ID, ORGANS      # noqa: E402

SAMPLES = 300
OUT = os.path.join(ASSETS_DIR, "lugat.json")


def _matcher(rule: str):
    if rule.startswith("id:"):
        wanted = rule[3:]
        return lambda part: part["id"] == wanted
    systems = None
    pattern = rule
    head, sep, tail = rule.partition(":")
    if sep and re.fullmatch(r"[a-z|\-]+", head):
        systems, pattern = set(head.split("|")), tail
    regex = re.compile(pattern, re.I)
    return lambda part: (systems is None or part["system"] in systems) and bool(regex.search(part["name"]))


def resolve(parts, key: str, body_key: str, memo: dict) -> list:
    """Organ → qism id lari (union bo'lsa — tarkibidagi organlarniki)."""
    if key in memo:
        return memo[key]
    organ = BY_ID[key]
    if organ.get("union"):
        ids = []
        for child in organ["union"]:
            ids += [i for i in resolve(parts, child, body_key, memo) if i not in ids]
    else:
        tests = [_matcher(r) for r in organ.get(body_key, [])]
        ids = [p["id"] for p in parts if any(t(p) for t in tests)]
    memo[key] = ids
    return ids


def build(directory: str = manba.ATLAS_DIR) -> dict:
    out = {"version": 1, "sha": manba.REPO_SHA, "bodies": {}}
    for body, body_key in (("male", "m"), ("female", "f")):
        atlas = manba.atlas(body, directory)
        parts = atlas.meta["parts"]
        by_id = {p["id"]: p for p in parts}
        memo: dict = {}
        organs = {}
        for seed, organ in enumerate(ORGANS):
            ids = resolve(parts, organ["id"], body_key, memo)
            if not ids:
                continue
            points = np.vstack([atlas._one(by_id[i])[0] for i in ids])
            lo, hi = points.min(axis=0), points.max(axis=0)
            if len(points) > SAMPLES:
                points = points[np.random.default_rng(seed).choice(len(points), SAMPLES, replace=False)]
            organs[organ["id"]] = {
                "parts": ids,
                "tris": int(sum(by_id[i]["indexCount"] for i in ids) // 3),
                "min": np.round(lo, 4).tolist(), "max": np.round(hi, 4).tolist(),
                "samples": np.round(points, 4).tolist(),
            }
        out["bodies"][body] = organs
    return out


def report(doc: dict) -> None:
    for organ in ORGANS:
        row = []
        for body in ("male", "female"):
            info = doc["bodies"][body].get(organ["id"])
            row.append(f"{len(info['parts']):4d} qism {info['tris']:7d} ▲" if info else "      —        ")
        print(f"{organ['id']:22s} {organ['uz'][:34]:34s} erkak: {row[0]}   ayol: {row[1]}")


def main(argv) -> int:
    if "--yukla" in argv:
        for body in ("male", "female"):
            print(body, "→", manba.ensure(body))
        return 0
    doc = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{OUT}: {os.path.getsize(OUT) / 1e6:.1f} MB")
    if "--hisobot" in argv or True:
        report(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
