"""Mini oyna uchun namuna: tayyor "Rahmat" sahifasi videosi (matn animatsiyasi + personaj + ovoz)."""
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 960, 540, 25
DARK, ACC, DEEP, GLOW, PANEL = (0x0B, 0x1B, 0x33), (0x2E, 0x5A, 0xAC), (0x06, 0x0F, 0x1C), (0x82, 0x9C, 0xCD), (0xE7, 0xEB, 0xF8)
FB = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
S = W / 1920


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _ease(v):
    v = min(max(v, 0.0), 1.0)
    return 1 - (1 - v) ** 3


def _background():
    yy, xx = np.mgrid[0:H, 0:W]
    t = np.clip((xx / W + yy / H) / 2, 0, 1)[..., None]
    c0, c1 = np.array(_mix(DARK, ACC, 0.3)), np.array(DEEP)
    bg = Image.fromarray((c0 + (c1 - c0) * t).astype(np.uint8))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([v * S for v in (700, -50, 1100, 350)], fill=90)
    bg = Image.composite(Image.new("RGB", (W, H), ACC), bg, glow.filter(ImageFilter.GaussianBlur(30)))
    d = ImageDraw.Draw(bg)
    for r, a in ((520, 0.30), (400, 0.22), (280, 0.14)):
        r *= S
        d.ellipse((-r, H - r, r, H + r), outline=_mix(DEEP, GLOW, a), width=2)
    d.rectangle((int(1060 * S), 0, W, H), fill=PANEL)
    return bg


def _text(img, txt, font, x, y, colour, a, dy):
    if a <= 0:
        return
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).text((x, y + dy), txt, font=font, fill=colour + (int(255 * a),))
    img.alpha_composite(lay)


def render(packed: str, out: str, title: str = "E'tiboringiz uchun rahmat!",
           subtitle: str = "Savollaringiz bo'lsa, marhamat", label: str = "SO'NGGI SO'Z") -> None:
    pw, ph = (int(v) for v in subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of",
         "csv=p=0", packed]).decode().split(","))
    cw = pw // 2
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                         "csv=p=0", packed]))
    bg = _background()
    f_lab, f_big = ImageFont.truetype(FB, int(40 * S)), ImageFont.truetype(FB, int(118 * S))
    f_sub = ImageFont.truetype(FR, int(50 * S))
    words, lines, cur = title.split(), [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if f_big.getlength(test) > 860 * S and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = test
    lines.append(cur)
    pos, y = [], 400 * S
    for ln in lines:
        x = 150 * S
        for w_ in ln.split():
            pos.append((w_, x, y))
            x += f_big.getlength(w_ + " ")
        y += 135 * S
    ybot = y
    ch = int(900 * S)
    chw = int(cw * ch / ph)
    if chw > 820 * S:                  # keng personaj panelga sig'sin (taqdimotdagi kabi)
        chw = int(820 * S)
        ch = int(ph * chw / cw)
    reader = subprocess.Popen(["ffmpeg", "-v", "error", "-i", packed, "-vf", f"fps={FPS}", "-f", "rawvideo",
                               "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-i", packed, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264",
                            "-crf", "27", "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "80k",
                            "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    size = pw * ph * 3
    for i in range(int(dur * FPS)):
        raw = reader.stdout.read(size)
        if len(raw) < size:
            break
        s = i / FPS
        frame = np.frombuffer(raw, np.uint8).reshape(ph, pw, 3)
        char = Image.fromarray(np.dstack([frame[:, :cw], frame[:, cw:, 0]]), "RGBA").resize((chw, ch), Image.LANCZOS)
        img = bg.convert("RGBA")
        p = _ease(s / 0.7)
        img.alpha_composite(char, (int(1060 * S + (860 * S - chw) / 2), int(H - ch - 30 * S + (1 - p) * 150)))
        a = _ease((s - 0.2) / 0.5)
        _text(img, " ".join(label), f_lab, 150 * S, 300 * S, GLOW, a, (1 - a) * 10)
        bar = _ease((s - 0.4) / 0.6)
        if bar > 0:
            ImageDraw.Draw(img).rectangle((150 * S, 365 * S, (150 + 160 * bar) * S, 373 * S), fill=ACC)
        for k, (w_, x, y) in enumerate(pos):
            a = _ease((s - 0.7 - k * 0.28) / 0.45)
            _text(img, w_, f_big, x, y, (255, 255, 255), a, (1 - a) * 20)
        t0 = 0.7 + len(pos) * 0.28 + 0.3
        a = _ease((s - t0) / 0.6)
        _text(img, subtitle, f_sub, 150 * S, ybot + 20 * S, _mix(DARK, (255, 255, 255), 0.75), a, (1 - a) * 10)
        enc.stdin.write(img.convert("RGB").tobytes())
    enc.stdin.close()
    enc.wait()
    reader.kill()          # kadrlar sanog'i yaxlitlangani uchun o'quvchida bitta-ikkita kadr qolishi mumkin
    reader.wait()
