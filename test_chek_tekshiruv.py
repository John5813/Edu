"""To'lov chekini AI bilan avtomatik tekshirish: qoidalar, o'qish, himoya va to'liq oqim.

Claude javobi soxtalashtirilgan (haqiqiy API chaqirilmaydi): qoidalar mijoz yuborgan haqiqiy
cheklar turlariga (Click, Hamkor, Uzum, SQB, Payme, soliq cheki) mos ma'lumotlar bilan sinaladi.

    python test_chek_tekshiruv.py
"""
import asyncio, io, os, sys, tempfile, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import config
from services.receipts import reader, rules, store, texts, flow
from services.receipts.rules import Receipt, Context, Prior

NOW = datetime(2026, 10, 6, 20, 10)
CARDS = ("6655", "2378")
def ctx(**kw):
    base = dict(now=NOW, claimed=10_000, cards=CARDS, owner_names=("JAVLONBEK",), user_tg=1,
                started_at=NOW - timedelta(minutes=15))
    base.update(kw)
    return Context(**base)

def rec(**kw):
    base = dict(doc_type="transfer", status="success", amount=10_000, dt=NOW - timedelta(minutes=6),
                ids=["5333277563"], sender_name="FARXOD N.", sender_tail="6989", receiver_name="JAVLONBEK M.",
                receiver_tail="6655", app="click", status_time="20:04", battery=28, is_screenshot=True)
    base.update(kw)
    return Receipt(**base)

def prior(**kw):
    base = dict(receipt_id=7, user_tg=99, verdict="auto", payment_id=3, payment_status="approved",
                created_at="2026-10-06 19:00:00", kind="id", age_min=70)
    base.update(kw)
    return Prior(**base)

print("1) Yaxshi cheklar avtomatik tasdiqlanadi (haqiqiy cheklar turlariga o'xshash)")
d = rules.evaluate(rec(), ctx())
check("Click kvitansiyasi (ID bor)", d.verdict == rules.AUTO and d.credit == 10_000, (d.verdict, d.reasons))
d = rules.evaluate(rec(app="hamkor", ids=["b4f4098b-482f-4cd4-b9f7-663554347505"], status_time=None, battery=None,
                       sender_name="PARDABOYEVA G.", sender_tail="2652"), ctx())
check("Hamkor PDF/skrinshot (uuid ID, soat yo'q)", d.verdict == rules.AUTO, (d.verdict, d.reasons))
d = rules.evaluate(rec(app="click", ids=[], sender_name="", sender_tail="", status_time="20:04", battery=91,
                       receiver_name="JAVLONBEK M."), ctx())
check("Click «Muvaffaqiyatli» ekrani: ID ham yuboruvchi ham yo'q, lekin soat+batareya bor", d.verdict == rules.AUTO, (d.verdict, d.reasons))
d = rules.evaluate(rec(app="payme", ids=[], receiver_tail="2378", sender_name="", sender_tail="", status_time="19:52", battery=46,
                       dt=NOW - timedelta(minutes=20)), ctx(started_at=NOW - timedelta(minutes=30)))
check("Payme (2-karta oxiri 2378)", d.verdict == rules.AUTO, (d.verdict, d.reasons))
d = rules.evaluate(rec(amount=17_000, fee=170), ctx(claimed=10_000))
check("summa farq qilsa chekdagi summa qo'shiladi va belgilanadi", d.verdict == rules.AUTO and d.credit == 17_000 and "amount_differs" in d.reasons, (d.verdict, d.credit, d.reasons))
check("ikkinchi o'qish talab qilinadi", d.needs_verify)

print("2) Chek emas")
d = rules.evaluate(Receipt(doc_type="tax_receipt", amount=26), ctx())
check("soliq cheki (Savdo cheki/MXIK) — chek emas", d.verdict == rules.NOT_RECEIPT and d.reasons == ["tax_receipt"], d.reasons)
check("boshqa hujjat — chek emas", rules.evaluate(Receipt(doc_type="other"), ctx()).verdict == rules.NOT_RECEIPT)
check("o'qib bo'lmagan chek", rules.evaluate(rec(readable=False), ctx()).verdict == rules.NOT_RECEIPT)
check("muvaffaqiyatsiz to'lov", rules.evaluate(rec(status="failed"), ctx()).verdict == rules.NOT_RECEIPT)
check("yakunlanmagan to'lov", rules.evaluate(rec(status="pending"), ctx()).verdict == rules.NOT_RECEIPT)

print("2b) Faqat summa va ilova nomi ko'rinadigan chek qabul qilinmaydi")
bare = Receipt(doc_type="payment", status="success", amount=10_000, app="click", status_time="20:04", battery=91)
d = rules.evaluate(bare, ctx())
check("faqat summa+brend (soat/batareya bor bo'lsa ham) — chek emas, asl chek so'raladi",
      d.verdict == rules.NOT_RECEIPT and d.reasons == ["too_little"] and not d.fraud, (d.verdict, d.reasons))
check("faqat summa+brend, hech narsa yo'q", rules.evaluate(Receipt(doc_type="transfer", amount=5000, app="payme"), ctx()).reasons == ["too_little"])
check("qabul qiluvchi ko'rinsa — to'liq emas, lekin chek", rules.evaluate(rec(ids=[], sender_name="", sender_tail="", dt=None, status_time="20:05"), ctx()).verdict != rules.NOT_RECEIPT)
check("faqat sana bor — chek", rules.evaluate(Receipt(doc_type="transfer", amount=5000, app="payme", dt=NOW - timedelta(minutes=3)), ctx()).verdict != rules.NOT_RECEIPT)
check("faqat ID bor — chek", rules.evaluate(Receipt(doc_type="transfer", amount=5000, app="uzum", ids=["c67a416a-e4eb-4a60"]), ctx()).verdict != rules.NOT_RECEIPT)

print("3) Takroriy cheklar (ID tahrirlangan holatlar ham)")
same = rec()
found = {("id", "5333277563"): prior()}
d = rules.evaluate(same, ctx(), "", found)
check("bir xil ID — takroriy, soxta belgisi", d.verdict == rules.DUPLICATE and d.fraud and "duplicate_id" in d.reasons, (d.verdict, d.reasons))
check("avvalgi chek ma'lumoti adminga beriladi", d.priors and d.priors[0].receipt_id == 7)
edited = rec(ids=["5333277999"])      # ID o'zgartirilgan, qolgani bir xil
keys = dict(rules.build_keys(rec(), "") )
found = {("cmp", rules.build_keys(rec())[1][1]): prior(kind="cmp")}
cmp_key = [k for k in rules.build_keys(edited) if k[0] == "cmp"][0]
d = rules.evaluate(edited, ctx(), "", {cmp_key: prior(kind="cmp")})
check("ID o'zgartirilgan, lekin summa+vaqt+yuboruvchi+qabul qiluvchi bir xil — ushlandi", d.verdict == rules.DUPLICATE and d.fraud, (d.verdict, d.reasons))
scr_key = [k for k in rules.build_keys(edited) if k[0] == "scr"][0]
d = rules.evaluate(rec(ids=["1111111"], sender_name="BOSHQA", sender_tail="1234"), ctx(), "", {scr_key: prior(kind="scr")})
check("ID va yuboruvchi o'zgargan, lekin telefon soati+batareya+ilova+summa bir xil — ushlandi",
      d.verdict == rules.DUPLICATE and "duplicate_scr" in d.reasons, (d.verdict, d.reasons))
d = rules.evaluate(rec(), ctx(), "abc", {("file", "abc"): prior(kind="file")})
check("aynan shu fayl — ushlandi", d.verdict == rules.DUPLICATE and "duplicate_file" in d.reasons)
d = rules.evaluate(rec(), ctx(user_tg=99), "", {("id", "5333277563"): prior(user_tg=99, payment_status="pending", age_min=500)})
check("o'zining kutilayotgan cheki qayta yuborildi — jazosiz", d.verdict == rules.OWN_PENDING and not d.fraud and d.reasons == ["own_pending"], (d.verdict, d.reasons))
d = rules.evaluate(rec(), ctx(user_tg=99), "", {("id", "5333277563"): prior(user_tg=99, payment_status="approved", age_min=5)})
check("o'zining yaqinda qabul qilingan cheki — jazosiz «allaqachon qabul qilingan»", d.verdict == rules.OWN_PENDING and d.reasons == ["own_done"], (d.verdict, d.reasons))
d = rules.evaluate(rec(), ctx(user_tg=99), "", {("id", "5333277563"): prior(user_tg=99, payment_status="approved", age_min=600)})
check("o'zining kech (10 soat) qayta yuborgan cheki — takroriy", d.verdict == rules.DUPLICATE and d.fraud)
wk = [k for k in rules.lookup_keys(rec()) if k[0] == "wk"][0]
d = rules.evaluate(rec(ids=["7777777"], sender_tail="1111", sender_name="X"), ctx(), "", {wk: prior(kind="wk")})
check("faqat summa+vaqt mos — shubha (admin), jazo yo'q", d.verdict == rules.REVIEW and not d.fraud and "possible_duplicate" in d.reasons, (d.verdict, d.reasons, d.fraud))
shifted = [k for k in rules.lookup_keys(rec()) if k[0] == "wk" and k != wk][0]
d = rules.evaluate(rec(ids=["7777777"], sender_tail="1111", sender_name="X"), ctx(), "", {shifted: prior(kind="wk")})
check("vaqt ±1 daqiqa farqi ham ushlanadi", "possible_duplicate" in d.reasons)

print("4) Vaqt")
d = rules.evaluate(rec(dt=NOW - timedelta(days=3), status_time=None, battery=None), ctx())
check("3 kun oldingi chek — admin, 'eski'", d.verdict == rules.REVIEW and "stale" in d.reasons and not d.fraud, (d.verdict, d.reasons))
check("yosh matni", rules.fmt_age(d.age_min) == "3 kun", rules.fmt_age(d.age_min))
d = rules.evaluate(rec(dt=NOW - timedelta(minutes=50)), ctx())
check("50 daqiqa oldingi chek eski (chegara 45)", "stale" in d.reasons)
d = rules.evaluate(rec(dt=NOW - timedelta(minutes=30)), ctx(started_at=NOW - timedelta(minutes=40)))
check("30 daqiqa oldingi chek yaroqli", d.verdict == rules.AUTO, (d.verdict, d.reasons))
d = rules.evaluate(rec(dt=NOW - timedelta(minutes=25)), ctx(started_at=NOW - timedelta(minutes=10)))
check("chek to'lov so'rovidan OLDIN o'tkazilgan — admin", "before_request" in d.reasons and d.verdict == rules.REVIEW)
d = rules.evaluate(rec(dt=NOW + timedelta(hours=2)), ctx())
check("kelajakdagi vaqt — admin", "future" in d.reasons)
d = rules.evaluate(rec(status_time="08:15", dt=NOW - timedelta(minutes=5)), ctx())
check("telefon soati hozirdan juda farq qiladi (skrinshot eski) — admin", d.verdict == rules.REVIEW and ("screenshot_old" in d.reasons or "clock_mismatch" in d.reasons), d.reasons)
d = rules.evaluate(rec(dt=None, status_time="20:05", ids=["1234567"]), ctx())
check("sana yo'q, lekin telefon soati yangi va ID bor — qabul", d.verdict in (rules.AUTO, rules.REVIEW) and "no_time" not in d.reasons, (d.verdict, d.reasons))
d = rules.evaluate(rec(dt=None, status_time=None, battery=None), ctx())
check("sana ham soat ham yo'q — admin", d.verdict == rules.REVIEW and "no_time" in d.reasons)
check("kechagi telefon soati kecha deb hisoblanadi", rules.clock_age_min("23:50", datetime(2026, 10, 6, 0, 5)) == 15)

print("5) Qabul qiluvchi")
d = rules.evaluate(rec(receiver_tail="1234", receiver_name="BOSHQA ODAM"), ctx())
check("boshqa karta — rad (admin tugmalari bilan)", d.verdict == rules.WRONG_RECEIVER and not d.fraud, (d.verdict, d.reasons))
d = rules.evaluate(rec(receiver_tail="", receiver_name="JAVLONBEK M."), ctx())
check("karta oxiri ko'rinmasa, faqat ism — admin", d.verdict == rules.REVIEW and "receiver_by_name" in d.reasons, d.reasons)
d = rules.evaluate(rec(receiver_tail="", receiver_name=""), ctx())
check("qabul qiluvchi yo'q — admin", d.verdict == rules.REVIEW and "no_receiver" in d.reasons)

print("6) Shubhali belgilar va chegaralar")
check("AI «tahrirlangan» desa — admin", rules.evaluate(rec(tamper="high"), ctx()).verdict == rules.REVIEW)
check("kuchsiz tahrir belgisi (low) — o'tadi", rules.evaluate(rec(tamper="low"), ctx()).verdict == rules.AUTO)
check("fayl metama'lumotida Photoshop izi — admin", rules.evaluate(rec(meta_flags=["exif:Adobe Photoshop"]), ctx()).verdict == rules.REVIEW)
check("qirqilgan chek — admin", rules.evaluate(rec(cropped=True), ctx()).verdict == rules.REVIEW)
check("AI ishonchi past — admin", rules.evaluate(rec(confidence=0.4), ctx()).verdict == rules.REVIEW)
check("summa avto-chegaradan katta — admin", rules.evaluate(rec(amount=250_000), ctx(claimed=250_000)).verdict == rules.REVIEW)
check("ID'siz chek uchun chegara past (30 000)", rules.evaluate(rec(ids=[], amount=50_000), ctx(claimed=50_000)).verdict == rules.REVIEW)
check("ID bor — 50 000 o'tadi", rules.evaluate(rec(amount=50_000), ctx(claimed=50_000)).verdict == rules.AUTO)
check("summa o'qilmadi — admin", rules.evaluate(rec(amount=None), ctx()).verdict == rules.REVIEW)
check("valyuta so'm emas — admin", rules.evaluate(rec(currency="USD"), ctx()).verdict == rules.REVIEW)
check("soya rejimi: hammasi yaxshi bo'lsa ham admin", rules.evaluate(rec(), ctx(auto_enabled=False)).verdict == rules.REVIEW)
check("ID ham, to'liq ma'lumot ham yo'q — takrorlanishni tekshirib bo'lmaydi", "no_unique_key" in rules.evaluate(
    rec(ids=[], sender_name="", sender_tail="", status_time=None, battery=None), ctx()).reasons)
check("ID normallashtiriladi (tire, harf registri)", rules.norm_id("B4F4098B-482F-4CD4") == "b4f4098b482f4cd4")
check("qisqa ID kalit bo'lmaydi", not [k for k in rules.build_keys(rec(ids=["12"])) if k[0] == "id"])
check("ism normallashtiriladi", rules.norm_name("javlonbek m.") == "JAVLONBEK M")

print("7) Claude javobini o'qish (parse)")
raw = {"doc_type": "transfer", "status": "success", "readable": True, "amount": "10 000", "fee": 110, "currency": "UZS",
       "date": {"year": None, "month": 10, "day": 6, "hour": 20, "minute": 0},
       "ids": ["5333277563"], "sender_name": "FARXOD N.", "sender_card": "986012******6989",
       "receiver_name": "JAVLONBEK M.", "receiver_card": "986016****6655", "app": "Click",
       "screenshot": {"is_screenshot": True, "clock": "19:31", "battery": 28}, "cropped": False,
       "tamper": "none", "confidence": 0.93}
r = reader.parse(raw, now=NOW)
check("summa, karta oxiri, sana (yil yo'q → joriy)", r.amount == 10_000 and r.receiver_tail == "6655" and r.sender_tail == "6989"
      and r.dt == datetime(2026, 10, 6, 20, 0), (r.amount, r.receiver_tail, r.dt))
check("telefon soati va batareya", r.status_time == "19:31" and r.battery == 28)
check("yil ko'rinmagan, sana kelajakda bo'lsa o'tgan yil", reader.parse({**raw, "date": {"year": None, "month": 12, "day": 25, "hour": 10, "minute": 0}}, now=NOW).dt.year == 2025)
check("noto'g'ri qiymatlar xavfsiz", reader.parse({"doc_type": "zzz", "amount": "abc", "date": {"month": 13}, "screenshot": {"battery": 500}}, now=NOW).doc_type == "other")
check("pul formatlari", (reader.money("17,000.00"), reader.money("5 000"), reader.money(26.4), reader.money("1.250.000")) == (17000, 5000, 26, 1250000))
a, b = reader.parse(raw, now=NOW), reader.parse({**raw, "amount": 18000}, now=NOW)
check("ikki o'qish solishtiriladi: summa farqi", reader.compare(a, b) == ["amount"], reader.compare(a, b))
check("ikki o'qish solishtiriladi: ID raqami adashtirilsa", "id" in reader.compare(a, reader.parse({**raw, "ids": ["5333277568"]}, now=NOW)))
check("bir xil o'qish — farq yo'q", reader.compare(a, reader.parse(raw, now=NOW)) == [])

print("8) Fayllarni tayyorlash (rasm, PDF, DOCX)")
from PIL import Image
buf = io.BytesIO(); Image.new("RGB", (600, 1200), "white").save(buf, "JPEG"); plain = buf.getvalue()
p = reader.prepare(plain, "a.jpg")
check("oddiy rasm: bitta rasm, tahrir belgisi yo'q", len(p.images) == 1 and not p.meta_flags)
img = Image.new("RGB", (600, 1200), "white"); ex = img.getexif(); ex[305] = "Adobe Photoshop 25.0"
buf = io.BytesIO(); img.save(buf, "JPEG", exif=ex); edited_jpg = buf.getvalue()
check("EXIF'da Photoshop — belgilanadi", any("Photoshop" in f for f in reader.prepare(edited_jpg, "b.jpg").meta_flags))
import pymupdf
pdf = pymupdf.open(); page = pdf.new_page(); page.insert_text((72, 72), "Receipt 10000 UZS  Transaction ID 123456789"); pdf_bytes = pdf.tobytes()
pp = reader.prepare(pdf_bytes, "chek.pdf")
check("PDF: matn qatlami va sahifa rasmi", pp.kind == "pdf" and "123456789" in pp.text and len(pp.images) == 1)
import docx
document = docx.Document(); document.add_paragraph("Chek 10000 so'm"); dbuf = io.BytesIO(); document.save(dbuf)
pd = reader.prepare(dbuf.getvalue(), "chek.docx")
check("DOCX: matn o'qiladi", pd.kind == "docx" and "10000" in pd.text)
try:
    reader.prepare(b"not an image", "x.heic"); ok = False
except reader.Unsupported:
    ok = True
check("o'qib bo'lmaydigan fayl — Unsupported", ok)

print("\nXATO:" if FAILS else "\nQoidalar HAMMASI YAXSHI", FAILS or "")
sys.exit(1 if FAILS else 0)
