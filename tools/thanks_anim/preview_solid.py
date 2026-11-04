"""Fonli personajlar uchun mini oyna namunasi (`preview.mp4`, `poster.jpg`) va reklama videosi uchun katta klip.

Haqiqiy sahifa (PPTX) LibreOffice orqali rasmga aylantiriladi, personaj videosi ustiga qo'yiladi — namuna
foydalanuvchi oladigan sahifaning aynan o'zi bo'ladi.

    python tools/thanks_anim/preview_solid.py [kalit ...]          # katalogdagi barcha fonli personajlar
"""
import os
import shutil
import subprocess
import sys
import tempfile

from pptx import Presentation

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from services.premium_presentation import themes  # noqa: E402
from services.thanks_anim import catalog, slide, solid_slide  # noqa: E402


def _run(cmd, **kw):
    res = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if res.returncode:
        raise RuntimeError(" ".join(cmd[:3]) + ": " + res.stderr[-500:])


def _blank_deck(path):
    prs = Presentation()
    prs.slide_width, prs.slide_height = 12192000, 6858000
    prs.slides.add_slide(prs.slide_layouts[6])
    prs.save(path)


def build_stills(anims, work):
    """Har animatsiyaning "Rahmat" sahifasi (personajsiz) 1920x1080 PNG sifatida. Qaytaradi: {kalit: yo'l}."""
    base = os.path.join(work, "base.pptx")
    _blank_deck(base)
    theme = themes.for_deck("Moliyaviy savodxonlik", "toza", "kam")
    files = []
    for a in anims:
        out = os.path.join(work, f"{a.key}.pptx")
        slide.add_thanks_slide(base, out, a, theme, "uz", "Javlonbek")
        prs = Presentation(out)
        s = prs.slides[-1]
        for sh in list(s.shapes):                       # GIF va ovoz olib tashlanadi — personaj video bilan qo'yiladi
            if sh.shape_type == 13 and (sh.left < 0 or sh.image.content_type == "image/gif"):
                sh._element.getparent().remove(sh._element)
        # faqat oxirgi sahifa qolsin
        ids = prs.slides._sldIdLst
        for sld in list(ids)[:-1]:
            ids.remove(sld)
        prs.save(out)
        files.append(out)
    _run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", work] + files, timeout=600)
    stills = {}
    for a in anims:
        pdf = os.path.join(work, f"{a.key}.pdf")
        _run(["pdftoppm", "-scale-to-x", "1920", "-scale-to-y", "1080", "-f", "1", "-l", "1", "-png", "-singlefile", pdf,
              os.path.join(work, f"{a.key}_still")])
        stills[a.key] = os.path.join(work, f"{a.key}_still.png")
    return stills


def _overlay_graph(anim):
    """ffmpeg filtri: personaj videosi sahifa rasmi ustiga (fonli — to'liq ustun, shaffof — niqob bilan)."""
    if anim.solid:
        sx, sw = solid_slide.strip_geometry(anim)
        return f"[1:v]fps=30,scale={sw}:1080:flags=lanczos[v];[0:v][v]overlay={sx}:0:shortest=1"
    cw = int(488 * slide.CHAR_H / 600)
    cw = min(cw, slide.PANEL_W - 40)
    ch = int(600 * cw / 488)
    x, y = slide.PANEL_X + (slide.PANEL_W - cw) // 2, 1080 - ch - 30
    return (f"[1:v]fps=30,split[l][r];[l]crop=iw/2:ih:0:0[c];[r]crop=iw/2:ih:iw/2:0,format=gray[m];"
            f"[c][m]alphamerge,scale={cw}:{ch}:flags=lanczos[ca];[0:v][ca]overlay={x}:{y}:shortest=1:format=auto")


def make_hq(anim, still, out):
    """1920x1080, 30 fps, ovozsiz klip (reklama videosi uchun)."""
    _run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "30", "-i", still, "-i",
          anim.path("packed.mp4"), "-filter_complex", _overlay_graph(anim) + ",format=yuv420p", "-an", "-c:v",
          "libx264", "-crf", "17", "-preset", "medium", "-t", "10", out], timeout=300)


def make_preview(anim, still, folder):
    """Mini oyna: 960x540, ovozi bilan; muqova — 4-soniyadagi kadr."""
    _run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "25", "-i", still, "-i",
          anim.path("packed.mp4"), "-filter_complex",
          _overlay_graph(anim).replace("fps=30", "fps=25") + ",scale=960:540:flags=lanczos,format=yuv420p[o]",
          "-map", "[o]", "-map", "1:a?", "-c:v", "libx264", "-crf", "24", "-preset", "slow", "-c:a", "aac",
          "-b:a", "80k", "-t", "10", "-shortest", "-movflags", "+faststart",
          os.path.join(folder, "preview.mp4")], timeout=300)
    _run(["ffmpeg", "-v", "error", "-y", "-ss", "4", "-i", os.path.join(folder, "preview.mp4"), "-frames:v", "1",
          "-q:v", "4", os.path.join(folder, "poster.jpg")])


if __name__ == "__main__":
    only = set(sys.argv[1:])
    anims = [a for a in catalog.ANIMATIONS if a.solid and (not only or a.key in only)]
    work = tempfile.mkdtemp(prefix="preview_solid_")
    try:
        stills = build_stills(anims, work)
        for a in anims:
            make_preview(a, stills[a.key], os.path.join(catalog.ASSETS, a.key))
            print("namuna:", a.key)
    finally:
        shutil.rmtree(work, ignore_errors=True)
