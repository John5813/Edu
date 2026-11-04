"""Fonli (shaffofsiz) personajlarni "Rahmat" sahifasi uchun tayyorlaydi (bir martalik, qo'lda ishga tushiriladi).

Yashil fonli videolardan farqi: fon OLIB TASHLANMAYDI. Sahifa foni videoning o'z fonidan quriladi, shuning
uchun videoning chap/o'ng chetlari fon rangiga silliq qo'shiladi — GIF va sahifa orasida chegara bo'lmaydi.

    python tools/thanks_anim/prepare_solid.py <xom_videolar_papkasi> [kalit ...]

Har animatsiya uchun `assets/thanks_anim/<nom>/packed.mp4` yoziladi (oddiy rangli video, ovozi bilan).
`preview.mp4` va `poster.jpg` ni `tools/thanks_anim/preview_solid.py` yasaydi (sahifa dizayni tayyor bo'lgach).
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from services.thanks_anim.catalog import ANIMATIONS  # noqa: E402

OUT = os.path.join(ROOT, "assets", "thanks_anim")
MAX_SECONDS = 10.0
FPS = 15
FADE = 64          # px: chetdan shuncha masofada personaj fon rangiga so'nadi
HOLD = 6           # px: eng chetdagi shuncha piksel butunlay fon rangida (tikuv ko'rinmasin)


def _probe(src):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height", "-of", "csv=p=0", src]).decode().strip()
    w, h = (int(v) for v in out.split(","))
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                         "csv=p=0", src]))
    return w, h, dur


def _frames(src, x0, w, h, dur):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-t", f"{dur:.2f}", "-i", src, "-vf",
                                   f"fps={FPS},crop={w}:{h}:{x0}:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


def edge_colours(frames):
    """Har qator uchun fon rangi: eng chetdagi ustunlarning vaqt bo'yicha medianasi (personaj tegmagan payt)."""
    left = np.median(frames[:, :, :4].astype(np.float32).mean(2), 0)
    right = np.median(frames[:, :, -4:].astype(np.float32).mean(2), 0)
    edge = (left + right) / 2
    # Personaj chetga tegib turgan qatorlar (quyon qulog'i, mushuk dumi) fonni buzmasin: qator bo'yicha
    # katta oynali median (≈ ±60 qator) — fon silliq, torroq dog'lar tushib qoladi.
    r = 60
    padded = np.pad(edge, ((r, r), (0, 0)), mode="edge")
    wins = np.lib.stride_tricks.sliding_window_view(padded, 2 * r + 1, axis=0)       # (h, 3, 2r+1)
    edge = np.median(wins, axis=2)
    k = 15                                             # vertikal tekislash (donador chiziqlarsiz)
    pad = np.pad(edge, ((k, k), (0, 0)), mode="edge")
    csum = np.cumsum(np.pad(pad, ((1, 0), (0, 0))), 0)
    return (csum[2 * k + 1:] - csum[:-2 * k - 1]) / (2 * k + 1)


def blend_edges(frames, bg):
    """Chap va o'ng chetlarda kadrni fon rangiga so'ndiradi (qator bo'yicha)."""
    h, w = frames.shape[1:3]
    ramp = np.clip((FADE - np.arange(w)) / (FADE - HOLD), 0, 1)
    ramp = np.maximum(ramp, ramp[::-1])
    ramp = ramp * ramp * (3 - 2 * ramp)                # yumshoq o'tish
    a = ramp[None, :, None]
    fill = bg[:, None, :]
    out = frames.astype(np.float32) * (1 - a) + fill * a
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def prepare(anim, raw_dir):
    src = os.path.join(raw_dir, anim.source)
    pw, ph, vdur = _probe(src)
    x0, x1 = anim.crop or (0, pw)
    w = (x1 - x0) // 2 * 2
    dur = min(vdur, MAX_SECONDS)
    frames = _frames(src, x0, w, ph, dur)
    bg = edge_colours(frames)
    if anim.bg:                                        # fon bir xil rang: chetga tegqan personaj fonni buzmaydi
        bg = np.tile(np.array([int(anim.bg[i:i + 2], 16) for i in (0, 2, 4)], np.float32), (len(bg), 1))
    frames = blend_edges(frames, bg)
    folder = os.path.join(OUT, anim.key)
    os.makedirs(folder, exist_ok=True)
    packed = os.path.join(folder, "packed.mp4")
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{ph}", "-r", str(FPS),
         "-i", "-", "-ss", "0", "-t", f"{dur:.2f}", "-i", src, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264",
         "-crf", "20", "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-shortest",
         "-movflags", "+faststart", packed], stdin=subprocess.PIPE)
    enc.communicate(frames.tobytes())
    if enc.returncode:
        raise RuntimeError("ffmpeg xatosi: " + anim.key)
    print(f"{anim.key}: {w}x{ph}, {dur:.1f} s, fon chetda {bg[0].astype(int)}…{bg[-1].astype(int)}")


if __name__ == "__main__":
    raw_dir = sys.argv[1]
    only = set(sys.argv[2:])
    for anim in ANIMATIONS:
        if anim.solid and (not only or anim.key in only):
            prepare(anim, raw_dir)
