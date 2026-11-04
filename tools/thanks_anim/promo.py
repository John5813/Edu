"""Reklama videosi: "Slaydni shunday yakunlang".

  0,0–2,5   Paxmoq «Rahmat» sahifasida raqsga tushadi, tepada kulgan smayl va «Slaydni shunday yakunlang!»
  2,5–3,5   kamera uzoqlashadi — barcha personajlar (har biri o'z sahifasida) ko'rinadi
  3,5–4,5   umumiy ko'rinish
  4,5–10,0  ketma-ket 4 ta shablon zoom bilan kattalashadi (har biri 1 soniya, o'tishda kamera "sakraydi")
  10,0–12,5 edufayl logotipi

Vaqtlar `promo_music.py` dagi zarblar bilan bir xil. Ishga tushirish:

    python tools/thanks_anim/promo.py <ish_papkasi> <chiqish.mp4>

`ish_papkasi` ga oraliq fayllar (sahifa rasmlari, katta klip) yoziladi.
"""
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import promo_music as M  # noqa: E402
import preview_solid  # noqa: E402
from services.thanks_anim import catalog  # noqa: E402

W, H, FPS = 1920, 1080, 30
TOTAL = M.TOTAL
GAP = 150
COLS, ROWS = 6, 4
LQ_W, LQ_H = 480, 270
HERO = "paxmoq"                                    # "Momiq": oldingi personaj
TEMPLATES = ["balerina", "tillarang_mushuk", "kapibara_raqs", "pingvin"]
ARRIVE = list(M.ARRIVALS)                          # 4.5, 6.0, 7.5, 9.0
CELL = {HERO: (2, 1), TEMPLATES[0]: (1, 2), TEMPLATES[1]: (4, 1), TEMPLATES[2]: (3, 3), TEMPLATES[3]: (5, 2)}
INTER = "/usr/share/fonts/opentype/inter/Inter-%s.otf"
NAVY, BLUE = (11, 27, 51), (28, 63, 120)

# ───────────────────────────────────────────── kamera


def ease(u):                                        # silliq tezlanish-sekinlanish
    u = min(max(u, 0.0), 1.0)
    return u * u * u * (u * (u * 6 - 15) + 10)


def ease_out(u):
    u = min(max(u, 0.0), 1.0)
    return 1 - (1 - u) ** 3


def back(u, s=1.7):                                 # sakrab chiqish (overshoot)
    u = min(max(u, 0.0), 1.0)
    return 1 + (s + 1) * (u - 1) ** 3 + s * (u - 1) ** 2


class Layout:
    """Tilelar joyi: 6x4 to'r; kamera (markaz, masshtab) vaqt bo'yicha."""

    def __init__(self, order):
        self.pos = {}
        free = [(c, r) for r in range(ROWS) for c in range(COLS) if (c, r) not in CELL.values()]
        rest = [k for k in order if k not in CELL]
        for k, cell in zip(rest, free):
            self.pos[k] = cell
        self.pos.update(CELL)
        self.gw = COLS * W + (COLS - 1) * GAP
        self.gh = ROWS * H + (ROWS - 1) * GAP
        self.wide_z = min(W / (self.gw + 2 * 700), H / (self.gh + 2 * 700))

    def centre(self, key):
        c, r = self.pos[key]
        return c * (W + GAP) + W / 2, r * (H + GAP) + H / 2

    def wide(self):
        return self.gw / 2, self.gh / 2, self.wide_z

    def camera(self, t):
        hero = (*self.centre(HERO), 1.0)
        wide = self.wide()
        if t < 2.5:
            return hero[0], hero[1], 1.0 + 0.02 * ease(t / 2.5)             # sekin yaqinlashish
        if t < 3.5:
            return self._mix(hero[0], hero[1], 1.02, *wide, ease((t - 2.5) / 1.0), dip=0.0)
        if t < ARRIVE[0] - 0.5:
            return wide[0], wide[1], wide[2] * (1 + 0.05 * ease((t - 3.5) / 0.5))
        stops = [(*self.centre(k), 1.0) for k in TEMPLATES]
        if t < ARRIVE[0]:
            return self._mix(wide[0], wide[1], wide[2] * 1.05, *stops[0], ease_out((t - ARRIVE[0] + 0.5) / 0.5), dip=0)
        for i in range(3):
            leave = ARRIVE[i + 1] - 0.5
            if t < leave:
                return stops[i][0], stops[i][1], 1.0 + 0.03 * ((t - ARRIVE[i]) / (leave - ARRIVE[i]))
            if t < ARRIVE[i + 1]:
                u = ease((t - leave) / 0.5)
                return self._mix(*stops[i][:2], 1.03, *stops[i + 1], u, dip=1.5)
        return stops[3][0], stops[3][1], 1.0 + 0.03 * min((t - ARRIVE[3]) / 1.0, 1)

    @staticmethod
    def _mix(x0, y0, z0, x1, y1, z1, u, dip=0.0):
        z = math.exp(math.log(z0) + (math.log(z1) - math.log(z0)) * u - dip * math.sin(math.pi * u))
        return x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, z

    def rect(self, key, cam):
        cx, cy, z = cam
        c, r = self.pos[key]
        x, y = c * (W + GAP), r * (H + GAP)
        return (x - cx) * z + W / 2, (y - cy) * z + H / 2, W * z, H * z


# ───────────────────────────────────────────── video o'quvchilar


class Reader:
    def __init__(self, path, w, h, offset=0.0):
        self.w, self.h = w, h
        cmd = ["ffmpeg", "-v", "error"]
        if offset:
            cmd += ["-ss", f"{offset:.3f}"]
        cmd += ["-stream_loop", "-1", "-i", path, "-vf", f"fps={FPS},scale={w}:{h}:flags=lanczos", "-f", "rawvideo",
                "-pix_fmt", "rgb24", "-"]
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=w * h * 3 * 2)
        self.last = Image.new("RGB", (w, h), (255, 255, 255))

    def read(self):
        raw = self.p.stdout.read(self.w * self.h * 3)
        if len(raw) == self.w * self.h * 3:
            self.last = Image.frombytes("RGB", (self.w, self.h), raw)
        return self.last

    def close(self):
        self.p.kill()
        self.p.wait()


# ───────────────────────────────────────────── smayl va yozuv

_emoji_cache = {}


def emoji(size):
    if "base" not in _emoji_cache:
        f = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109)
        im = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((4, 4), "😂", font=f, embedded_color=True)
        _emoji_cache["base"] = im.crop(im.getbbox()).resize((218, 218), Image.LANCZOS)   # 2x: lanczos
    return _emoji_cache["base"].resize((size, size), Image.LANCZOS)


def bubble(text, scale=1.0):
    f = ImageFont.truetype(INTER % "ExtraBold", 46)
    l, t, r, b = f.getbbox(text)
    pad_x, pad_y = 44, 26
    w, h = r - l + 2 * pad_x, (b - t) + 2 * pad_y
    img = Image.new("RGBA", (w + 80, h + 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((40, 38, 40 + w, 38 + h), h // 2, fill=(0, 0, 0, 90))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    d.rounded_rectangle((40, 30, 40 + w, 30 + h), h // 2, fill=(255, 255, 255, 255))
    d.polygon([(40 + 70, 30 + h - 2), (40 + 130, 30 + h - 2), (40 + 60, 30 + h + 30)], fill=(255, 255, 255, 255))
    d.text((40 + pad_x - l, 30 + pad_y - t), text, font=f, fill=(24, 42, 90, 255))
    if scale != 1.0:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    return img


def hero_overlay(frame, t, geo):
    """Paxmoq sahifasi ustiga smayl va yozuv (sahifa koordinatasida — kamera bilan birga uzoqlashadi)."""
    cx, cy = geo["smiley"]
    if 0.5 <= t < 3.6:
        # smayl chiqishi: sakrab chiqadi, so'ng kuladi (tebranish + urg'uda "pulse")
        u = back((t - M.SMILEY) / 0.45)
        beat = (t - M.SMILEY) % M.BEAT / M.BEAT
        pulse = 1 + 0.06 * (1 - beat) ** 2
        size = max(4, int(190 * u * pulse))
        img = emoji(size).rotate(9 * math.sin((t - M.SMILEY) * 2 * math.pi * 3.2) * min(1, (t - M.SMILEY) / 0.5),
                                 resample=Image.BICUBIC, expand=True)
        frame.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))
    if 0.8 <= t < 3.6:
        u = back((t - 0.8) / 0.4, 1.4)
        bub = bubble("Slaydni shunday yakunlang!", max(0.05, u))
        bx, by = geo["bubble"]
        frame.alpha_composite(bub, (int(bx - bub.width / 2), int(by - bub.height / 2)))
    return frame


# ───────────────────────────────────────────── tile chizish

_mask_cache = {}


def rounded(w, h, r):
    key = (w, h, r)
    if key not in _mask_cache:
        m = Image.new("L", (w * 2, h * 2), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w * 2 - 1, h * 2 - 1), r * 2, fill=255)
        _mask_cache[key] = m.resize((w, h), Image.LANCZOS)
        if len(_mask_cache) > 400:
            _mask_cache.pop(next(iter(_mask_cache)))
    return _mask_cache[key]


def background():
    yy, xx = np.mgrid[0:H, 0:W]
    t = np.clip(0.55 * yy / H + 0.45 * xx / W, 0, 1)[..., None]
    img = np.array(NAVY) + (np.array(BLUE) - np.array(NAVY)) * t
    glow = np.exp(-(((xx - W * 0.5) / 900) ** 2 + ((yy - H * 0.45) / 520) ** 2))[..., None]
    img = img + glow * np.array([25, 45, 80])
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")


# ───────────────────────────────────────────── logotip

def logo_scene(t, logo, sparkles):
    """10.0 s dan: oq iris ochiladi, logotip sakrab chiqadi, qo'ng'iroqchalar bilan yulduzchalar chaqnaydi."""
    k = t - M.END
    frame = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    u = back(k / 0.6, 1.3)
    size = max(8, int(720 * (0.55 + 0.45 * u)))
    lg = logo.resize((size, size), Image.LANCZOS)
    # ingichka pulsatsiyalovchi halqa
    ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    for j, (delay, col) in enumerate(((0.0, (20, 62, 128)), (0.35, (70, 120, 200)))):
        kk = (k - delay) / 1.6
        if 0 < kk < 1:
            r = 330 + 520 * ease_out(kk)
            a = int(150 * (1 - kk))
            rd.ellipse((W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r), outline=col + (a,), width=6)
    frame.alpha_composite(ring)
    fade = min(max(k / 0.12, 0), 1)
    lg_a = lg.convert("RGBA")
    lg_a.putalpha(int(255 * fade))
    frame.alpha_composite(lg_a, (int(W / 2 - size / 2), int(H / 2 - size / 2)))
    d = ImageDraw.Draw(frame)
    for (sx, sy, r0, delay) in sparkles:
        kk = (k - delay) / 0.9
        if 0 < kk < 1:
            r = r0 * math.sin(math.pi * kk) ** 0.8
            pts = []
            for i in range(8):
                rad = r if i % 2 == 0 else r * 0.26
                a = math.radians(i * 45 - 90)
                pts.append((sx + rad * math.cos(a), sy + rad * math.sin(a)))
            d.polygon(pts, fill=(36, 92, 176, 255))
    # kirishdagi oq iris: oxirgi shablondan logotipga o'tish
    return frame


# ───────────────────────────────────────────── asosiy


def main(work, out):
    os.makedirs(work, exist_ok=True)
    anims = {a.key: a for a in catalog.ANIMATIONS}
    featured = [HERO] + TEMPLATES
    # 1) shablonlar rasmlari va katta klip
    stills = preview_solid.build_stills([anims[k] for k in featured], work)
    hq = {}
    for k in featured:
        hq[k] = os.path.join(work, f"{k}_hq.mp4")
        if not os.path.exists(hq[k]):
            preview_solid.make_hq(anims[k], stills[k], hq[k])
    order = [a.key for a in catalog.ANIMATIONS]
    lay = Layout(order)
    lq = {k: Reader(anims[k].path("preview.mp4"), LQ_W, LQ_H) for k in order if k not in featured}
    hero = Reader(hq[HERO], W, H)
    # shablonlar: katta klip faqat o'z vaqtida o'qiladi
    windows = {k: (ARRIVE[i] - 0.9, (ARRIVE[i + 1] - 0.1) if i < 3 else 10.2) for i, k in enumerate(TEMPLATES)}
    small = {k: Reader(anims[k].path("preview.mp4"), LQ_W, LQ_H) for k in TEMPLATES}
    big = {}
    logo = Image.open(os.path.join(ROOT, "assets", "brand", "edufayl_logo.jpg")).convert("RGB")
    sparkles = [(W / 2 - 430, H / 2 - 250, 34, 0.35), (W / 2 + 450, H / 2 - 220, 28, 0.5), (W / 2 + 380, H / 2 + 300, 36, 0.62),
                (W / 2 - 480, H / 2 + 260, 26, 0.75), (W / 2, H / 2 - 420, 30, 0.9), (W / 2 - 250, H / 2 + 430, 22, 1.0),
                (W / 2 + 160, H / 2 + 440, 24, 1.1)]
    bg = background()
    geo = {"smiley": (1490, 108), "bubble": (1490, 240)}

    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-i", os.path.join(work, "music.wav"), "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt",
         "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", f"{TOTAL}", "-movflags", "+faststart", out],
        stdin=subprocess.PIPE)
    n = int(TOTAL * FPS)
    for i in range(n):
        t = i / FPS
        if t >= M.END:
            frame = logo_scene(t, logo, sparkles)
            # shablondan oq iris: logotipga o'tish 0.25 s
        else:
            cam = lay.camera(t)
            frame = bg.copy()
            # o'qish: kadrlar har doim ketma-ket o'qiladi (sinxron qolsin)
            lq_frames = {k: r.read() for k, r in lq.items()}
            sm_frames = {k: r.read() for k, r in small.items()}
            hero_frame = hero.read().convert("RGBA")
            hero_overlay(hero_frame, t, geo)
            for k in TEMPLATES:
                a, b = windows[k]
                if a <= t <= b:
                    if k not in big:
                        big[k] = Reader(hq[k], W, H, offset=0)
                    big[k].read()
                elif k in big and t > b:
                    big.pop(k).close()
            for k in order:
                x, y, w, h = lay.rect(k, cam)
                if x > W or y > H or x + w < 0 or y + h < 0 or w < 4:
                    continue
                if k == HERO:
                    src = hero_frame
                elif k in TEMPLATES and k in big and w > 520:
                    src = big[k].last
                elif k in TEMPLATES:
                    src = sm_frames[k]
                else:
                    src = lq_frames[k]
                tw, th = max(2, int(round(w))), max(2, int(round(h)))
                tile = src.convert("RGBA").resize((tw, th), Image.BILINEAR if tw < src.width else Image.BICUBIC)
                rad = int(min(tw, th) * 0.035)
                mask = rounded(tw, th, rad)
                if w < 900:                                    # uzoqdan — ramka va yumshoq soya
                    sh = Image.new("RGBA", (tw + 24, th + 24), (0, 0, 0, 0))
                    sh.paste((0, 0, 0, 110), (12, 16), mask)
                    frame.alpha_composite(sh.filter(ImageFilter.GaussianBlur(7)), (int(x) - 12, int(y) - 12))
                frame.paste(tile.convert("RGB"), (int(round(x)), int(round(y))), mask)
                if w < 900:
                    ImageDraw.Draw(frame).rounded_rectangle((x, y, x + w, y + h), rad, outline=(255, 255, 255, 90),
                                                            width=max(1, int(w / 140)))
            if t >= M.END - 0.15:                              # logotipdan oldin qisqa oq chaqnash
                flash = Image.new("RGB", (W, H), (255, 255, 255))
                frame = Image.blend(frame.convert("RGB"), flash, min(1.0, (t - (M.END - 0.15)) / 0.15))
        enc.stdin.write(frame.convert("RGB").tobytes())
    enc.stdin.close()
    enc.wait()
    for r in list(lq.values()) + list(small.values()) + list(big.values()) + [hero]:
        r.close()


if __name__ == "__main__":
    work, out = sys.argv[1], sys.argv[2]
    if not os.path.exists(os.path.join(work, "music.wav")):
        os.makedirs(work, exist_ok=True)
        M.write_wav(os.path.join(work, "music.wav"), M.render())
    main(work, out)
