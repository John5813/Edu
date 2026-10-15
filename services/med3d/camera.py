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
from typing import Sequence, Tuple

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

    def anchor(self, points, rot, occluders=None, radius: float = 0.01) -> Tuple[float, float]:
        """Qismning kameraga qaragan yuzasidagi, markaziga eng yaqin nuqta (yorliq chizig'i uchi).

        occluders — slayddagi boshqa organlarning nuqtalari: ular oldida turgan (yopib qo'yilgan) nuqta
        tanlanmaydi. radius — ramka ulushida, shu masofadagi oldinroq nuqta "yopadi" deb hisoblanadi.
        """
        uv, z = self.project(points, rot)
        keep = z >= np.quantile(z, 0.7)
        front, fz = uv[keep], z[keep]
        if occluders is not None and len(occluders):
            ouv, oz = self.project(occluders, rot)
            d2 = ((front[:, None, :] - ouv[None, :, :]) ** 2).sum(axis=2)
            hidden = ((d2 < radius * radius) & (oz[None, :] > fz[:, None] + 1e-3)).any(axis=1)
            if (~hidden).any():
                front = front[~hidden]
        mid = front.mean(axis=0)
        best = front[np.argmin(((front - mid) ** 2).sum(axis=1))]
        return float(best[0]), float(best[1])
