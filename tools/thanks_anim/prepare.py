"""Yashil fonli animatsiyalarni "Rahmat" sahifasi uchun tayyorlaydi (bir martalik, qo'lda ishga tushiriladi).

Har animatsiya uchun `assets/thanks_anim/<nom>/` ga ikki fayl yoziladi:
- `packed.mp4` — chap yarmi rangli kadr, o'ng yarmi shaffoflik niqobi (oq — personaj), ovozi bilan.
  Taqdimot yig'ilayotganda shu fayldan istalgan rangdagi panel ustiga GIF yasaladi: fonni qayta
  ajratish shart emas, oddiy H.264 hamma joyda o'qiladi.
- `preview.mp4` — mini oynada ko'rsatiladigan tayyor sahifa (matn animatsiyasi + personaj + ovoz).

    python tools/thanks_anim/prepare.py <xom_videolar_papkasi>

Xom videolar nomi `SOURCES` dagi kabi bo'lishi kerak (masalan `m10.mp4`).
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from services.thanks_anim.catalog import ANIMATIONS  # noqa: E402
sys.path.insert(0, HERE)
import preview  # noqa: E402

OUT = os.path.join(ROOT, "assets", "thanks_anim")
HEIGHT = 600          # GIF balandligi (sahifada 900 px gacha cho'ziladi)
MAX_SECONDS = 10.0    # GIF hajmi katta bo'lmasin


def probe(path, entries, stream="format"):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "a:0" if stream == "a" else "v:0",
                                   "-show_entries", entries, "-of", "csv=p=0", path]).decode().strip()
    return out.split("\n")[0].split(",") if out else []


def key_colour(src):
    """Fon rangi: 1-soniyadagi kadr burchaklarining o'rtachasi (ba'zi videolar qora kadr bilan boshlanadi)."""
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", "1", "-i", src, "-frames:v", "1", "-f", "rawvideo",
                                   "-pix_fmt", "rgb24", "-"])
    w, h = (int(v) for v in probe(src, "stream=width,height", "v"))
    img = np.frombuffer(raw, np.uint8).reshape(h, w, 3)
    corners = np.concatenate([img[:20, :20].reshape(-1, 3), img[:20, -20:].reshape(-1, 3),
                              img[-20:, :20].reshape(-1, 3), img[-20:, -20:].reshape(-1, 3)])
    r, g, b = np.median(corners, 0).astype(int)
    return f"0x{r:02X}{g:02X}{b:02X}", w, h


def key_filter(colour, sim):
    return f"chromakey={colour}:{sim}:0.06,despill=type=green:mix=0.6:expand=0.1"


def bbox(src, colour, sim, w, h, start, dur):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", src, "-vf",
                                   f"fps=4,{key_filter(colour, sim)},format=rgba,alphaextract", "-f", "rawvideo",
                                   "-pix_fmt", "gray", "-"])
    alpha = np.frombuffer(raw, np.uint8).reshape(-1, h, w)
    mask = (alpha > 128).mean(0) > 0.002       # tasodifiy dog'lar hisobga olinmaydi
    ys, xs = np.where(mask)
    pad = 16
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, w)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, h)
    return x0, y0, (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2


def prepare(anim, raw_dir):
    src = os.path.join(raw_dir, anim.source)
    colour, w, h = key_colour(src)
    vdur = float(probe(src, "format=duration")[0])
    adur = probe(src, "stream=duration", "a")
    dur = min(vdur, float(adur[0]) if adur and adur[0] not in ("", "N/A") else vdur, anim.seconds or MAX_SECONDS,
              MAX_SECONDS) - anim.start
    x, y, cw, ch = bbox(src, colour, anim.similarity, w, h, anim.start, dur)
    ow = int(cw * HEIGHT / ch) // 2 * 2
    folder = os.path.join(OUT, anim.key)
    os.makedirs(folder, exist_ok=True)
    packed = os.path.join(folder, "packed.mp4")
    graph = (f"[0:v]{key_filter(colour, anim.similarity)},crop={cw}:{ch}:{x}:{y},scale={ow}:{HEIGHT}:flags=lanczos,"
             "format=rgba,split[c][m];[m]alphaextract,format=yuv420p[a];"
             "[c]format=yuv420p[cc];[cc][a]hstack[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(anim.start), "-t", f"{dur:.2f}", "-i", src,
                    "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-r", "15", "-c:v", "libx264",
                    "-crf", "23", "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "80k",
                    "-movflags", "+faststart", packed], check=True)
    preview.render(packed, os.path.join(folder, "preview.mp4"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{min(4.0, dur * 0.6):.1f}", "-i", os.path.join(folder, "preview.mp4"),
                    "-frames:v", "1", "-q:v", "4", os.path.join(folder, "poster.jpg")], check=True)
    print(f"{anim.key}: kalit {colour}, {dur:.1f} s, {ow}x{HEIGHT}")


if __name__ == "__main__":
    raw_dir = sys.argv[1]
    only = set(sys.argv[2:])
    for anim in ANIMATIONS:
        if not only or anim.key in only:
            prepare(anim, raw_dir)
