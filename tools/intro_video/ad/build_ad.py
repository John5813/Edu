"""Instagram reklamasi uchun vertikal video (1080x1920, 9:16), 27 soniya.

Saytning haqiqiy mobil kadrlari (record.js `mobile` yozuvi) telefon ichida ko'rsatiladi, ustiga kinetik matn
va @Edufayl_bot ga chaqiruv qo'yiladi. Ovoz yo'q: reklama odatda ovozsiz ham ko'riladi, shuning uchun matn
o'zi ham asosiy xabarni olib yuradi. Ovoz tayyor bo'lsa, `--voice` bilan qo'shiladi.

    python build_ad.py <rec_m papkasi> <chiqish.mp4> [--voice ovoz.mp3]
"""
import json, math, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_STATIC = os.path.join(HERE, "..", "..", "..", "webapp", "site", "static")
W, H, FPS = 1080, 1920, 30
BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

NAVY, NAVY2 = (12, 18, 38), (26, 37, 80)          # saytning --ink va to'qroq ton
BRAND = (36, 87, 255)                              # --brand
MARK = (255, 214, 64)                              # sariq marker (saytdagi «taqdimot tayyor» rangi)
WHITE, MUTE = (255, 255, 255), (170, 180, 215)

# (boshlanish, tugash, sarlavha, pastki matn, kadr belgisi, kadr siljishi, rejim)
# Vaqtlar ovozga moslash uchun ham qulay: har sahna ovoz satriga yetadigan uzunlikda.
SCENES = [
    (0.0, 4.0, "Taqdimotga vaqt yo‘qmi?", "Mavzuni yozing — qolganini bot qiladi.", None, 0, "hook"),
    (4.0, 9.0, "Mavzuni yozing", "Til, slaydlar soni va uslubni o‘zingiz tanlaysiz.", "02", 2.5, "phone"),
    (9.0, 14.0, "AI reja va slaydlarni tayyorlaydi", "Diagramma, rasm va xulosa bilan.", "05", 9.0, "phone"),
    (14.0, 19.0, "Keyin istalgan so‘zni o‘zgartiring", "Matn va diagramma tahriri — bepul.", "07", 3.0, "phone"),
    (19.0, 23.0, "Tayyor faylni yuklab oling", "PPTX yoki Word, tahrirlanadigan holda.", "11", 4.0, "phone"),
    (23.0, 27.0, None, None, None, 0, "cta"),
]
TOTAL = SCENES[-1][1]
XFADE = 0.35


def font(path, size):
    return ImageFont.truetype(path, size)


def mix(a, b, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(round(x + (y - x) * k)) for x, y in zip(a, b))


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def wrap(draw, text, fnt, width):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= width:
            cur = trial
        else:
            lines.append(cur); cur = word
    if cur:
        lines.append(cur)
    return lines


def background():
    base = Image.new("RGB", (W, H), NAVY)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((-300, 900, 1100, 2300), fill=(40, 70, 170))
    d.ellipse((500, -400, 1500, 600), fill=(90, 60, 170))
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    return Image.blend(base, glow, 0.55)


BG = background()
FH = font(BOLD, 92)
FS = font(REG, 44)
FSMALL = font(REG, 36)
LOGO = None
try:
    LOGO = Image.open(os.path.join(SITE_STATIC, "logo.jpg")).convert("RGB").resize((220, 220))
except OSError:
    pass


def load_frames(rec):
    frames = sorted(json.load(open(os.path.join(rec, "frames.json"))), key=lambda f: f["t"])
    marks = {m["id"]: m["t"] for m in json.load(open(os.path.join(rec, "marks.json")))}
    return frames, marks, rec


def shot(rec_ctx, mark_id, offset):
    frames, marks, rec = rec_ctx
    t = marks[mark_id] + offset
    best = [f for f in frames if f["t"] <= t]
    f = best[-1] if best else frames[0]
    return Image.open(os.path.join(rec, "frames", f["file"])).convert("RGB")


def phone_layer(img, zoom):
    """Telefon kadri: burchaklari yumaloq, soyasi bor, sekin zoom bilan."""
    pw, ph = 600, 1067
    crop_w, crop_h = int(img.width / zoom), int(img.height / zoom)
    x0 = (img.width - crop_w) // 2
    y0 = int((img.height - crop_h) * 0.35)   # yuqori qismiga yaqin: sarlavha va tugmalar ko'rinadi
    part = img.crop((x0, y0, x0 + crop_w, y0 + crop_h)).resize((pw, ph), Image.LANCZOS)
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), radius=44, fill=255)
    return part, mask


def draw_phone(canvas, img, zoom, y):
    part, mask = phone_layer(img, zoom)
    x = (W - part.width) // 2
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x + 10, y + 26, x + part.width - 10, y + part.height + 30), radius=44, fill=150)
    shadow = shadow.filter(ImageFilter.GaussianBlur(34))
    canvas.paste((0, 0, 0), (0, 0), shadow)
    canvas.paste(part, (x, int(y)), mask)


def headline(d, lt, title, sub, y0=300):
    """Sarlavha va pastki matn: yuqoridan sekin paydo bo'ladi."""
    a1 = ease(lt / 0.5)
    lines = wrap(d, title, FH, W - 160)
    y = y0 + (1 - a1) * 40
    for ln in lines:
        tw = d.textlength(ln, font=FH)
        d.text(((W - tw) / 2, y), ln, font=FH, fill=mix(NAVY, WHITE, a1))
        y += 104
    a2 = ease((lt - 0.45) / 0.5)
    for ln in wrap(d, sub, FS, W - 200):
        tw = d.textlength(ln, font=FS)
        d.text(((W - tw) / 2, y + 16), ln, font=FS, fill=mix(NAVY, MUTE, a2))
        y += 58


def draw_scene(lt, sc, ctx):
    start, end, title, sub, mark, off, mode = sc
    img = BG.copy()
    d = ImageDraw.Draw(img)
    if mode == "hook":
        # Sariq chiziq «vaqt yo'qmi?» orqasida o'sadi
        a = ease(lt / 0.7)
        t1, t2 = "Taqdimotga", "vaqt yo‘qmi?"
        f = font(BOLD, 128)
        w2 = d.textlength(t2, font=f)
        y = 700
        tw = d.textlength(t1, font=f)
        d.text(((W - tw) / 2, y), t1, font=f, fill=mix(NAVY, WHITE, ease(lt / 0.4)))
        y += 150
        d.rectangle(((W - w2) / 2 - 10, y + 92, (W - w2) / 2 - 10 + (w2 + 20) * a, y + 122), fill=MARK)
        d.text(((W - w2) / 2, y), t2, font=f, fill=mix(NAVY, WHITE, ease(lt / 0.4)))
        if lt > 1.6:
            k = ease((lt - 1.6) / 0.6)
            s = "Mavzuni yozing — qolganini bot qiladi."
            sw = d.textlength(s, font=FS)
            d.text(((W - sw) / 2, 1080), s, font=FS, fill=mix(NAVY, MUTE, k))
        return img
    if mode == "cta":
        y = 420
        if LOGO is not None:
            mask = Image.new("L", LOGO.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, LOGO.width - 1, LOGO.height - 1), fill=255)
            img.paste(LOGO, ((W - LOGO.width) // 2, y), mask)
        y = 720
        for txt, f, col in (("Hozir sinab ko‘ring", FH, WHITE),):
            tw = d.textlength(txt, font=f)
            d.text(((W - tw) / 2, y), txt, font=f, fill=mix(NAVY, col, ease(lt / 0.5)))
        handle = "@Edufayl_bot"
        hf = font(BOLD, 112)
        hw = d.textlength(handle, font=hf)
        d.text(((W - hw) / 2, 860), handle, font=hf, fill=mix(NAVY, MARK, ease((lt - 0.3) / 0.5)))
        pulse = 1 + 0.03 * math.sin(lt * 2 * math.pi / 1.2) * ease((lt - 0.8) / 0.4)
        bw, bh = int(640 * pulse), int(128 * pulse)
        bx, by = (W - bw) // 2, 1080 - (bh - 128) // 2
        d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=64, fill=BRAND)
        bt = "Botni ochish →"
        bf = font(BOLD, 56)
        btw = d.textlength(bt, font=bf)
        d.text(((W - btw) / 2, by + 30), bt, font=bf, fill=WHITE)
        sub2 = "Taqdimot · Kurs ishi · Referat · Maqola · Diplom"
        for i, ln in enumerate(wrap(d, sub2, FSMALL, W - 220)):
            lw = d.textlength(ln, font=FSMALL)
            d.text(((W - lw) / 2, 1300 + i * 50), ln, font=FSMALL, fill=mix(NAVY, MUTE, ease((lt - 1.0) / 0.6)))
        return img
    # phone: telefon pastdan ko'tariladi, zoom sekin
    rise = ease(lt / 0.6)
    y = (1 - rise) * 500 + 600
    zoom = 1.0 + 0.05 * (lt / (end - start))
    draw_phone(img, shot(ctx, mark, off), zoom, y)
    d = ImageDraw.Draw(img)
    headline(d, lt, title, sub, y0=200)
    return img


def render_at(t, ctx):
    for i, sc in enumerate(SCENES):
        start, end = sc[0], sc[1]
        if start <= t < end:
            img = draw_scene(t - start, sc, ctx)
            if t > end - XFADE and i + 1 < len(SCENES):
                nxt = SCENES[i + 1]
                k = (t - (end - XFADE)) / XFADE
                img = Image.blend(img, draw_scene(0.0, nxt, ctx), ease(k))
            return img
    return draw_scene(0.0, SCENES[-1], ctx)


def main():
    args = sys.argv[1:]
    rec, out = os.path.abspath(args[0]), os.path.abspath(args[1])
    voice = args[args.index("--voice") + 1] if "--voice" in args else None
    ctx = load_frames(rec)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if voice:
        cmd += ["-i", os.path.abspath(voice), "-filter:a", f"apad,atrim=0:{TOTAL},loudnorm=I=-16:TP=-1.5,aresample=48000",
                "-c:a", "aac", "-b:a", "160k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(round(TOTAL * FPS))
    for k in range(n):
        p.stdin.write(render_at(k / FPS, ctx).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit("ffmpeg xatosi")
    print(f"{out}: {TOTAL:.0f} s, {W}x{H}, {os.path.getsize(out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
