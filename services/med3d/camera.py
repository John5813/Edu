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
from typing import List, Optional, Sequence, Tuple

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

    def anchor(self, points, rot, occluders=None, radius: float = 0.01) -> Optional[Tuple[float, float]]:
        """Qismning kameraga qaragan va KO'RINIB TURGAN yuzasidagi nuqta (yorliq chizig'i uchi).

        occluders — slayddagi boshqa organlarning nuqtalari: ular ortida qolgan nuqta tanlanmaydi. Juft organda —
        ko'proq ko'rinib turgan tomoni. Nuqta ko'rinadigan joyning ichkarisidan olinadi (chetidan emas: chekka
        nuqta boshqa organ chegarasida bo'lib, ko'pincha aslida uning ortida qoladi). Organ deyarli butunlay
        yopilgan bo'lsa — None (yorliq qo'yilmaydi: kurak suyagi yorlig'i deltasimon mushak ustiga tushmasin).
        radius — eski chaqiruvlar uchun qoldirilgan.
        """
        best = None
        for part in sides(points):
            uv, z = self.project(part, rot)
            if occluders is not None and len(occluders):
                seen = self.visible_mask(part, rot, occluders)
            else:
                seen = np.ones(len(uv), dtype=bool)
            if best is None or seen.sum() > best[2].sum():
                best = (uv, z, seen)
        uv, z, seen = best
        if seen.sum() < max(3, int(0.04 * len(uv))):
            return None
        uv, z = uv[seen], z[seen]
        front = z >= np.quantile(z, 0.5) if len(z) >= 8 else np.ones(len(z), dtype=bool)
        cand = uv[front]
        # ko'rinadigan nuqtalar zich joylashgan joy — ko'rinadigan yuzaning ichkarisi
        reach = 0.18 * float(max(np.ptp(uv[:, 0]), np.ptp(uv[:, 1]), 1e-6))
        dist = np.sqrt(((cand[:, None, :] - uv[None, :, :]) ** 2).sum(axis=2))
        crowd = (dist < reach).sum(axis=1).astype(float)
        mid = uv.mean(axis=0)
        score = crowd - 0.5 * np.sqrt(((cand - mid) ** 2).sum(axis=1)) / reach
        pick = cand[int(np.argmax(score))]
        return float(pick[0]), float(pick[1])


class IdBuffer:
    """Slaydning "qaysi pikselda qaysi organ ko'rinadi" xaritasi: organ yuzasidan zich nuqtalar proyeksiya qilinadi
    va har pikselda kameraga eng yaqini qoladi (z-bufer). Siyrak namunalar bo'yicha taxmin emas — yorliq nuqtasi
    organning haqiqatan ko'rinib turgan joyiga tushadi, boshqa organ ostiga emas.

    layers — [(kalit, slayddagi x, y dyuymda, chuqurlik)]: kalit odatda (guruh, organ).
    """

    def __init__(self, layers, width: float, height: float, dpi: float = 40.0):
        self.dpi = dpi
        self.w, self.h = int(width * dpi) + 1, int(height * dpi) + 1
        self.keys = [key for key, *_ in layers]
        xs, ys, zs, ids = [], [], [], []
        for k, (_, x, y, z) in enumerate(layers):
            xs.append(np.asarray(x, float))
            ys.append(np.asarray(y, float))
            zs.append(np.asarray(z, float))
            ids.append(np.full(len(xs[-1]), k, dtype=np.int32))
        self.ids = np.full((self.h, self.w), -1, dtype=np.int32)
        self.depth = np.full((self.h, self.w), -np.inf)
        if not xs:
            return
        x, y, z, idx = np.concatenate(xs), np.concatenate(ys), np.concatenate(zs), np.concatenate(ids)
        col, row = np.floor(x * dpi).astype(int), np.floor(y * dpi).astype(int)
        ok = (col >= 0) & (col < self.w) & (row >= 0) & (row < self.h)
        col, row, z, idx = col[ok], row[ok], z[ok], idx[ok]
        pix = row * self.w + col
        order = np.lexsort((-z, pix))                  # har piksel ichida eng yaqini birinchi
        pix, z, idx = pix[order], z[order], idx[order]
        first = np.r_[True, pix[1:] != pix[:-1]]
        flat_ids, flat_depth = self.ids.reshape(-1), self.depth.reshape(-1)
        flat_ids[pix[first]] = idx[first]
        flat_depth[pix[first]] = z[first]
        self._close_holes()

    def _close_holes(self) -> None:
        """Nuqtalar orasidagi bo'sh piksel (8 qo'shnidan kamida 5 tasi band) eng yaqin qo'shni bilan to'ldiriladi."""
        for _ in range(2):
            pad_d = np.pad(self.depth, 1, constant_values=-np.inf)
            pad_i = np.pad(self.ids, 1, constant_values=-1)
            near_d = np.stack([pad_d[1 + dy:self.h + 1 + dy, 1 + dx:self.w + 1 + dx]
                               for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])
            near_i = np.stack([pad_i[1 + dy:self.h + 1 + dy, 1 + dx:self.w + 1 + dx]
                               for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])
            fill = (self.ids < 0) & (np.isfinite(near_d).sum(axis=0) >= 5)
            if not fill.any():
                return
            best = np.argmax(near_d, axis=0)
            rows, cols = np.nonzero(fill)
            self.ids[rows, cols] = near_i[best[rows, cols], rows, cols]
            self.depth[rows, cols] = near_d[best[rows, cols], rows, cols]

    @staticmethod
    def _erode(mask: np.ndarray) -> np.ndarray:
        pad = np.pad(mask, 1, constant_values=False)
        out = mask.copy()
        h, w = mask.shape
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                out &= pad[1 + dy:h + 1 + dy, 1 + dx:w + 1 + dx]
        return out

    def visible_pixels(self, key) -> int:
        if key not in self.keys:
            return 0
        return int((self.ids == self.keys.index(key)).sum())

    def anchor(self, key, min_pixels: int = 6) -> Optional[Tuple[float, float]]:
        """Organning ko'rinib turgan qismining eng "ichkari" nuqtasi (chetidan eng uzoq piksel) — slayd dyuymida.
        Organ deyarli ko'rinmasa — None."""
        if key not in self.keys:
            return None
        mask = self.ids == self.keys.index(key)
        if mask.sum() < min_pixels:
            return None
        while True:                                     # eroziya: eng qalin joy qoladi
            inner = self._erode(mask)
            if not inner.any():
                break
            mask = inner
        rows, cols = np.nonzero(mask)
        cy, cx = rows.mean(), cols.mean()
        k = int(np.argmin((rows - cy) ** 2 + (cols - cx) ** 2))
        return (cols[k] + 0.5) / self.dpi, (rows[k] + 0.5) / self.dpi

    def near_model(self, x: float, y: float, gap: float) -> bool:
        """(x, y) dyuym nuqtasidan `gap` dyuym radiusda modelning biror pikseli bormi."""
        r = max(1, int(round(gap * self.dpi)))
        col, row = int(x * self.dpi), int(y * self.dpi)
        r0, r1, c0, c1 = max(0, row - r), min(self.h, row + r + 1), max(0, col - r), min(self.w, col + r + 1)
        if r0 >= r1 or c0 >= c1:
            return False
        return bool((self.ids[r0:r1, c0:c1] >= 0).any())
