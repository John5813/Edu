"""Brave rasm qidiruvi va «🧠 AI nazorati».

- mavzuga Brave'ga faqat BITTA so'rov: muqova, slaydlar va qayta yaratish xotiradan oladi;
- stok saytlar, do'konlar va kichik rasmlar tashlab ketiladi;
- AI tanlovi takrorsiz; bitta rasm ikki slaydga tushmaydi;
- topilmagan slaydga AI chizadi, topilganiga chizilmaydi;
- kunlik hisob: saytdan / AI dan rasmlar va modellar ulushi foizda.

    python test_brave_rasm.py
"""
import asyncio
import os
import sys
import tempfile
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import database.database as dbmod

# Testlarda vizual tekshiruv (AI) o'tkazuvchi — maxsus `check=` bilan beriladiganlar bundan mustasno.
from services import photo_search as _ps_default
_REAL_TEXT_CHECK = _ps_default._ask_text_check
_ps_default._ask_text_check = lambda paths, formulas=False: set()

_db_dir = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(_db_dir, "test.db")

from PIL import Image

from services import ai_usage, photo_search
from services.premium_presentation import html_images


_IMAGE_SEED = [0]


def _image(width=900, height=600, seed=None):
    """Har chaqiruvda boshqa surat (haqiqiy fotolar kabi bir-biridan farq qiladi); `seed` — aynan o'sha surat."""
    import random as _random
    from PIL import ImageDraw as _Draw

    if seed is None:
        _IMAGE_SEED[0] += 1
        seed = _IMAGE_SEED[0]
    rng = _random.Random(seed)
    handle, path = tempfile.mkstemp(suffix=".jpg")
    os.close(handle)
    picture = Image.new("RGB", (900, 600), (90, 140, 60))
    draw = _Draw.Draw(picture)
    for _ in range(14):
        x, y = rng.randrange(0, 820), rng.randrange(0, 520)
        draw.rectangle((x, y, x + rng.randrange(60, 300), y + rng.randrange(60, 260)),
                       fill=tuple(rng.randrange(0, 256) for _ in range(3)))
    picture.resize((width, height)).save(path)
    return path


def _result(i, source="example.org", width=1200, height=800, title=None):
    return {"title": title or f"photo {i}", "source": source, "url": f"https://{source}/page{i}",
            "properties": {"url": f"https://{source}/img{i}.jpg", "width": width, "height": height}}


print("1) Natijalarni saralash")
raw = [
    _result(0),
    _result(1, source="gettyimages.com"),
    _result(2, source="www.shutterstock.com"),
    _result(3, source="amazon.com"),
    _result(4, width=400, height=300),
    _result(5, width=3000, height=500),          # juda uzun panorama
    _result(0),                                   # takror
    {"title": "svg", "source": "x.org", "properties": {"url": "https://x.org/a.svg", "width": 900, "height": 600}},
    _result(6, source="upload.wikimedia.org"),
]
kept = photo_search.usable(raw)
check("faqat yaroqlilari qoldi (oddiy sayt va Wikimedia)",
      [c["url"] for c in kept] == ["https://example.org/img0.jpg", "https://upload.wikimedia.org/img6.jpg"],
      [c["url"] for c in kept])

print("\n2) AI javobini o'qish")
picks = photo_search.parse_picks({"picks": [
    {"slot": 1, "ids": [3, 3, 7, 8, 9]},
    {"slot": 2, "ids": [7, 2, "x", 99]},
    {"slot": 9, "ids": [1]},
    "buzuq",
]}, slots=3, candidates=10)
check("har slotga eng ko'pi 3 ta, takrorsiz, chegaradan tashqarisi yo'q",
      picks == [[3, 7, 8], [2], []], picks)

print("\n2b) Mavzuga mos qidiruv tili va fokusli qirqish")
original_ask_json = photo_search._ask_json
try:
    photo_search._ask_json = lambda system, user, max_tokens: {
        "query": "阿米尔·帖木儿 撒马尔罕", "search_lang": "zh-hans"}
    query, search_lang = asyncio.run(photo_search.search_plan("Amir Temur"))
    check("madaniy mavzu uchun mahalliy tildagi so'rov va Brave tili tanlanadi",
          query == "阿米尔·帖木儿 撒马尔罕" and search_lang == "zh-hans", (query, search_lang))
    photo_search._ask_json = lambda system, user, max_tokens: {
        "query": "Amir Temur tarixiy suratlari", "search_lang": "uz"}
    query, search_lang = asyncio.run(photo_search.search_plan("Amir Temur"))
    check("Brave qo'llamaydigan o'zbek tili filtri yuborilmaydi, lekin mahalliy so'rov saqlanadi",
          query == "Amir Temur tarixiy suratlari" and not search_lang, (query, search_lang))
finally:
    photo_search._ask_json = original_ask_json
check("qidiruv yo'riqnomasi mavhum texnologiya va madaniy mavzularni farqlaydi",
      "Amir Temur: Uzbek" in photo_search._QUERY_SYSTEM and "AI, internet" in photo_search._QUERY_SYSTEM)
check("mavhum va futuristik mavzularda AI birinchi tanlanadi",
      all(photo_search.prefer_ai(topic) for topic in (
          "Sun'iy intellekt", "internet xavfsizligi", "Kosmos", "Virtual reality",
          "Internetni o'rganish", "Kosmosni o'rganish"))
      and not photo_search.prefer_ai("Amir Temur tarixi"))

request_params = []


class _Response:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self, content_type=None):
        return {"results": []}


class _Session:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url, params, headers):
        request_params.append(dict(params))
        return _Response()


with patch.object(photo_search.aiohttp, "ClientSession", _Session):
    from services import brave_keys

    with patch.object(brave_keys, "take", lambda: "test-key"):
        asyncio.run(photo_search._brave("Amir Temur", "zh-hans"))
        asyncio.run(photo_search._brave("Amir Temur", "uz"))
check("Brave'ga qo'llanadigan til filtri yuboriladi, qo'llanmaydigani o'tkaziladi",
      request_params[0].get("search_lang") == "zh-hans" and "search_lang" not in request_params[1],
      request_params)

left, right, top, bottom = photo_search.crop_margins(1600, 900, 0.78, 1.0, 0.25, 0.45)
kept_width = 1 - left - right
visible_face_x = (0.25 - left) / kept_width
check("keng suratdagi chap yuz qirqilganda ham kadr markaziga yaqin qoladi",
      left < right and abs(visible_face_x - 0.5) < 0.02, (left, right, visible_face_x))
check("mos nisbatli rasm keraksiz qirqilmaydi",
      photo_search.crop_margins(780, 1000, 0.78, 1.0) == (0.0, 0.0, 0.0, 0.0))
focus_sample = _image(1600, 900)
try:
    with patch.object(photo_search, "focal_point", lambda path, default_y=0.4: (0.25, 0.45)):
        focused_position = html_images._photo_position(focus_sample, 0.78)
finally:
    os.remove(focus_sample)
check("HTML crop pozitsiyasi aniqlangan chap yuzni markazga olib keladi",
      focused_position == "5.5% 50.0%", focused_position)

print("\n3) Mavzuga bitta Brave so'rovi")
photo_search.reset()
calls = []


async def search(query):
    calls.append(query)
    return [_result(i, title=f"heart anatomy photo {i}") for i in range(10)]


async def choose_first(system, user):
    # Har slotga ketma-ket nomzodlar: 1-slot → 0,1 ; 2-slot → 2,3 ...
    slots = [line for line in user.split("Search results:")[0].splitlines() if line[:1].isdigit()]
    ids = [int(line.split(".")[0]) for line in user.split("Search results:")[1].splitlines() if line[:1].isdigit()]
    return {"picks": [{"slot": n + 1, "ids": ids[n * 2:n * 2 + 2]} for n in range(len(slots))]}


downloads = []


async def fake_download(session, url):
    downloads.append(url)
    return None if url.endswith("img0.jpg") else _image()

real_download = photo_search._download
photo_search._download = fake_download
try:
    first = asyncio.run(photo_search.find_photos("Inson yuragi", ["Yurak tuzilishi", "Qon aylanishi"],
                                                 search=search, choose=choose_first))
    first_downloads = list(downloads)
    second = asyncio.run(photo_search.find_photos("  inson YURAGI ", ["Muqova"],
                                                  search=search, choose=choose_first))
finally:
    photo_search._download = real_download
check("ikkala murojaatga Brave'ga bitta so'rov", len(calls) == 1, calls)
check("1-slot: birinchi rasm yuklanmasa keyingisi olinadi", bool(first[0]) and downloads[0].endswith("img0.jpg")
      and downloads[1].endswith("img1.jpg"), downloads)
check("ikkala slotga rasm topildi", all(first), first)
check("keyingi murojaat oldin sinalgan rasmni qayta bermaydi",
      bool(second[0]) and not set(downloads[len(first_downloads):]) & set(first_downloads), downloads)
for path in first + second:
    if path:
        os.remove(path)


async def broken(query):
    calls.append(query)
    raise RuntimeError("tarmoq yo'q")

photo_search.reset(); calls.clear()
asyncio.run(photo_search.find_photos("Fotosintez", ["Barg"], search=broken, choose=choose_first))
asyncio.run(photo_search.find_photos("Fotosintez", ["Ildiz"], search=broken, choose=choose_first))
check("Brave xatosida ham mavzuga ikkinchi so'rov yuborilmaydi", len(calls) == 1, calls)


async def choose_none(system, user):
    return {"picks": [{"slot": 1, "ids": []}]}

photo_search.reset()
none = asyncio.run(photo_search.find_photos("Ko'llar", ["Orol"], search=search, choose=choose_none))
check("AI mos rasm topmasa — None (keyin AI chizadi)", none == [None], none)

print("\n3b) Zaxira rasmlar: yuklanmagan yoki bo'sh qolgan slot to'ldiriladi")
check("zaxira ro'yxati slotlardagilarni takrorlamaydi",
      photo_search.parse_spare({"spare": [1, 4, 4, "x", 50, 5]}, [[1, 2], [3]], 10) == [4, 5])
photo_search.reset(); downloads.clear()


async def choose_with_spare(system, user):
    return {"picks": [{"slot": 1, "ids": [0]}, {"slot": 2, "ids": []}], "spare": [5, 6]}

photo_search._download = fake_download
try:
    got = asyncio.run(photo_search.find_photos("Amir Temur", ["Saltanat", "Me'morchilik"],
                                               search=search, choose=choose_with_spare))
finally:
    photo_search._download = real_download
check("1-slot rasmi yuklanmadi → zaxira, 2-slot bo'sh → keyingi zaxira",
      all(got) and [d.rsplit("/", 1)[1] for d in downloads] == ["img0.jpg", "img5.jpg", "img6.jpg"], downloads)
for path in got:
    if path:
        os.remove(path)

print("\n3b) Bir xil rasm (boshqa saytdan, boshqa manzil bilan) ikki slaydga qo'yilmaydi")
photo_search.reset(); downloads.clear()
_twin = {"img1.jpg": (900, 600), "img2.jpg": (1200, 800)}       # bitta surat, ikki sayt, ikki o'lcham


async def twin_download(session, url):
    downloads.append(url)
    name = url.rsplit("/", 1)[1]
    if name in _twin:
        return _image(*_twin[name], seed=4242)
    return _image()


async def choose_twins(system, user):
    return {"picks": [{"slot": 1, "ids": [1]}, {"slot": 2, "ids": [2]}], "spare": [3, 4]}


async def no_text(paths):
    return set()

photo_search._download = twin_download
try:
    got = asyncio.run(photo_search.find_photos("Amir Temur saltanati", ["Saltanat", "Yurishlar"],
                                               search=search, choose=choose_twins, check=no_text))
    again = asyncio.run(photo_search.find_photos("Amir Temur saltanati", ["Muqova"],
                                                 search=search, choose=choose_twins, check=no_text))
finally:
    photo_search._download = real_download
marks = [photo_search.image_hashes(p) for p in got if p]
check("ikkala slaydda rasm bor, lekin ular har xil",
      all(got) and len(marks) == 2 and not photo_search.same_picture(marks[0], marks[1]), (got, downloads))
check("takror tashlanib, slotga zaxira nomzod olindi", [d.rsplit("/", 1)[1] for d in downloads][:3] == ["img1.jpg", "img2.jpg", "img3.jpg"],
      downloads)
check("o'sha mavzuning keyingi chaqiruvi (muqova) ham oldingi rasmlarni takrorlamaydi",
      not again[0] or not any(photo_search.same_picture(photo_search.image_hashes(again[0]), m) for m in marks))
check("o'xshash, lekin boshqa suratlar takror hisoblanmaydi",
      not photo_search.same_picture(photo_search.image_hashes(_image(seed=1)), photo_search.image_hashes(_image(seed=2))))
for path in got + again:
    if path:
        os.remove(path)

nameless = photo_search.usable([{"title": "", "source": "travel.uz", "url": "https://travel.uz/tours/gur-e-amir-mausoleum",
                                 "properties": {"url": "https://travel.uz/i/1.jpg", "width": 1200, "height": 800}}])
check("nomsiz natijaga sahifa manzilidan ishora", "gur e amir mausoleum" in photo_search._pick_prompt("t", ["s"], nameless),
      nameless)

print("\n3c) Matnli rasmlar (birovning slaydi, jadval, sxema) qo'yilmaydi")
texty = photo_search.usable([
    _result(20, source="slideplayer.com", title="Levosimendan mechanism"),
    _result(21, source="www.slideshare.net"),
    _result(22, title="Mechanism of action - PowerPoint presentation"),
    _result(23, title="Heart failure treatment diagram"),
    _result(24, title="Схема кровообращения"),
    _result(25, title="Doctor talking with patient in hospital"),
])
check("slayd saytlari va «slide/ppt/diagram/схема» sarlavhalari tashlanadi",
      [c["url"].rsplit("/", 1)[1] for c in texty] == ["img25.jpg"], [c["url"] for c in texty])
check("AI ga slayd va matnli rasm tanlamaslik aytilgan", "presentation slides" in photo_search._PICK_SYSTEM)

photo_search.reset(); downloads.clear()
checked = []


async def reject_first(paths):
    checked.append(len(paths))
    return {0} if len(checked) == 1 else set()   # birinchi davrada 1-rasm matnli


async def choose_two(system, user):
    return {"picks": [{"slot": 1, "ids": [1, 2]}, {"slot": 2, "ids": [3]}], "spare": [4]}

photo_search._download = fake_download
try:
    got = asyncio.run(photo_search.find_photos("Yurak yetishmovchiligi", ["Davolash", "Klinik sinov"],
                                               search=search, choose=choose_two, check=reject_first))
finally:
    photo_search._download = real_download
check("matnli rasm tashlandi, slotga navbatdagi nomzod qo'yildi",
      all(got) and checked == [2, 1] and [d.rsplit("/", 1)[1] for d in downloads] == ["img1.jpg", "img3.jpg", "img2.jpg"],
      (checked, downloads))
for path in got:
    if path:
        os.remove(path)


async def broken_check(paths):
    raise RuntimeError("vision yo'q")

check("tekshiruv ishlamasa rasmlar tashlanadi (fail-closed: skrinshot o'tib ketmasin)",
      asyncio.run(photo_search.text_heavy(["a.jpg", "b.jpg"], broken_check)) == {0, 1})

print("\n5b) O'zbek slayd/referat saytlari va matnli varaqlar")
uz_sites = photo_search.usable([
    {"title": "Global ekologik muammolar", "source": "soff.uz", "url": "https://soff.uz/product/ekologiya-8",
     "properties": {"url": "https://soff.uz/_next/image?url=https://cdn.net/a.jpg", "width": 961, "height": 540}},
    {"title": "Naysimon suyaklar", "source": "arxiv.uz", "url": "https://arxiv.uz/ru/documents/x",
     "properties": {"url": "https://arxiv.uz/b.jpg", "width": 1024, "height": 768}},
    {"title": "Iqlim o'zgarishi", "source": "slaydchi.uz", "url": "https://slaydchi.uz/x",
     "properties": {"url": "https://slaydchi.uz/c.jpg", "width": 1024, "height": 768}},
    {"title": "Iqlim", "source": "cdn.example.com", "url": "https://example.com/x",
     "properties": {"url": "https://cdn.example.com/file-46759_page-5_generate.jpg", "width": 1024, "height": 768}},
    {"title": "Ekologiya referat", "source": "example.com", "url": "https://example.com/y",
     "properties": {"url": "https://example.com/d.jpg", "width": 1024, "height": 768}},
    {"title": "Mustaqillik bayrami", "source": "gazeta.uz", "url": "https://gazeta.uz/mustaqillik-bayrami",
     "properties": {"url": "https://gazeta.uz/media/e.jpg", "width": 1024, "height": 768}},
])
check("soff.uz, arxiv.uz, slaydchi, «page-5» va «referat» tashlanadi; yangilik fotosi qoladi",
      [c["url"].rsplit("/", 1)[1] for c in uz_sites] == ["e.jpg"], [c["url"] for c in uz_sites])

from PIL import ImageDraw
_tmp = tempfile.mkdtemp()
page = Image.new("RGB", (1000, 1300), "white")
_draw = ImageDraw.Draw(page)
for row in range(26):
    _draw.text((80, 80 + row * 44), "Ponasimon suyak bosh suyagining markaziy qismida joylashgan " * 2, fill="black")
page_path = os.path.join(_tmp, "page.jpg"); page.save(page_path)
photo_img = Image.radial_gradient("L").resize((1200, 800)).convert("RGB")
photo_path = os.path.join(_tmp, "photo.jpg"); photo_img.save(photo_path)
check("hujjat beti mahalliy tekshiruvda topiladi", photo_search.looks_like_text_page(page_path),
      photo_search.text_lines(page_path))
check("matnsiz rasm o'tadi", not photo_search.looks_like_text_page(photo_path), photo_search.text_lines(photo_path))
seen_by_ai = []


async def ai_accepts(paths):
    seen_by_ai.append(list(paths))
    return set()

check("matnli varaq AI ga yuborilmay tashlanadi, qolgani AI ga boradi",
      asyncio.run(photo_search.text_heavy([page_path, photo_path], ai_accepts)) == {0}
      and seen_by_ai == [[photo_path]], seen_by_ai)

check("har rasm hukmi o'qiladi; hukmsiz rasm rad etiladi",
      photo_search.parse_rejects({"images": [{"n": 1, "verdict": "accept"}, {"n": 2, "verdict": "reject"}]}, 3)
      == {1, 2})
check("eski {reject: [...]} javobi ham tushuniladi", photo_search.parse_rejects({"reject": [2]}, 3) == {1})

import json
from services.premium_presentation import llm_client

_sent = []


def _fake_request(kind, payload, timeout=90):
    _sent.append((kind, payload))
    return {"choices": [{"message": {"content": json.dumps({"images": [
        {"n": n, "verdict": "accept"} for n in range(1, 5)]})}}]}

with patch.object(llm_client, "_request", _fake_request):
    got = _REAL_TEXT_CHECK([photo_path] * 6)
check("rasmlar 4 tadan guruhlab, «photocheck» zanjiri bilan tekshiriladi",
      got == set() and [k for k, _ in _sent] == ["photocheck", "photocheck"]
      and [sum(1 for c in p["messages"][0]["content"] if c["type"] == "image_url") for _, p in _sent] == [4, 2],
      [(k, len(p["messages"][0]["content"])) for k, p in _sent])

import tempfile as _tf
os.environ["BRAVE_KEYS_FILE"] = os.path.join(_tf.mkdtemp(), "brave_keys.json")   # haqiqiy kalitlar fayliga tegmaydi
os.environ.pop("BRAVE_API_KEY", None); os.environ.pop("BRAVE_SEARCH_API_KEY", None)
check("kalit yo'q bo'lsa qidiruv o'chiq", not photo_search.enabled())
os.environ["BRAVE_API_KEY"] = "k"; os.environ["PHOTO_SEARCH"] = "0"
check("PHOTO_SEARCH=0 bilan o'chiriladi", not photo_search.enabled())
os.environ.pop("PHOTO_SEARCH"); os.environ.pop("BRAVE_API_KEY")

print("\n4) Zamonaviy taqdimot: avval sayt, topilmaganini AI chizadi")
page = ('<html><head></head><body><section class="slide"><div class="body"><h2>Yurak <b>tuzilishi</b></h2>'
        '<div class="rasm" data-prompt="human heart close up"><p class="rasm-matn">A</p></div>'
        '<div class="rasm" data-prompt="doctor with stethoscope"><p class="rasm-matn">B</p></div>'
        '</div></section></body></html>')
asked, drawn = [], []


async def find(topic, slots):
    asked.append((topic, list(slots)))
    return [_image(), None]


async def draw(prompt):
    drawn.append(prompt)
    return _image(40, 30)

done, placed = asyncio.run(html_images.fill_photos([page], generate=draw, topic="Inson yuragi", find=find))
check("slot matni: sarlavha + rasm tavsifi",
      asked and asked[0][1][0] == "Yurak tuzilishi — human heart close up", asked)
check("2 ta rasm qo'yildi, AI faqat topilmaganini chizdi",
      placed == 2 and len(drawn) == 1 and "doctor" in drawn[0], (placed, drawn))
check("matn o'rnida rasm", done[0].count('class="photo"') == 2 and "rasm-matn" not in done[0])
check("slayd rasmlarining kesish fokusi HTML ga uzatildi",
      done[0].count("object-position:") == 2, done[0])

ai_first_calls = {"find": 0, "drawn": 0}


async def find_ai_first(topic, slots):
    ai_first_calls["find"] += 1
    return ["/web.jpg"] * len(slots)


async def draw_ai_first(prompt):
    ai_first_calls["drawn"] += 1
    return "/ai.png"


with patch.object(html_images, "_take_uri", lambda path: "data:image/png;base64,AA" if path else None), \
        patch.object(html_images, "_photo_position", lambda path, ratio: "50% 50%"):
    _, ai_first_placed = asyncio.run(html_images.fill_photos(
        [page], topic="Sun'iy intellekt", source="mix",
        find=find_ai_first, generate=draw_ai_first))
check("mix AI-mavzuda Brave'ni o'tkazib, tasvirni AI ga beradi",
      ai_first_calls == {"find": 0, "drawn": 2} and ai_first_placed == 2, ai_first_calls)
ai_first_calls["find"] = 0
with patch.object(html_images, "_take_uri", lambda path: "data:image/png;base64,AA" if path else None), \
        patch.object(html_images, "_photo_position", lambda path, ratio: "50% 50%"):
    asyncio.run(html_images.fill_photos(
        [page], topic="Sun'iy intellekt", source="web", find=find_ai_first))
check("web tanlovi AI-first mavzuda ham internetdan qidiradi", ai_first_calls["find"] == 1, ai_first_calls)

cover = ('<html><head></head><body><section class="slide cover"><div class="body"><h1>Yurak</h1>'
         '</div></section><!-- end --></body></html>')
drawn.clear()


async def find_cover(topic, slots):
    return [_image()]

pages, ok = asyncio.run(html_images.fill_cover([cover], "Inson yuragi", generate=draw, find=find_cover))
check("muqova rasmi saytdan topilsa AI chizmaydi", ok and not drawn and "cover-photo" in pages[0], (ok, drawn))
check("muqova rasmida ham fokusli kesish pozitsiyasi bor",
      ok and "object-position:" in pages[0], pages[0])


async def find_nothing(topic, slots):
    return [None]

pages, ok = asyncio.run(html_images.fill_cover([cover], "Inson yuragi", generate=draw, find=find_nothing))
check("muqova rasmi topilmasa AI chizadi", ok and len(drawn) == 1, (ok, drawn))
ai_cover_calls = {"find": 0, "drawn": 0}


async def find_ai_cover(topic, slots):
    ai_cover_calls["find"] += 1
    return ["/web.jpg"]


async def draw_ai_cover(subject):
    ai_cover_calls["drawn"] += 1
    return "/ai.png"


with patch.object(html_images, "_take_uri", lambda path: "data:image/png;base64,AA" if path else None), \
        patch.object(html_images, "_photo_position", lambda path, ratio: "50% 50%"):
    _, ai_cover_done = asyncio.run(html_images.fill_cover(
        [cover], "Kosmos", generate=draw_ai_cover, find=find_ai_cover, source="mix"))
check("mix futuristik muqovada AI qidiruvdan oldin tanlanadi",
      ai_cover_done and ai_cover_calls == {"find": 0, "drawn": 1}, ai_cover_calls)

print("\n5) Oddiy taqdimot: topilgan slaydga AI chizilmaydi")
from services import document_service as ds


class FakeTogether:
    def __init__(self):
        self.calls = []

    async def generate_cover_image(self, topic, language):
        self.calls.append("cover"); return _image()

    async def generate_slide_image(self, topic, title, language):
        self.calls.append(title); return _image()

    async def generate_panoramic_image(self, topic, title, language):
        self.calls.append(title); return _image()


service = ds.DocumentService.__new__(ds.DocumentService)
service.together = FakeTogether()
slides = [{"layout": "cover"}, {"layout": "text", "title": "Reja"}]
from services import slide_layouts
image_layouts = [name for name, spec in slide_layouts.CATALOG.items() if spec.image == "slide"]
slides += [{"layout": image_layouts[0], "title": "Yurak"}, {"layout": image_layouts[0], "title": "O'pka"}]
seen_slots = []


async def fake_find(topic, slots):
    seen_slots.append(list(slots))
    return [_image(), None, _image()]

old_enabled, old_find = photo_search.enabled, photo_search.find_photos
photo_search.enabled, photo_search.find_photos = (lambda: True), fake_find
try:
    images = asyncio.run(service._prefetch_slide_images(slides, "Inson organlari", "uz"))
finally:
    photo_search.enabled, photo_search.find_photos = old_enabled, old_find
check("rasm kerak slaydlar bitta ro'yxatda so'raldi (muqova + 2 slayd)",
      len(seen_slots) == 1 and len(seen_slots[0]) == 3 and seen_slots[0][1:] == ["Yurak", "O'pka"], seen_slots)
check("AI faqat topilmagan «Yurak» slaydini chizdi", service.together.calls == ["Yurak"], service.together.calls)
check("hamma rasm o'rni to'ldi", sorted(images) == [0, 2, 3], sorted(images))
for path in images.values():
    if isinstance(path, str) and os.path.exists(path):
        os.remove(path)

print("\n6) AI nazorati hisobi")
ai_usage.record("photo", ai_usage.PHOTO_SITE, 3)
ai_usage.record("photo", ai_usage.PHOTO_AI)
for _ in range(3):
    ai_usage.record("text", "anthropic/claude-sonnet-5")
ai_usage.record("text", "google/gemini-2.5-flash")
ai_usage.record("image", "black-forest-labs/FLUX.1-schnell")
today = asyncio.run(ai_usage.day_counts())
check("bugungi hisob (oldingi bo'limlardagi saytdan topilganlar ham qo'shiladi)",
      today["text"] == {"anthropic/claude-sonnet-5": 3, "google/gemini-2.5-flash": 1}
      and today["photo"].get(ai_usage.PHOTO_SITE, 0) >= 3, today)
fresh = {"photo": {"sayt": 3, "ai": 1}, "text": today["text"], "image": {"black-forest-labs/FLUX.1-schnell": 1}}
text = ai_usage.report_text(fresh, asyncio.run(ai_usage.photo_days(7)))
check("rasmlar foizda: saytdan 75%, AI 25%", "Saytdan (Brave): 3 ta — 75%" in text and "AI chizgan: 1 ta — 25%" in text, text)
check("eng ko'p ishlatilgan model birinchi, foizda",
      text.index("claude-sonnet-5 — 75%") < text.index("gemini-2.5-flash — 25%"), text)
check("7 kunlik jadval bor", "Oxirgi 7 kun" in text, text)

from services.premium_presentation import llm_client
before = asyncio.run(ai_usage.day_counts())["text"].get("test/model", 0)
llm_client._count_model("test/model")
after = asyncio.run(ai_usage.day_counts())["text"].get("test/model", 0)
check("premium matn modeli hisobga tushadi", after == before + 1, (before, after))

from services import together_service
together_service._count_image("test/flux")
counts = asyncio.run(ai_usage.day_counts())
check("chizilgan rasm modeli va «AI chizgan» hisobga tushadi",
      counts["image"].get("test/flux") == 1 and counts["photo"].get("ai") == 2, counts)

print("\n6b) Rasm tanlash modeli — arzon, Claude'siz")
from services.premium_presentation import config as pconfig
chain = llm_client._models("photo")
check("birinchi model gemini-2.5-flash-lite", chain[0] == "google/gemini-2.5-flash-lite", chain)
check("zanjirda Claude yo'q", not any(m.startswith("anthropic/") for m in chain), chain)
llm_client.set_text_model("anthropic/claude-sonnet-4.5")
llm_client._WORKING["photocheck"] = "openai/gpt-4o-mini"
check("rasmdagi matn tekshiruvi modeli qat'iy: admin AI ni almashtirsa ham o'zgarmaydi",
      llm_client._models("photocheck") == list(pconfig.PHOTO_TEXT_CHECK_MODELS)
      and pconfig.PHOTO_TEXT_CHECK_MODELS[0] == "google/gemini-2.5-flash", llm_client._models("photocheck"))
llm_client._WORKING.pop("photocheck", None)

print("\n7) Admin panel")
from bot.keyboards import get_admin_keyboard
from bot.handlers import admin
check("admin menyusida «🧠 AI nazorati»",
      any(b.text == "🧠 AI nazorati" for row in get_admin_keyboard().keyboard for b in row))
check("tugma ishlovchisi bor", hasattr(admin, "handle_ai_control"))

print()
if FAILS:
    print(f"XATO: {len(FAILS)} ta"); sys.exit(1)
print("Hammasi to'g'ri")
