"""«Taqdimot turini tanlang» rasmi (`assets/taqdimot/turlar.jpg`): har tur uchun 10 tadan, jami 30 ta slayd.

Slaydlar haqiqiy chizish kodidan olinadi (yasa.py bilan bir xil) va bitta rasmga sig'diriladi: 3 ustun
(Infografik / Zamonaviy / Klassik), har ustunda 10 slayd (2×5). Rasm o'lchami avvalgidek (1976×822), slaydlar mayda.
Suratlar — foydalanuvchi bergan joylar fotosi (Registon emas): Go'ri Amir, Sherdor, Chor-Minor, Xiva, Samarqand vokzali.

    python tools/taqdimot_namuna/turlar.py <fotolar_papkasi>

Fotolar papkasida: `gur_emir.jpg`, `sherdor.jpg`, `chor_minor.jpg`, `xiva.jpg`, `vokzal.jpg`.
Kerak: Playwright (Chromium), LibreOffice (`soffice`), `pdftoppm`.
"""
import asyncio
import itertools
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import yasa  # noqa: E402  (ROOT ga o'tadi, BOT_TOKEN qo'yadi)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

OUT = os.path.join(yasa.ROOT, "assets", "taqdimot", "turlar.jpg")
SIZE = (1976, 822)                       # avvalgi rasm bilan bir xil o'lcham
PHOTO_ORDER = ("gur_emir", "sherdor", "xiva", "chor_minor", "vokzal")
BG = (17, 20, 27)

# ───────────────────────────────────────────── Zamonaviy / Infografik uchun mazmun (Samarqand)

PAR = ('<section class="slide"><div class="head"><h2 class="title">Registon: uch madrasa maydoni</h2>'
       '<div class="rule"></div></div><div class="body"><p class="lead">Samarqandning yuragi — Ulug\'bek, Sherdor va '
       'Tillakori madrasalari.</p><div class="split"><div class="par-col">'
       '<p class="par">Maydon XV–XVII asrlarda shakllangan: uch madrasa bir-biriga qarama-qarshi turadi va yagona '
       'me\'moriy ansambl hosil qiladi.</p>'
       '<p class="par">Ularning peshtoqlari moviy koshin va naqshlar bilan bezatilgan; shuning uchun maydon Sharq '
       'me\'morchiligining timsoliga aylangan.</p></div>'
       '<div class="rasm" data-prompt="sherdor madrasa"><p class="rasm-matn">Registon maydoni.</p></div></div></div>'
       '</section>')
STEPS = ('<section class="slide"><div class="head"><h2 class="title">Ipak yo\'li bo\'ylab sayohat</h2>'
         '<div class="rule"></div></div><div class="body"><p class="lead">Karvonlar Samarqandga to\'rt bosqichda '
         'yetib kelgan.</p><div class="steps">'
         '<div class="card"><div class="card-title">1-qadam</div><div class="card-note">Xitoydan chiqish.</div></div>'
         '<div class="arrow">&#8594;</div>'
         '<div class="card"><div class="card-title">2-qadam</div><div class="card-note">Farg\'ona vodiysi.</div></div>'
         '<div class="arrow">&#8594;</div>'
         '<div class="card"><div class="card-title">3-qadam</div><div class="card-note">Samarqand bozori.</div></div>'
         '<div class="arrow">&#8594;</div>'
         '<div class="card"><div class="card-title">4-qadam</div><div class="card-note">G\'arbga yo\'l.</div></div>'
         '</div></div></section>')
TIMELINE = ('<section class="slide"><div class="head"><h2 class="title">Samarqand tarixidan lavhalar</h2>'
            '<div class="rule"></div></div><div class="body"><p class="lead">Shahar 2750 yildan ortiq tarixga ega.</p>'
            '<div class="timeline">'
            '<div class="stop"><span class="bead"></span><div class="when">VIII asr m.a.</div>'
            '<div class="what">Afrosiyob shahri.</div></div>'
            '<div class="stop"><span class="bead"></span><div class="when">1370</div>'
            '<div class="what">Amir Temur poytaxti.</div></div>'
            '<div class="stop"><span class="bead"></span><div class="when">1420</div>'
            '<div class="what">Ulug\'bek rasadxonasi.</div></div>'
            '<div class="stop"><span class="bead"></span><div class="when">2001</div>'
            '<div class="what">UNESCO ro\'yxati.</div></div></div></div></section>')
COMPARE = ('<section class="slide"><div class="head"><h2 class="title">Qadimgi va zamonaviy Samarqand</h2>'
           '<div class="rule"></div></div><div class="body"><p class="lead">Shahar o\'tmish merosini bugun bilan '
           'uyg\'unlashtiradi.</p><div class="cols cols-2">'
           '<div class="card"><div class="card-title">Qadimgi shahar</div><div class="list">'
           '<div class="item"><span class="item-dot"></span><div class="item-text">Registon va Shohizinda.</div></div>'
           '<div class="item"><span class="item-dot"></span><div class="item-text">Karvon bozorlari.</div></div></div>'
           '</div><div class="card solid"><div class="card-title">Bugungi shahar</div><div class="list">'
           '<div class="item"><span class="item-dot"></span><div class="item-text">Tezyurar poyezd.</div></div>'
           '<div class="item"><span class="item-dot"></span><div class="item-text">Zamonaviy mehmonxonalar.</div>'
           '</div></div></div></div></div></section>')
QUOTE = ('<section class="slide"><div class="head"><h2 class="title">Sharq va G\'arb uchrashgan joy</h2>'
         '<div class="rule"></div></div><div class="body"><div><div class="quote-mark">&#8220;</div>'
         '<p class="quote">Samarqand — yer yuzining sayqali.</p><p class="quote-by">— Sharq maqoli</p></div></div>'
         '</section>')
LIST_PHOTO = ('<section class="slide"><div class="head"><h2 class="title">Samarqandga qanday borish mumkin</h2>'
              '<div class="rule"></div></div><div class="body"><div class="split wide-left"><div class="list">'
              '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Poyezd.</b> Toshkentdan '
              '2 soatda.</div></div>'
              '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Avtobus.</b> Har kuni '
              'qatnovlar bor.</div></div>'
              '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Samolyot.</b> Xalqaro '
              'aeroport.</div></div></div>'
              '<div class="rasm" data-prompt="samarkand railway station"><p class="rasm-matn">Vokzal.</p></div>'
              '</div></div></section>')
CONCLUSION = ('<section class="slide"><div class="head"><h2 class="title">Xulosa</h2><div class="rule"></div></div>'
              '<div class="body"><p class="lead">Samarqand — ilm, savdo va me\'morchilik shahri; uni ko\'rgan odam '
              'unutmaydi.</p><div class="list">'
              '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Tarix.</b> 2750 yillik '
              'meros.</div></div>'
              '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Bugun.</b> Zamonaviy '
              'turizm markazi.</div></div></div></div></section>')

MODERN = [yasa.COVER, PAR, yasa.CARDS, yasa.KPI, STEPS, TIMELINE, COMPARE, QUOTE, LIST_PHOTO, CONCLUSION]

I_RASM_CHAP = ('<section class="slide k k-rasm-chap"><div class="rasm" data-prompt="gur emir"><p class="rasm-matn">'
               'Go\'ri Amir.</p></div><div class="k-text"><h2 class="title">Go\'ri Amir maqbarasi</h2>'
               '<p class="lead">Amir Temur va temuriylar oilasi dafn etilgan.</p>'
               '<p class="k-p">Moviy gumbaz va naqshli peshtoq — Markaziy Osiyo me\'morchiligining ramzi.</p></div></section>')
I_RASM_ONG = ('<section class="slide k k-rasm-ong"><div class="k-text"><h2 class="title">Sherdor madrasasi</h2>'
              '<p class="k-p">Peshtoqdagi sher va quyosh tasviri maydonning eng mashhur bezagi.</p></div>'
              '<div class="rasm" data-prompt="sherdor"><p class="rasm-matn">Sherdor.</p></div></section>')
I_RASM_TEPA = ('<section class="slide k k-rasm-tepa"><div class="rasm" data-prompt="wide samarkand"><p class="rasm-matn">'
               'Samarqand.</p></div><div class="k-text"><h2 class="title">Shahar manzarasi</h2>'
               '<p class="k-p">Qadimiy gumbazlar zamonaviy ko\'chalar bilan yonma-yon turadi.</p></div></section>')
I_RASM_FON = ('<section class="slide k k-rasm-fon"><div class="rasm" data-prompt="bukhara"><p class="rasm-matn">Buxoro.'
              '</p></div><div class="k-text"><h2 class="title">Chor-Minor</h2>'
              '<p class="k-p">Buxorodagi to\'rt minorali madrasa — kechqurun alohida go\'zal.</p></div></section>')
I_QUOTE = ('<section class="slide k k-iqtibos"><div class="rasm" data-prompt="khiva"><p class="rasm-matn">Xiva.</p></div>'
           '<div class="k-text"><h2 class="title">Ipak yo\'li shaharlari</h2>'
           '<p class="quote">Sharq durdonalari bir-biridan go\'zal.</p><p class="quote-by">— sayyohlar daftaridan</p>'
           '<p class="k-p">Samarqand, Buxoro va Xiva — sayohatning uch tayanchi.</p></div></section>')
I_TIMELINE = ('<section class="slide k k-vaqt"><div class="rasm" data-prompt="samarkand"><p class="rasm-matn">Tarix.</p>'
              '</div><div class="k-text"><h2 class="title">Samarqand tarixi</h2><div class="k-axis">'
              '<div class="k-stop"><p class="k-y">VIII asr m.a.</p><p class="k-yd">Afrosiyob</p></div>'
              '<div class="k-stop"><p class="k-y">1370</p><p class="k-yd">Temur poytaxti</p></div>'
              '<div class="k-stop"><p class="k-y">1420</p><p class="k-yd">Ulug\'bek rasadxonasi</p></div>'
              '<div class="k-stop"><p class="k-y">2001</p><p class="k-yd">UNESCO</p></div></div></div></section>')
I_CARDS = ('<section class="slide k k-kartalar"><div class="k-text"><h2 class="title">Nimani ko\'rish kerak</h2>'
           '<p class="lead">Birinchi sayohatda albatta ko\'riladigan joylar.</p><div class="k-row">'
           '<div class="k-card"><p class="k-h">Registon</p><p class="k-d">Uch madrasa maydoni.</p></div>'
           '<div class="k-card"><p class="k-h">Shohizinda</p><p class="k-d">Maqbaralar yo\'lagi.</p></div>'
           '<div class="k-card"><p class="k-h">Go\'ri Amir</p><p class="k-d">Temur maqbarasi.</p></div></div>'
           '</div></section>')
I_YAKUN = ('<section class="slide k k-yakun"><div class="k-text"><h2 class="title">Xulosa</h2>'
           '<p class="lead">Samarqand — tarix va bugun uchrashgan joy.</p>'
           '<p class="k-ln"><i></i><span>2750 yillik tarix.</span></p>'
           '<p class="k-ln"><i></i><span>Ipak yo\'lining markazi.</span></p>'
           '<p class="k-ln"><i></i><span>Butunjahon merosi.</span></p></div></section>')

INFO = [yasa.COVER, I_RASM_CHAP, yasa.K_STEPS, I_RASM_ONG, yasa.K_KPI, I_RASM_TEPA, I_QUOTE, I_TIMELINE, I_CARDS,
        I_YAKUN]

# Klassik: tayyor fon shabloni; har slayd o'z joylashuvida (kit — native shakllar)
CLASSIC = [
    {"title": "Samarqand — Sharq durdonasi", "layout": "cover", "content": ""},
    {"title": "Samarqand tarixi bosqichlari", "layout": "numbered_list", "items": [
        {"head": "", "text": "Afrosiyob — mil. avv. VIII asrdagi qadimgi shahar.", "value": ""},
        {"head": "", "text": "Ipak yo'li chorrahasida savdo markaziga aylangan.", "value": ""},
        {"head": "", "text": "Temur davrida buyuk saltanat poytaxti bo'lgan.", "value": ""},
        {"head": "", "text": "Ulug'bek davrida ilm-fan markaziga aylangan.", "value": ""}]},
    {"title": "Samarqand nimasi bilan mashhur", "layout": "three_column", "items": [
        {"head": "Me'morchilik", "text": "Registon va Go'ri Amir — temuriylar davrining durdonalari.", "value": ""},
        {"head": "Ilm-fan", "text": "Ulug'bek rasadxonasida 1018 yulduz jadvali tuzilgan.", "value": ""},
        {"head": "Savdo", "text": "Ipak yo'li chorrahasida karvonlar uchrashgan.", "value": ""}]},
    {"title": "Registon maydoni", "layout": "right_image", "content":
        "Uch madrasa maydoni XV–XVII asrlarda shakllangan. Moviy koshinli peshtoqlar uni Sharq me'morchiligining "
        "timsoliga aylantirgan."},
    {"title": "Go'ri Amir maqbarasi", "layout": "image_left_bullets", "items": [
        {"head": "", "text": "Amir Temur va temuriylar oilasi dafn etilgan.", "value": ""},
        {"head": "", "text": "Moviy gumbaz shahar ramzlaridan biri.", "value": ""},
        {"head": "", "text": "Ichki bezaklari oltin suvi bilan ishlangan.", "value": ""}]},
    {"title": "Samarqand tarixi", "layout": "timeline", "items": [
        {"head": "VIII asr m.a.", "text": "Afrosiyob shahri", "value": ""},
        {"head": "1370", "text": "Amir Temur poytaxti", "value": ""},
        {"head": "1420", "text": "Ulug'bek rasadxonasi", "value": ""},
        {"head": "2001", "text": "UNESCO ro'yxati", "value": ""}]},
    {"title": "Raqamlarda Samarqand", "layout": "stats_row", "items": [
        {"head": "yillik tarix", "text": "2750 yillik tarix", "value": "2750"},
        {"head": "yulduz jadvali", "text": "1018 ta yulduz jadvali", "value": "1018"},
        {"head": "UNESCO ro'yxati", "text": "2001-yildan UNESCO ro'yxatida", "value": "2001"}]},
    {"title": "Qadimgi va zamonaviy shahar", "layout": "comparison", "items": [
        {"head": "Qadimgi shahar", "text": "Registon, Shohizinda va karvon bozorlari.", "value": ""},
        {"head": "Bugungi shahar", "text": "Tezyurar poyezd va zamonaviy mehmonxonalar.", "value": ""}]},
    {"title": "Nimani ko'rish kerak", "layout": "image_top_columns", "items": [
        {"head": "Registon", "text": "Uch madrasa maydoni.", "value": ""},
        {"head": "Shohizinda", "text": "Maqbaralar yo'lagi.", "value": ""},
        {"head": "Go'ri Amir", "text": "Temur maqbarasi.", "value": ""}]},
    {"title": "Xulosa", "layout": "conclusion", "content": "Samarqand — ilm va me'morchilik shahri."},
]


# ───────────────────────────────────────────── chizish

def photo_generator(photos_dir: str, work: str):
    """`fill_photos` uchun: har chaqiriqda keyingi foto (nusxasi — u o'qilgach o'chiriladi)."""
    cycle = itertools.cycle(PHOTO_ORDER)
    counter = itertools.count()
    by_word = (("railway", "vokzal"), ("sherdor", "sherdor"), ("gur", "gur_emir"), ("bukhara", "chor_minor"),
               ("khiva", "xiva"), ("wide", "xiva"))        # tavsifdagi so'z → mos foto (qolganlari ketma-ket)

    async def generate(prompt):
        name = next((photo for word, photo in by_word if word in (prompt or "").lower()), None) or next(cycle)
        path = os.path.join(work, f"foto_{next(counter)}.jpg")
        shutil.copy(os.path.join(photos_dir, name + ".jpg"), path)
        return path
    return generate


def with_photos(pages, photos_dir: str, work: str):
    from services.premium_presentation import html_images

    pages, placed = asyncio.run(html_images.fill_photos(list(pages), 20, generate=photo_generator(photos_dir, work)))
    print("  rasm qo'yildi:", placed)
    return pages


def build_modern(photos, photos_dir: str, work: str):
    pages, _ = yasa.html_pages(MODERN, "toza", "kop", photos)
    pages = with_photos(pages, photos_dir, work)
    return yasa.shoot(pages, os.path.join(work, "modern"))


def build_info(photos, photos_dir: str, work: str):
    pages, theme = yasa.html_pages(INFO, "", "kam", photos)
    pages = with_photos(pages, photos_dir, work)
    folder = os.path.join(work, "info")
    os.makedirs(folder, exist_ok=True)
    return yasa.pptx_images(yasa.native_deck(pages, theme, folder), folder)


def build_classic(photos_dir: str, work: str):
    from services.document_service import DocumentService
    from services.template_service import TemplateService

    folder = os.path.join(work, "classic")
    os.makedirs(folder, exist_ok=True)
    cycle = itertools.cycle(PHOTO_ORDER)

    class Photos:                      # AI rasm o'rniga tayyor foto (namuna oflayn yasalsin)
        async def _image(self, *args, **kwargs):
            path = os.path.join(folder, f"foto_{len(os.listdir(folder))}.jpg")
            shutil.copy(os.path.join(photos_dir, next(cycle) + ".jpg"), path)
            return path
        generate_cover_image = generate_slide_image = generate_panoramic_image = _image

    service = DocumentService.__new__(DocumentService)
    service.documents_dir, service.together = folder, Photos()
    service.use_icons, service._last_used_icons = True, set()
    path = asyncio.run(service.create_presentation_with_smart_images(
        yasa.TOPIC, {"slides": CLASSIC}, "Talaba", "uz", TemplateService(), "template_7"))
    return yasa.pptx_images(path, folder)


def compose(columns, out: str):
    """3 ustun, har birida 10 slayd (2×5); rasm o'lchami — SIZE."""
    width, height = SIZE
    sheet = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(yasa.FONT, 22)
    head_h, gap, group_gap, rows, sub = 46, 6, 36, 5, 2
    tile_h = (height - head_h - gap * (rows + 1)) // rows
    tile_w = tile_h * 16 // 9
    group_w = sub * tile_w + (sub - 1) * gap
    total = len(columns) * group_w + (len(columns) - 1) * group_gap
    x0 = (width - total) // 2
    for c, (label, images) in enumerate(columns):
        gx = x0 + c * (group_w + group_gap)
        draw.text((gx, 12), label, font=font, fill=(240, 242, 247))
        for i, path in enumerate(images[:rows * sub]):
            r, s = divmod(i, sub)
            tile = Image.open(path).convert("RGB").resize((tile_w, tile_h), Image.LANCZOS)
            sheet.paste(tile, (gx + s * (tile_w + gap), head_h + gap + r * (tile_h + gap)))
    sheet.save(out, quality=90, optimize=True)
    print("✓", out, sheet.size, f"{os.path.getsize(out) // 1024} KB, slayd {tile_w}×{tile_h}")


def main():
    photos_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    photos = {"registon": os.path.join(photos_dir, "gur_emir.jpg")}          # muqova fotosi
    work = tempfile.mkdtemp(prefix="turlar_")
    try:
        print("Zamonaviy…")
        modern = build_modern(photos, photos_dir, work)
        print("Infografik…")
        info = build_info(photos, photos_dir, work)
        print("Klassik…")
        classic = build_classic(photos_dir, work)
        print("slaydlar:", len(info), len(modern), len(classic))
        compose([("1. Infografik", info), ("2. Zamonaviy", modern), ("3. Klassik", classic)], OUT)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
