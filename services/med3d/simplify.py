"""Katta modelni soddalashtirish (vertex clustering): yaqin nuqtalar bitta nuqtaga birlashtiriladi.

Masalan, butun mushaklar ~600 ming uchburchak — slaydga qo'yilsa fayl juda katta bo'ladi va PowerPoint
sekin ishlaydi. Fazo kichik kataklarga bo'linadi, har katakdagi nuqtalar bittaga aylanadi; katak o'lchami
uchburchaklar soni chegaraga tushguncha tanlanadi. Tez (numpy) va tashqi kutubxona talab qilmaydi.
"""
from typing import Tuple

import numpy as np


def _cluster(pos: np.ndarray, nrm: np.ndarray, idx: np.ndarray, cell: float):
    lo = pos.min(axis=0)
    grid = np.floor((pos - lo) / cell).astype(np.int64)
    span = grid.max(axis=0) + 1
    keys = (grid[:, 0] * span[1] + grid[:, 1]) * span[2] + grid[:, 2]      # katak → bitta son (tez)
    _, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    n = len(counts)
    new_pos = np.stack([np.bincount(inverse, weights=pos[:, k], minlength=n) for k in range(3)], axis=1)
    new_nrm = np.stack([np.bincount(inverse, weights=nrm[:, k], minlength=n) for k in range(3)], axis=1)
    new_pos /= counts[:, None]
    lens = np.linalg.norm(new_nrm, axis=1, keepdims=True)
    new_nrm = np.where(lens > 1e-9, new_nrm / np.maximum(lens, 1e-9), [0.0, 1.0, 0.0])
    tri = inverse[idx.reshape(-1, 3)]
    keep = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
    tri = tri[keep]
    if len(tri):                                   # bir xil uchburchaklar (qarama-qarshi tomonlari ham) bittaga
        s = np.sort(tri, axis=1)
        code = (s[:, 0] * n + s[:, 1]) * n + s[:, 2]
        tri = tri[np.sort(np.unique(code, return_index=True)[1])]
    used = np.unique(tri)
    remap = np.full(n, -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    return (new_pos[used].astype(np.float32), new_nrm[used].astype(np.float32),
            remap[tri].reshape(-1).astype(np.uint32))


def vertex_normals(pos: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Uchburchak yuzasiga qarab o'rtachalangan nuqta normallari."""
    tri = idx.reshape(-1, 3)
    face = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
    out = np.zeros_like(pos, dtype=np.float64)
    for k in range(3):
        for axis in range(3):
            out[:, axis] += np.bincount(tri[:, k], weights=face[:, axis], minlength=len(pos))
    lens = np.linalg.norm(out, axis=1, keepdims=True)
    return np.where(lens > 1e-12, out / np.maximum(lens, 1e-12), [0.0, 1.0, 0.0]).astype(np.float32)


def _quadric(pos: np.ndarray, idx: np.ndarray, target: int):
    """Sifatli soddalashtirish (quadric edge collapse, `fast_simplification`): shakl, egat va burmalar saqlanadi.

    Vertex clustering yaqin nuqtalarni bittaga yopishtiradi — miya kabi burmali yuzada teshik va dog'lar
    paydo bo'ladi. Kutubxona o'rnatilmagan bo'lsa — None (oddiy usul ishlaydi).
    """
    try:
        import fast_simplification
    except ImportError:
        return None
    faces = idx.reshape(-1, 3).astype(np.int32)
    p, f = fast_simplification.simplify(pos.astype(np.float32), faces, target_reduction=1 - target / len(faces))
    p = p.astype(np.float32)
    i = f.reshape(-1).astype(np.uint32)
    return p, vertex_normals(p, i), i


def simplify(pos: np.ndarray, nrm: np.ndarray, idx: np.ndarray, target: int
             ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Uchburchaklar soni `target` dan oshmaydigan qilib soddalashtiradi (kerak bo'lmasa — o'zgarishsiz)."""
    if len(idx) // 3 <= target or len(pos) < 4:
        return pos, nrm, idx
    result = _quadric(pos, idx, target)
    if result is not None and len(result[2]):
        return result
    size = float((pos.max(axis=0) - pos.min(axis=0)).max()) or 1.0
    low, high = size / 4000, size / 20             # katak o'lchami: kichik — sifatli, katta — soddaroq
    best = None
    for _ in range(14):
        cell = (low * high) ** 0.5
        result = _cluster(pos, nrm, idx, cell)
        if len(result[2]) // 3 > target:
            low = cell
        else:
            best, high = result, cell
        if best is not None and len(best[2]) // 3 > target * 0.85:
            break
    return best if best is not None else _cluster(pos, nrm, idx, high)
