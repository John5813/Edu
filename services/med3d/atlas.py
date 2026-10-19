"""human-atlas (BodyParts3D 4.0) ma'lumotini o'qish: `atlas.json` katalogi va `body-N.bin` bo'laklari.

Faqat bir martalik tayyorlash skripti (`tools/med3d_tayyorla.py`) ishlatadi — bot ishlayotganda
atlas kerak emas. Har qism uchun bin ichida: Float32 pozitsiyalar (metr), Int16 normallar
(normallangan) va Uint32 indekslar. O'qlar: Y — yuqoriga, +Z — oldinga (yuz), +X — bemorning chapi.
"""
import json
import os
from typing import Dict, List, Tuple

import numpy as np

from . import MICRO_DIR, ZA_DIR


class Atlas:
    def __init__(self, models_dir: str, catalog: str = "atlas.json"):
        """catalog: "atlas.json" — erkak (BodyParts3D), "atlas-female.json" — ayol (HRA, slorksmo/Human-Atlas)."""
        self.dir = models_dir
        with open(os.path.join(models_dir, catalog), encoding="utf-8") as fh:
            self.meta = json.load(fh)
        if catalog == "atlas.json" and os.path.isdir(ZA_DIR):
            for name in sorted(os.listdir(ZA_DIR)):
                if name.startswith("atlas-za") and name.endswith(".json"):
                    self._merge(os.path.join(ZA_DIR, name))
        self._merge(os.path.join(MICRO_DIR, "atlas-mikro.json"))
        # BodyParts3D bitta a'zoni bir nechta bo'lakka bo'ladi (masalan "Proximal part of ileum" — o'nlab
        # bo'lak): nom bo'yicha hammasi olinadi. Aniq bitta bo'lak kerak bo'lsa — uning id si ("FJ2823").
        self.by_name: Dict[str, List[dict]] = {}
        self.by_id: Dict[str, dict] = {}
        for part in self.meta["parts"]:
            self.by_name.setdefault(part["name"], []).append(part)
            self.by_id[part["id"]] = part
        self._chunks: Dict[int, bytes] = {}

    def _merge(self, path: str) -> None:
        """Qo'shimcha katalog (masalan Z-Anatomy bosh mushaklari) — o'z bo'laklari bilan, shu atlasga qo'shiladi."""
        if not os.path.isfile(path):
            return
        with open(path, encoding="utf-8") as fh:
            extra = json.load(fh)
        base = len(self.meta["chunks"])
        self.meta["chunks"] = self.meta["chunks"] + [dict(c, dir=os.path.dirname(path)) for c in extra["chunks"]]
        self.meta["parts"] = self.meta["parts"] + [dict(p, chunk=p["chunk"] + base) for p in extra["parts"]]

    @property
    def version(self) -> str:
        return self.meta.get("version", "")

    def _chunk(self, index: int) -> bytes:
        if index not in self._chunks:
            chunk = self.meta["chunks"][index]
            with open(os.path.join(chunk.get("dir", self.dir), os.path.basename(chunk["url"])), "rb") as fh:
                self._chunks[index] = fh.read()
        return self._chunks[index]

    def parts(self, name: str) -> List[dict]:
        if name in self.by_id:
            return [self.by_id[name]]
        if name in self.by_name:
            return self.by_name[name]
        raise KeyError(f"Atlasda bunday qism yo'q: {name!r}")

    def _one(self, p: dict) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        buf = self._chunk(p["chunk"])
        n = p["vertexCount"]
        pos = np.frombuffer(buf, dtype="<f4", count=n * 3, offset=p["positions"]).reshape(n, 3)
        nrm = np.frombuffer(buf, dtype="<i2", count=n * 3, offset=p["normals"]).reshape(n, 3)
        idx = np.frombuffer(buf, dtype="<u4", count=p["indexCount"], offset=p["indices"])
        return pos.astype(np.float32), (nrm.astype(np.float32) / 32767.0), idx.astype(np.uint32)

    def mesh(self, name: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Nom (yoki id) bo'yicha hamma bo'laklar bitta mesh: (pozitsiyalar N×3, normallar N×3, indekslar M)."""
        pos, nrm, idx, base = [], [], [], 0
        for p in self.parts(name):
            a, b, c = self._one(p)
            pos.append(a)
            nrm.append(b)
            idx.append(c + base)
            base += len(a)
        return np.vstack(pos), np.vstack(nrm), np.concatenate(idx)
