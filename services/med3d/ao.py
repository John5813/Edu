"""Soya (ambient occlusion): yopiq joylar — egatlar, kanallar, chuqurliklar — qorong'iroq bo'ladi.

PowerPoint 3D modelni oddiy chiroqlar bilan yoritadi va soya tashlamaydi: miya egatining ichi ham burma
ustidek yorug' ko'rinadi, model "yassi" bo'lib qoladi. Shuning uchun har nuqta uchun atrofdagi yuzalar unga
qancha yorug'lik o'tkazmasligi oldindan hisoblanadi va natija modelning nuqta rangiga (glTF COLOR_0)
yoziladi — rang material rangiga ko'paytiriladi.

Hisob: model fazoviy panjaraga (voksel) aylantiriladi; har nuqtadan normal tomonidagi yarim sfera
bo'ylab nurlar chiqariladi; nur boshqa yuzaga urilsa — shu tomondan yorug'lik to'silgan. Faqat numpy.
"""
from typing import Optional, Tuple

import numpy as np

GRID = 112            # panjara aniqligi (eng uzun tomon bo'yicha)
RAYS = 24             # har nuqtadan nurlar soni
STEPS = 10            # nur bo'ylab qadamlar
REACH = 0.12          # nur uzunligi — model o'lchamining ulushi
STRENGTH = 0.95       # to'liq yopiq joy qanchalik qorong'i (0 — soyasiz, 1 — qop-qora)


def _directions(n: int) -> np.ndarray:
    """Yarim sfera bo'ylab teng taqsimlangan yo'nalishlar (Fibonachchi, z ≥ 0, kosinusga yaqin)."""
    i = np.arange(n) + 0.5
    z = np.sqrt(1 - i / n)                       # kosinus bo'yicha: normalga yaqin nurlar ko'proq
    r = np.sqrt(1 - z * z)
    phi = i * np.pi * (3 - np.sqrt(5))
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


def _basis(normals: np.ndarray):
    """Har normal uchun (t, b, n) ortonormal bazis."""
    n = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
    helper = np.where(np.abs(n[:, :1]) < 0.9, [[1.0, 0, 0]], [[0, 1.0, 0]])
    t = np.cross(helper, n)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    b = np.cross(n, t)
    return t, b, n


def occlusion(pos: np.ndarray, nrm: np.ndarray, idx: np.ndarray,
              others: Optional[Tuple[np.ndarray, np.ndarray]] = None) -> np.ndarray:
    """Har nuqta uchun yorug'lik ko'paytuvchisi (0..1): 1 — ochiq joy, kichik — yopiq joy.

    others — (nuqtalar, indekslar): yonida turgan boshqa organlar. Ular ham yorug'likni to'sadi — masalan,
    yurak aorta ildiziga soya tushiradi, aks holda yig'ilgan organlar tutashgan joyda yorug' "chok" qoladi.
    """
    if len(pos) == 0:
        return np.ones(0)
    lo, hi = pos.min(axis=0), pos.max(axis=0)
    size = float((hi - lo).max()) or 1.0
    cell = size / GRID
    reach = REACH * size
    tri = pos[idx.reshape(-1, 3)]
    if others is not None and len(others[1]):
        near = others[0][others[1].reshape(-1, 3)]
        mid = near.mean(axis=1)
        keep = ((mid > lo - reach - cell) & (mid < hi + reach + cell)).all(axis=1)
        if keep.any():
            lo, hi = lo - reach - 2 * cell, hi + reach + 2 * cell          # panjara qo'shnilarni ham sig'dirsin
            tri = np.concatenate([tri, near[keep]])
    dims = np.ceil((hi - lo) / cell).astype(int) + 3
    occ = np.zeros(dims, dtype=bool)

    # Yuzani panjaraga "chizish": uchburchak ichidan bir nechta nuqta (katta uchburchaklar uchun ko'proq).
    weights = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1], [2, 1, 1], [1, 2, 1], [1, 1, 2],
                        [1, 1, 0], [0, 1, 1], [1, 0, 1]], dtype=float)
    weights /= weights.sum(axis=1, keepdims=True)
    pts = np.einsum("wk,tkd->twd", weights, tri).reshape(-1, 3)
    cells = np.clip(np.floor((pts - lo) / cell).astype(int) + 1, 0, dims - 1)
    occ[cells[:, 0], cells[:, 1], cells[:, 2]] = True

    t, b, n = _basis(nrm.astype(float))
    dirs = _directions(RAYS)
    steps = np.linspace(1.6 * cell, reach, STEPS)
    blocked = np.zeros((len(pos), RAYS), dtype=bool)
    start = pos + n * (0.6 * cell)               # o'z yuzasiga urilmaslik uchun biroz tashqaridan
    for k, (dx, dy, dz) in enumerate(dirs):
        world = t * dx + b * dy + n * dz
        hit = np.zeros(len(pos), dtype=bool)
        for s in steps:
            p = np.floor((start + world * s - lo) / cell).astype(int) + 1
            p = np.clip(p, 0, dims - 1)
            hit |= occ[p[:, 0], p[:, 1], p[:, 2]]
        blocked[:, k] = hit
    weight = dirs[:, 2]                           # normalga yaqin nur muhimroq
    amount = (blocked * weight).sum(axis=1) / weight.sum()
    return np.clip(1.0 - STRENGTH * amount, 0.0, 1.0) ** 1.8


def cavity(pos: np.ndarray, nrm: np.ndarray, idx: np.ndarray, rounds: int = 12) -> np.ndarray:
    """Egrilik bo'yicha yorug'lik (0..1.15): botiq joy (egat) qorong'i, qavariq joy (burma tepasi) biroz yorug'.

    Har nuqta qo'shnilari o'rtasiga bir necha marta "silliqlanadi"; nuqta silliqlangan yuzadan qancha ichkarida
    qolsa — shuncha botiq. Atlasdagi egatlar keng va sayoz, nur bilan hisoblangan soya ularni deyarli
    qoraytirmaydi; bu usul esa egat chizig'ini aniq ko'rsatadi.
    """
    tri = idx.reshape(-1, 3)
    a = np.concatenate([tri[:, 0], tri[:, 1], tri[:, 2], tri[:, 1], tri[:, 2], tri[:, 0]])
    b = np.concatenate([tri[:, 1], tri[:, 2], tri[:, 0], tri[:, 0], tri[:, 1], tri[:, 2]])
    degree = np.bincount(a, minlength=len(pos)).astype(float)
    degree[degree == 0] = 1
    smooth = pos.astype(float).copy()
    for _ in range(rounds):
        smooth = np.stack([np.bincount(a, weights=smooth[b, k], minlength=len(pos)) for k in range(3)],
                          axis=1) / degree[:, None]
    depth = ((smooth - pos) * nrm).sum(axis=1)       # musbat — nuqta atrofidan pastda (botiq)
    scale = np.percentile(np.abs(depth), 90) or 1.0
    d = np.clip(depth / scale, -1.0, 1.5)
    return np.where(d > 0, 1.0 - 0.6 * np.minimum(d, 1.2) / 1.2, 1.0 + 0.12 * np.minimum(-d, 1.0))


def _mottle(pos: np.ndarray, amount: float) -> np.ndarray:
    """Tirik to'qimaning notekis rangi: yuza bo'ylab yumshoq qizg'ish va och dog'lar (N×3 ko'paytuvchi).

    Bir necha chastotadagi sinus to'lqinlar yig'indisi (tasodifiy, lekin har safar bir xil) — tekstura kerak emas.
    """
    size = float((pos.max(axis=0) - pos.min(axis=0)).max()) or 1.0
    rng = np.random.default_rng(7)
    wave = np.zeros(len(pos))
    for freq in (3.0, 7.0, 15.0):
        for _ in range(3):
            direction = rng.normal(size=3)
            direction /= np.linalg.norm(direction)
            wave += np.sin(pos @ direction * (freq * 2 * np.pi / size) + rng.uniform(0, 2 * np.pi)) / freq ** 0.6
    wave /= np.abs(wave).max() or 1.0
    red = 1.0 + amount * 0.6 * wave              # dog'larda qizilroq, oraliqda och sariqroq
    other = 1.0 - amount * wave
    return np.stack([red, other, other * 0.98], axis=1)


def colors(pos: np.ndarray, nrm: np.ndarray, idx: np.ndarray, tint=(1.0, 1.0, 1.0), mottle: float = 0.0,
           others: Optional[Tuple[np.ndarray, np.ndarray]] = None) -> np.ndarray:
    """glTF COLOR_0 uchun N×4 uint8 (chiziqli rang; material rangiga ko'paytiriladi).

    tint — soyadagi rang ko'paytuvchisi (chiziqli, 0..1): ochiq joyda 1, to'liq yopiq joyda tint ga yaqinlashadi.
    Masalan, miya egatlari kulrang emas, qizg'ish-qoramtir bo'lsin: tint qizil kanali kattaroq.
    others — qo'shni organlar geometriyasi (soya tushiradi, `occlusion` ga qarang).
    """
    light = (occlusion(pos, nrm, idx, others) * cavity(pos, nrm, idx))[:, None]
    shadow = np.asarray(tint, dtype=float)[None, :]
    dark = np.clip(1.0 - light, 0.0, 1.0)
    rgb = np.minimum(light, 1.0) + dark * shadow * np.sqrt(np.clip(light, 0, 1))  # soyada tint rangi
    rgb *= np.where(light > 1.0, light, 1.0)       # qavariq joy biroz yorug'roq
    if mottle:
        rgb = rgb * _mottle(pos, mottle)
    value = np.round(np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    return np.concatenate([value, np.full((len(value), 1), 255, dtype=np.uint8)], axis=1)

