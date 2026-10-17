"""PowerPoint 3D kamerasining taxminiy nusxasi: model nuqtasi slaydda qayerga tushishini hisoblaydi.

Kerak bo'ladi: (1) qism slaydning kerakli joyida kerakli kattalikda chiqishi uchun ramka o'lchami va
joyini topish, (2) yorliq chizig'i suyakning aynan ustiga tushishi uchun.

PowerPoint (OfficeCLI tadqiqoti bo'yicha) modelni chegara qutisi markaziga ko'chiradi, eng katta
o'lchamini 1 ga keltiradi, kamerani +Z tomonga 45° ko'rish burchagi bilan shunday qo'yadiki, qutini
o'rab turgan shar ramkaga to'liq sig'adi. Aylanish — o'ng qo'l qoidasi, X → Y → Z tartibida
(three.js "XYZ"): rotx musbat — model yuqoridan ko'rinadi, roty musbat — yuzi o'ngga buriladi.
Bu taxmin PowerPoint'da tekshirilishi kerak; noto'g'ri chiqsa faqat shu fayldagi `SIGN` o'zgaradi.
"""
import math
from typing import List, Sequence, Tuple

import numpy as np

FOV_DEG = 45.0
SIGN = (1.0, 1.0, 1.0)            # PowerPoint aylanish yo'nalishi boshqacha bo'lsa — shu yerda -1


def rotation(rot: Sequence[float]) -> np.ndarray:
    ax, ay, az = (math.radians(a * s) for a, s in zip(rot, SIGN))
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rx @ ry @ rz


def sides(points) -> List[np.ndarray]:
    """Juft organ (o'ng va chap chaynov mushagi) — ikki bo'lak, toq organ — bitta. Juft organning bir tomoni
    ko'rinsa yetarli: yon tomondan qaraganda narigi tomoni bosh suyagi ortida qolishi tabiiy."""
    pts = np.asarray(points, float)
    if len(pts) < 8:
        return [pts]
    x = pts[:, 0]
    mid = float(x.max() + x.min()) / 2
    left, right = pts[x < mid - 0.004], pts[x > mid + 0.004]
    width = float(x.max() - x.min())
    # ikki tomon orasida bo'shliq bor (o'rta chiziqda nuqta deyarli yo'q) — juft organ
    centre = np.abs(x - mid) < width * 0.12
    if min(len(left), len(right)) >= len(pts) * 0.3 and centre.mean() < 0.04:
        return [left, right]
    return [pts]


class Camera:
    """Bitta sahna (umumiy chegara qutisi) uchun proyeksiya."""

    def __init__(self, bbox_min: Sequence[float], bbox_max: Sequence[float]):
        lo, hi = np.asarray(bbox_min, float), np.asarray(bbox_max, float)
        self.center = (lo + hi) / 2
        half = (hi - lo) / 2
        self.unit = 2 * float(half.max())                       # eng katta o'lcham → 1
        radius = float(np.linalg.norm(half)) / self.unit
        theta = math.radians(FOV_DEG / 2)
        self.distance = radius / math.sin(theta)
        self.tan = math.tan(theta)

    def project(self, points, rot: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
        """Nuqtalar → (N×2 ramka ulushida: markazdan, o'ngga va pastga musbat; N chuqurlik — kameraga yaqin katta)."""
        p = (np.asarray(points, float).reshape(-1, 3) - self.center) / self.unit
        p = p @ rotation(rot).T
        depth = self.distance - p[:, 2]
        uv = np.stack([p[:, 0], -p[:, 1]], axis=1) / depth[:, None] / self.tan * 0.5
        return uv, p[:, 2]

    def extent(self, points, rot) -> Tuple[float, float, float, float]:
        uv, _ = self.project(points, rot)
        (u0, v0), (u1, v1) = uv.min(axis=0), uv.max(axis=0)
        return float(u0), float(v0), float(u1), float(v1)

    def visible_mask(self, points, rot, occluders, grid: int = 0) -> np.ndarray:
        """Har nuqta boshqa organlar bilan to'silmaganmi (True — ko'rinadi). O'zini o'zi to'sishi hisobga olinmaydi.

        Namunaviy nuqtalar siyrak bo'lishi mumkin: to'suvchilar kichik chuqurlik xaritasiga (raster) chiziladi,
        nuqtalar orasidagi bo'shliqlar yopiladi, keyin har nuqta xarita bilan solishtiriladi.
        """
        uv, z = self.project(points, rot)
        if occluders is None or not len(occluders) or not len(uv):
            return np.ones(len(uv), dtype=bool)
        ouv, oz = self.project(occluders, rot)
        lo = np.minimum(ouv.min(axis=0), uv.min(axis=0))
        hi = np.maximum(ouv.max(axis=0), uv.max(axis=0))
        grid = grid or int(np.clip(np.sqrt(len(occluders)) * 1.1, 16, 48))   # katak — nuqtalar zichligiga qarab
        cell = float((hi - lo).max()) / grid or 1.0
        dims = np.ceil((hi - lo) / cell).astype(int) + 3
        depth = np.full(dims, -np.inf)
        ij = np.floor((ouv - lo) / cell).astype(int) + 1
        np.maximum.at(depth, (ij[:, 0], ij[:, 1]), oz)
        filled = np.isfinite(depth)
        for _ in range(2):          # bo'shliqni yopish: 8 qo'shnidan kamida 5 tasi band bo'lsa — katak ham band
            pad = np.pad(depth, 1, constant_values=-np.inf)
            near = np.stack([pad[1 + dx:dims[0] + 1 + dx, 1 + dy:dims[1] + 1 + dy]
                             for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy])
            count = np.isfinite(near).sum(axis=0)
            fill = ~filled & (count >= 5)
            depth[fill] = near.max(axis=0)[fill]
            filled = np.isfinite(depth)
        pij = np.floor((uv - lo) / cell).astype(int) + 1
        return ~(depth[pij[:, 0], pij[:, 1]] > z + 1e-3)

    def visible_share(self, points, rot, occluders, radius: float = 0.01, grid: int = 0) -> float:
        """Organ siluetining qancha ulushi boshqa organlar ortida qolmagan (0..1)."""
        if not len(points):
            return 1.0
        return float(self.visible_mask(points, rot, occluders, grid).mean())

    def anchor(self, points, rot, occluders=None, radius: float = 0.01) -> Tuple[float, float]:
        """Qismning kameraga qaragan yuzasidagi, markaziga eng yaqin nuqta (yorliq chizig'i uchi).

        occluders — slayddagi boshqa organlarning nuqtalari: ular ortida qolgan (yopilgan) nuqta tanlanmaydi
        (`visible_mask`). radius — eski chaqiruvlar uchun qoldirilgan.
        """
        parts = sides(points)
        if len(parts) == 2:
            # Juft organ: chiziq o'rta chiziqqa (ikki tomon orasidagi bo'shliqqa) emas, kameraga yaqin va ko'proq
            # ko'rinib turgan tomoniga tushadi.
            def rank(part):
                share = self.visible_share(part, rot, occluders) if occluders is not None and len(occluders) else 1.0
                return share + 0.5 * float(self.project(part, rot)[1].mean()) / max(self.distance, 1e-6)
            points = max(parts, key=rank)
        uv, z = self.project(points, rot)
        if occluders is not None and len(occluders):
            seen = self.visible_mask(points, rot, occluders)
            if seen.sum() >= 3:                 # faqat ko'rinib turgan joyga (boshqa organ ortiga emas)
                uv, z = uv[seen], z[seen]
        front = uv[z >= np.quantile(z, 0.7)]
        mid = front.mean(axis=0)
        best = front[np.argmin(((front - mid) ** 2).sum(axis=1))]
        return float(best[0]), float(best[1])
