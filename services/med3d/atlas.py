"""human-atlas (BodyParts3D 4.0) ma'lumotini o'qish: `atlas.json` katalogi va `body-N.bin` bo'laklari.

Faqat bir martalik tayyorlash skripti (`tools/med3d_tayyorla.py`) ishlatadi — bot ishlayotganda
atlas kerak emas. Har qism uchun bin ichida: Float32 pozitsiyalar (metr), Int16 normallar
(normallangan) va Uint32 indekslar. O'qlar: Y — yuqoriga, +Z — oldinga (yuz), +X — bemorning chapi.
"""
import json
import os
from typing import Dict, List, Tuple

import numpy as np


class Atlas:
    def __init__(self, models_dir: str):
        self.dir = models_dir
        with open(os.path.join(models_dir, "atlas.json"), encoding="utf-8") as fh:
            self.meta = json.load(fh)
        # BodyParts3D bitta a'zoni bir nechta bo'lakka bo'ladi (masalan "Proximal part of ileum" — o'nlab
        # bo'lak): nom bo'yicha hammasi olinadi. Aniq bitta bo'lak kerak bo'lsa — uning id si ("FJ2823").
        self.by_name: Dict[str, List[dict]] = {}
        self.by_id: Dict[str, dict] = {}
        for part in self.meta["parts"]:
            self.by_name.setdefault(part["name"], []).append(part)
            self.by_id[part["id"]] = part
        self._chunks: Dict[int, bytes] = {}

    @property
    def version(self) -> str:
        return self.meta.get("version", "")

    def _chunk(self, index: int) -> bytes:
        if index not in self._chunks:
            url = self.meta["chunks"][index]["url"]
            with open(os.path.join(self.dir, os.path.basename(url)), "rb") as fh:
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
