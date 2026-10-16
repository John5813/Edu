"""Oddiy GLB (glTF 2.0 binar) yozuvchi va o'quvchi — tashqi kutubxonasiz, faqat numpy.

PowerPoint 3D modelni GLB dan oladi. Bitta faylda bir nechta "primitiv" bo'ladi: har biri o'z
materiali (suyak, tish...) bilan. `anchors` — qutining ikki qarama-qarshi burchagidagi ikkita juda kichik
(piksel ulushidan ham kichik, qora) uchburchak: ular modelning chegara qutisini (bounding box) belgilaydi.
Nol yuzali uchburchak yetmaydi — PowerPoint uni import paytida tashlab yuboradi va har modelni o'z
geometriyasi bo'yicha markazlaydi (yurakdan uzilib qolgan tomirlar shundan edi). Bir sahnadagi hamma qism (bosh suyagi tepasi, jag')
bir xil qutiga ega bo'lsa, PowerPoint ularni bir xil masshtab va markaz bilan chizadi — bir xil
ramkaga qo'yilganda qismlar bir-biriga aniq yopishadi.
"""
import json
import struct
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_FLOAT, _U8, _U16, _U32 = 5126, 5121, 5123, 5125
_ARRAY, _ELEMENTS = 34962, 34963
ANCHOR_SIZE = 4e-4        # langar uchburchak tomoni — model o'lchamining ulushi (ekranda < 1 piksel)


class Primitive:
    def __init__(self, positions: np.ndarray, normals: np.ndarray, indices: np.ndarray,
                 color: Sequence[float], roughness: float = 0.62, name: str = "",
                 colors: Optional[np.ndarray] = None):
        """colors — ixtiyoriy N×4 uint8 nuqta rangi (soya): material rangiga ko'paytiriladi."""
        self.colors = None if colors is None else np.ascontiguousarray(colors, dtype=np.uint8).reshape(-1, 4)
        self.positions = np.ascontiguousarray(positions, dtype=np.float32).reshape(-1, 3)
        self.normals = np.ascontiguousarray(normals, dtype=np.float32).reshape(-1, 3)
        self.indices = np.ascontiguousarray(indices, dtype=np.uint32).reshape(-1)
        self.color = tuple(float(c) for c in color)
        self.roughness = roughness
        self.name = name


def _pad(data: bytes, fill: bytes = b"\0") -> bytes:
    return data + fill * (-len(data) % 4)


def write_glb(primitives: List[Primitive], *, anchors: Optional[Tuple[Sequence[float], Sequence[float]]] = None,
              name: str = "model") -> bytes:
    """Primitivlardan GLB baytlarini yasaydi. anchors=(min, max) — modelning majburiy chegara qutisi."""
    prims = list(primitives)
    if anchors is not None:
        lo, hi = (np.asarray(a, dtype=np.float32) for a in anchors)
        tiny = np.float32(ANCHOR_SIZE * max(float((hi - lo).max()), 1e-6))
        ex, ey = np.array([tiny, 0, 0], np.float32), np.array([0, tiny, 0], np.float32)
        corners = np.array([lo, lo + ex, lo + ey, hi, hi - ey, hi - ex], dtype=np.float32)  # quti ichida
        first = prims[0]
        base = len(first.positions)
        prims[0] = Primitive(
            np.vstack([first.positions, corners]),
            np.vstack([first.normals, [[0, 0, 1]] * 6]),
            np.concatenate([first.indices, base + np.arange(6)]),
            first.color, first.roughness, first.name,
            None if first.colors is None else np.vstack([first.colors, [[0, 0, 0, 255]] * 6]))

    blob = bytearray()
    views, accessors, materials, gltf_prims = [], [], [], []

    def add(data: bytes, target: int) -> int:
        offset = len(blob)                         # har bo'lak 4 baytga tekislangan
        blob.extend(_pad(data))
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        return len(views) - 1

    for prim in prims:
        pos, nrm = prim.positions, prim.normals
        lens = np.linalg.norm(nrm, axis=1, keepdims=True)
        nrm = np.where(lens > 1e-8, nrm / np.maximum(lens, 1e-8), [0.0, 1.0, 0.0]).astype(np.float32)
        v_pos = add(pos.tobytes(), _ARRAY)
        accessors.append({"bufferView": v_pos, "componentType": _FLOAT, "count": len(pos), "type": "VEC3",
                          "min": [float(x) for x in pos.min(axis=0)], "max": [float(x) for x in pos.max(axis=0)]})
        a_pos = len(accessors) - 1
        v_nrm = add(nrm.tobytes(), _ARRAY)
        accessors.append({"bufferView": v_nrm, "componentType": _FLOAT, "count": len(nrm), "type": "VEC3"})
        a_nrm = len(accessors) - 1
        attributes = {"POSITION": a_pos, "NORMAL": a_nrm}
        if prim.colors is not None and len(prim.colors) == len(pos):
            v_col = add(prim.colors.tobytes(), _ARRAY)
            accessors.append({"bufferView": v_col, "componentType": _U8, "normalized": True, "count": len(pos),
                              "type": "VEC4"})
            attributes["COLOR_0"] = len(accessors) - 1
        small = len(pos) < 65535
        idx = prim.indices.astype(np.uint16 if small else np.uint32)
        v_idx = add(idx.tobytes(), _ELEMENTS)
        accessors.append({"bufferView": v_idx, "componentType": _U16 if small else _U32, "count": len(idx),
                          "type": "SCALAR"})
        a_idx = len(accessors) - 1
        materials.append({"name": prim.name or f"material{len(materials)}",
                          "pbrMetallicRoughness": {"baseColorFactor": [*prim.color[:3], 1.0],
                                                   "metallicFactor": 0.0, "roughnessFactor": prim.roughness}})
        gltf_prims.append({"attributes": attributes, "indices": a_idx,
                           "material": len(materials) - 1, "mode": 4})

    doc = {
        "asset": {"version": "2.0", "generator": "Edu med3d"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{"name": name, "primitives": gltf_prims}],
        "materials": materials,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    js = _pad(json.dumps(doc, separators=(",", ":")).encode("utf-8"), b" ")
    bin_chunk = _pad(bytes(blob))
    total = 12 + 8 + len(js) + 8 + len(bin_chunk)
    return (struct.pack("<III", 0x46546C67, 2, total)
            + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk)


def read_glb(data: bytes) -> Tuple[Dict, bytes]:
    """GLB → (JSON hujjat, BIN bo'lak). Tekshiruv va chegara qutisini o'qish uchun."""
    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2 or total != len(data):
        raise ValueError("GLB emas yoki buzilgan")
    offset, doc, binary = 12, None, b""
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8: offset + 8 + length]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif kind == 0x004E4942:
            binary = chunk
        offset += 8 + length
    if doc is None:
        raise ValueError("GLB ichida JSON yo'q")
    return doc, binary


def bounds(data: bytes) -> Tuple[np.ndarray, np.ndarray]:
    """GLB chegara qutisi (POSITION accessor min/max bo'yicha — PowerPoint ham shunday hisoblaydi)."""
    doc, _ = read_glb(data)
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for mesh in doc.get("meshes", []):
        for prim in mesh.get("primitives", []):
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            lo = np.minimum(lo, acc["min"])
            hi = np.maximum(hi, acc["max"])
    return lo, hi
