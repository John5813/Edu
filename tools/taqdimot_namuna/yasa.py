"""Botdagi dizayn namunalari rasmlarini yasaydi — haqiqiy chizish kodi bilan (qo'lda chizilgan rasm emas).

    python tools/taqdimot_namuna/yasa.py <fotolar_papkasi>

Fotolar papkasida `registon.jpg` (Registon maydonining gorizontal fotosurati) bo'lishi kerak.
3D uslublar uchun Registon, Go'ri Amir va Ulug'bek sekstanti modellari kerak (`KATALOG3D_DIR`; yo'q bo'lsa
o'zi yuklab olinadi).
Natija:
  assets/taqdimot/uslublar.jpg    — zamonaviy taqdimotning 5 uslubi (taqdimot uslubini tanlashda ko'rsatiladi)
  assets/taqdimot/turlar.jpg      — Infografik / Zamonaviy / Klassik (taqdimot turini tanlashda)
  assets/taqdimot/uslublar_3d.jpg — 3D taqdimot Pro'ning 11 uslubi («Narxlar» bo'limida)
Kerak: Playwright (Chromium), LibreOffice (`soffice`) va `pdftoppm`.
"""
import asyncio, base64, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("BOT_TOKEN", "1:x")

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(ROOT, "assets", "taqdimot")
TOPIC = "Samarqand — Sharq durdonasi"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def uri(path: str) -> str:
    with open(path, "rb") as handle:
        return "data:image/jpeg;base64," + base64.b64encode(handle.read()).decode()


COVER = ('<section class="slide dark"><div class="body"><h1 class="title big">Samarqand — Sharq durdonasi</h1>'
         '<div class="rule"></div><p class="lead">Buyuk Ipak yo\'lidagi 2750 yillik shahar: me\'morchilik, '
         'ilm-fan va savdo markazi.</p></div></section>')
CARDS = ('<section class="slide"><div class="head"><h2 class="title">Samarqand nimasi bilan mashhur</h2>'
         '<div class="rule"></div></div><div class="body">'
         '<p class="lead">Shahar uch asosiy boyligi bilan butun dunyoga tanilgan.</p>'
         '<div class="cols cols-3">'
         '<div class="card line"><div class="ikon-dot"><img class="ikon" data-icon="architecture" alt=""></div>'
         '<div class="card-title">Me\'morchilik</div><div class="card-note">Registon, Go\'ri Amir va Bibixonim — '
         'temuriylar davrining durdonalari.</div></div>'
         '<div class="card line"><div class="ikon-dot"><img class="ikon" data-icon="science" alt=""></div>'
         '<div class="card-title">Ilm-fan</div><div class="card-note">Ulug\'bek rasadxonasida 1018 yulduz '
         'jadvali tuzilgan.</div></div>'
         '<div class="card line"><div class="ikon-dot"><img class="ikon" data-icon="trade" alt=""></div>'
         '<div class="card-title">Savdo</div><div class="card-note">Ipak yo\'li chorrahasida Sharq va G\'arb '
         'karvonlari uchrashgan.</div></div>'
         '</div><div class="list">'
         '<div class="item"><span class="item-dot"></span><div class="item-text"><b>UNESCO.</b> 2001-yildan shahar '
         'markazi Butunjahon merosi ro\'yxatida.</div></div>'
         '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Turizm.</b> Har yili shaharga '
         'millionlab sayyoh keladi.</div></div>'
         '</div></div></section>')
KPI = ('<section class="slide"><div class="head"><h2 class="title">Raqamlarda Samarqand</h2><div class="rule"></div>'
       '</div><div class="body"><p class="lead">Shahar tarixi va bugungi kuni — uchta raqamda.</p>'
       '<div class="cols cols-3">'
       '<div class="kpi"><div class="kpi-value">2750</div><div class="kpi-label">yillik tarix</div>'
       '<div class="kpi-note">2007-yilda shaharning 2750 yilligi nishonlangan.</div></div>'
       '<div class="kpi"><div class="kpi-value">1018</div><div class="kpi-label">yulduz jadvali</div>'
       '<div class="kpi-note">Ulug\'bek «Ziji»dagi yulduzlar soni.</div></div>'
       '<div class="kpi"><div class="kpi-value">2001</div><div class="kpi-label">UNESCO ro\'yxati</div>'
       '<div class="kpi-note">Shahar markazi Butunjahon merosi deb tan olingan yil.</div></div>'
       '</div></div></section>')


# Infografik (kam matnli) sahifalar AI tomonidan boshqa ko'rinishda — kompozitsiyalar bilan yoziladi (`deck_compose`).
K_STEPS = ('<section class="slide k k-bosqichlar"><div class="k-text"><h2 class="title">Samarqand tarixi to\'rt '
           'bosqichda</h2><p class="lead">2750 yil davomida shahar to\'rt marta yangidan gullagan.</p><div class="k-row">'
           '<div class="k-step"><p class="k-n">01</p><p class="k-h">Afrosiyob</p><p class="k-d">Mil. av. VIII asr — '
           'shahar poydevori</p></div>'
           '<div class="k-step"><p class="k-n">02</p><p class="k-h">Ipak yo\'li</p><p class="k-d">Sharq va G\'arb '
           'savdo markazi</p></div>'
           '<div class="k-step"><p class="k-n">03</p><p class="k-h">Temuriylar</p><p class="k-d">XIV–XV asr — poytaxt '
           'va ilm markazi</p></div>'
           '<div class="k-step"><p class="k-n">04</p><p class="k-h">Bugun</p><p class="k-d">UNESCO merosi va sayyohlik '
           'markazi</p></div></div></div></section>')
K_KPI = ('<section class="slide k k-raqamlar"><div class="k-text"><h2 class="title">Raqamlarda Samarqand</h2>'
         '<div class="k-row">'
         '<div class="k-kpi"><div class="k-num"><p class="k-v">2750</p><p class="k-u">yil</p></div>'
         '<p class="k-l">Tarix</p><p class="k-d">Shaharning yoshi</p></div>'
         '<div class="k-kpi"><div class="k-num"><p class="k-v">1018</p><p class="k-u">yulduz</p></div>'
         '<p class="k-l">Ulug\'bek «Ziji»</p><p class="k-d">Jadvaldagi yulduzlar</p></div>'
         '<div class="k-kpi"><div class="k-num"><p class="k-v">2001</p><p class="k-u">yil</p></div>'
         '<p class="k-l">UNESCO</p><p class="k-d">Butunjahon merosi</p></div>'
         '</div></div></section>')


def html_pages(bodies, style: str, volume: str, photos: dict):
    from services.premium_presentation import html_images, html_slides, themes

    theme = themes.for_deck(TOPIC, style, volume)
    pages = html_slides.build_pages(list(bodies), theme, "uz")
    pages, _ = html_images.apply_icons(pages, theme)
    for index, page in enumerate(pages):
        if "slide dark" in page and index == 0:
            pages[index] = html_images.with_cover_photo(page, uri(photos["registon"]), "50% 60%")
    if volume != "kam":
        pages = html_images.add_backdrops(pages)
    return pages, theme


def shoot(pages, out_dir):
    """Botdagi yakuniy ko'rinish: render() varaqni sig'diradi (`fit`) va har slayd suratini saqlaydi."""
    from services.premium_presentation import html_render

    os.makedirs(out_dir, exist_ok=True)
    html_render.render(pages, out_dir=out_dir, shots_dir=out_dir)
    return sorted(os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.startswith("shot_"))


def pptx_images(path: str, out_dir: str):
    """PPTX → PNG (LibreOffice orqali PDF, keyin pdftoppm)."""
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, path],
                   check=True, capture_output=True, timeout=300)
    pdf = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
    subprocess.run(["pdftoppm", "-png", "-r", "110", pdf, os.path.join(out_dir, "p")], check=True, timeout=300)
    return sorted(os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.startswith("p") and f.endswith(".png"))


def native_deck(pages, theme, out_dir: str) -> str:
    """Infografik: sahifalar vektor dizayner bilan PowerPoint shakllari qilib chiziladi (botdagidek)."""
    from services.premium_presentation import html_render
    from services.premium_presentation.designer import Designer

    designer = Designer(theme, TOPIC, seed=7, pages=pages)
    try:
        return html_render.render(pages, out_dir=out_dir, native=designer.draw)
    finally:
        designer.close()


def grid(tiles, columns: int, out: str, tile_w: int = 640, label_h: int = 56, gap: int = 14):
    """[(rasm yo'li, yozuv)] → bitta rasm (3D Anatomiya uslublari rasmi bilan bir xil ko'rinish)."""
    rows = (len(tiles) + columns - 1) // columns
    tile_h = tile_w * 9 // 16
    width = columns * tile_w + (columns + 1) * gap
    height = rows * (tile_h + label_h) + (rows + 1) * gap
    sheet = Image.new("RGB", (width, height), (17, 20, 27))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(FONT, 26)
    last_row = len(tiles) - (rows - 1) * columns
    for index, (path, label) in enumerate(tiles):
        row, col = divmod(index, columns)
        offset = (columns - last_row) * (tile_w + gap) // 2 if row == rows - 1 else 0
        x = gap + col * (tile_w + gap) + offset
        y = gap + row * (tile_h + label_h + gap)
        image = Image.open(path).convert("RGB").resize((tile_w, tile_h), Image.LANCZOS)
        sheet.paste(image, (x, y))
        draw.text((x + 8, y + tile_h + 12), label, font=font, fill=(240, 242, 247))
    sheet.save(out, quality=88, optimize=True)
    print("✓", out, sheet.size)


def main():
    photos_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    photos = {"registon": os.path.join(photos_dir, "registon.jpg")}
    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp(prefix="namuna_")
    try:
        build(photos, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def classic_deck(photos, out_dir: str) -> str:
    """Klassik: oddiy taqdimot oqimi (tayyor fon shabloni + slayd kompozitsiyalari), rasm o'rnida foto."""
    from services.document_service import DocumentService
    from services.template_service import TemplateService

    class Photos:                      # AI rasm o'rniga tayyor foto (namuna oflayn yasalsin)
        async def _image(self, *args, **kwargs):
            path = os.path.join(out_dir, f"foto_{len(os.listdir(out_dir))}.jpg")
            shutil.copy(photos["registon"], path)
            return path
        generate_cover_image = generate_slide_image = generate_panoramic_image = _image

    service = DocumentService.__new__(DocumentService)
    service.documents_dir, service.together = out_dir, Photos()
    service.use_icons, service._last_used_icons = True, set()
    slides = [{"title": "Samarqand — Sharq durdonasi", "layout": "cover", "content": ""},
              {"title": "Samarqand nimasi bilan mashhur", "layout": "", "items": [
                  {"head": "Me'morchilik", "text": "Registon, Go'ri Amir va Bibixonim — temuriylar davrining "
                   "durdonalari. Ularning moviy gumbazlari shaharning ramziga aylangan.", "value": ""},
                  {"head": "Ilm-fan", "text": "Ulug'bek rasadxonasida 1018 yulduz jadvali tuzilgan. Bu asar "
                   "Yevropada ham yuz yillar davomida o'rganilgan.", "value": ""},
                  {"head": "Savdo", "text": "Ipak yo'li chorrahasida Sharq va G'arb karvonlari uchrashgan. Shahar "
                   "bozorlari butun Osiyoga mashhur bo'lgan.", "value": ""}]},
              {"title": "Xulosa", "layout": "conclusion", "content": "Samarqand — ilm va me'morchilik shahri."}]
    return asyncio.run(service.create_presentation_with_smart_images(
        TOPIC, {"slides": slides}, "Talaba", "uz", TemplateService(), "template_7"))


def kat3d_slide(style: str, out_dir: str) -> str:
    """3D taqdimot Pro: bitta uslubdagi slayd (sarlavha, matn va haqiqiy 3D model)."""
    from services import katalog3d
    from services.kat3d import deck, reja

    ids = list(KAT3D_MODELS)
    codes = {f"m{i}": mid for i, mid in enumerate(ids)}
    raw = {"slides": [
        {"layout": "muqova", "kicker": "Tarix", "title": TOPIC, "subtitle": "Buyuk Ipak yo'lidagi 2750 yillik shahar",
         "models": ["m0"]},
        {"layout": "chap", "kicker": "Me'morchilik", "title": "Go'ri Amir maqbarasi",
         "points": ["Amir Temur va temuriylar maqbarasi, 1404-yil", "Moviy qovurg'ali gumbazi — 12,5 m",
                    "Ichki bezaklarida oltin va lojuvard"], "models": ["m1"]},
        {"layout": "yakun", "kicker": "Xulosa", "title": "Ilm va me'morchilik shahri",
         "points": ["Registon, Go'ri Amir va rasadxona — UNESCO merosi"], "models": ["m0", "m1", "m2"]}]}
    plan = reja.normalize(raw, 3, ids, codes)
    plan.update(style=style, topic="Samarqand", language="uz")
    os.makedirs(out_dir, exist_ok=True)
    images = pptx_images(deck.build(plan, os.path.join(out_dir, f"{style}.pptx")), out_dir)
    return images[1]


# Registon maydoni, Go'ri Amir maqbarasi, Ulug'bek rasadxonasi sekstanti (katalogdagi o'zbek yodgorliklari).
KAT3D_MODELS = ("af54f5280eb249beb6501eab4769c351", "fd795227e0bc4f61bc1e4e453d29a74b",
                "20775c69c259465eb15c1463cd20564a")


def columns(cols, out: str, tile_w: int = 640, head_h: int = 60, gap: int = 14):
    """Har ustun — bitta tur: tepada nomi, ostida shu turning slaydlari."""
    tile_h = tile_w * 9 // 16
    rows = max(len(images) for _, images in cols)
    width = len(cols) * tile_w + (len(cols) + 1) * gap
    height = head_h + rows * (tile_h + gap) + gap
    sheet = Image.new("RGB", (width, height), (17, 20, 27))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(FONT, 28)
    for col, (label, images) in enumerate(cols):
        x = gap + col * (tile_w + gap)
        draw.text((x + 4, 14), label, font=font, fill=(240, 242, 247))
        for row, path in enumerate(images):
            image = Image.open(path).convert("RGB").resize((tile_w, tile_h), Image.LANCZOS)
            sheet.paste(image, (x, head_h + row * (tile_h + gap)))
    sheet.save(out, quality=88, optimize=True)
    print("✓", out, sheet.size)


def build(photos, work):
    from bot.handlers import premium_presentation as pp

    # 1) Zamonaviy: 5 uslub, bir xil mazmun — farq faqat dizaynda. Raqamlar uslub tugmalari tartibida.
    tiles = []
    for number, key in enumerate([k for k in pp._STYLE_ORDER if k != pp.SIMPLE_STYLE], 1):
        pages, _ = html_pages([CARDS], key, "kop", photos)
        tiles.append((shoot(pages, os.path.join(work, key))[0], f"{number}. {pp._style_name(key, 'uz')}"))
    grid(tiles, 3, os.path.join(OUT, "uslublar.jpg"))

    # 2) Taqdimot turlari: har biri o'z oqimi bilan (Infografik — vektor dizayner, Klassik — fon shabloni).
    info_dir, modern_dir, classic_dir = (os.path.join(work, name) for name in ("info", "modern", "classic"))
    for folder in (info_dir, modern_dir, classic_dir):
        os.makedirs(folder, exist_ok=True)
    pages, theme = html_pages([COVER, K_STEPS], "", "kam", photos)
    info = pptx_images(native_deck(pages, theme, info_dir), info_dir)
    pages, _ = html_pages([COVER, CARDS], "toza", "kop", photos)
    modern = shoot(pages, modern_dir)
    classic = pptx_images(classic_deck(photos, classic_dir), classic_dir)
    columns([("1. Infografik", info[:2]), ("2. Zamonaviy", modern[:2]), ("3. Klassik", classic[:2])],
            os.path.join(OUT, "turlar.jpg"))

    # 3) 3D taqdimot Pro: 11 uslub (mijoz tanlamaydi — fanga qarab tizim tanlaydi; «Narxlar» da ko'rsatiladi).
    from services import katalog3d
    from services.kat3d import uslub, yukla

    missing = [mid for mid in KAT3D_MODELS if not katalog3d.model_yoli(mid)]
    if missing:
        yukla.ensure(missing)
    if any(not katalog3d.model_yoli(mid) for mid in KAT3D_MODELS):
        print("✗ 3D modellar topilmadi — uslublar_3d.jpg yasalmadi (KATALOG3D_DIR ni tekshiring)")
        return
    tiles = [(kat3d_slide(key, os.path.join(work, "3d", key)), style.uz) for key, style in uslub.STYLES.items()]
    grid(tiles, 4, os.path.join(OUT, "uslublar_3d.jpg"), tile_w=480, label_h=48)


if __name__ == "__main__":
    main()
