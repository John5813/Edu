"""Bir chek — bir marta: mijoz adminga yetib borgan chekini qayta yuborsa, u adminga qayta bormaydi.

AI'siz, faqat faylning o'zi bo'yicha (raqamli iz, Telegram fayl raqami, rasm ko'rinishi) va faqat o'sha mijozning
o'z cheklari orasida. Galereyadan qayta tanlangan (qayta siqilgan) skrinshot ham taniladi; boshqa summa, vaqt yoki
ID yozilgan chek — yangi chek. Izlar faqat 2 kun saqlanadi. Chek sifatida faqat bitta rasm yoki PDF (5 MB gacha).

    python test_chek_bir_marta.py
"""
import asyncio, glob, io, os, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import config
import database.database as dbmod
from database.database import Database, init_db
from PIL import Image, ImageDraw, ImageFont
from services.receipts import once, web as receipt_web

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "t.db")
config.RECEIPT_AI = False                         # AI tekshiruvi o'chiq: chek to'g'ridan-to'g'ri adminga
if not config.ADMIN_IDS:
    config.ADMIN_IDS.append(7001)

_FONT = (glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)
         or glob.glob("/usr/share/fonts/**/*.ttf", recursive=True))


def font(size):
    return ImageFont.truetype(_FONT[0], size) if _FONT else ImageFont.load_default()


def receipt(amount="50 000", time_="14:32", rid="7731904562", clock="14:33"):
    """Telefon to'lov chekiga o'xshash skrinshot."""
    im = Image.new("RGB", (1080, 2340), (245, 247, 250))
    d = ImageDraw.Draw(im)
    d.text((40, 20), clock, fill=(0, 0, 0), font=font(40))
    d.rectangle([0, 160, 1080, 420], fill=(20, 130, 90))
    d.text((60, 240), "Click", fill="white", font=font(90))
    d.text((250, 860), f"{amount} so'm", fill=(0, 0, 0), font=font(110))
    y = 1100
    for k, v in [("Sana", f"19.11.2026 {time_}"), ("Qabul qiluvchi", "8600 **** 6655"), ("ID", rid)]:
        d.text((60, y), k, fill=(120, 120, 120), font=font(42))
        d.text((560, y), v, fill=(10, 10, 10), font=font(46))
        y += 120
    return im


def jpg(im, q=85, scale=1.0):
    if scale != 1:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    out = io.BytesIO(); im.save(out, "JPEG", quality=q); return out.getvalue()


class FakeBot:
    def __init__(self): self.sent, self.texts = [], []
    async def send_photo(self, chat_id, photo, **k):
        self.sent.append(("photo", chat_id))
        return types.SimpleNamespace(photo=[types.SimpleNamespace(file_id="F")])
    async def send_document(self, chat_id, document, **k):
        self.sent.append(("doc", chat_id))
        return types.SimpleNamespace(document=types.SimpleNamespace(file_id="F"))
    async def send_message(self, chat_id, text, **k):
        self.sent.append(("msg", chat_id)); self.texts.append(text)
        return types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id), message_id=len(self.sent))


async def main():
    await init_db()
    await Database.create_user(501, "ali", "Ali", "uz")
    await Database.create_user(502, "vali", "Vali", "ru")
    ali, vali = await Database.get_user(501), await Database.get_user(502)
    base = receipt()
    first = jpg(base, 90)

    print("1) Rasm izi (AI'siz)")
    pid = await Database.create_payment(ali.id, 50000, "F", "")
    await once.remember(501, first, "uid-1", pid)
    hit = await once.find(501, first)
    check("aynan o'sha fayl — taniladi, holati «kutilmoqda»", hit and hit["status"] == "pending" and hit["payment_id"] == pid, hit)
    check("galereyadan qayta tanlangan (qayta siqilgan, kichraygan) o'sha skrinshot — taniladi",
          bool(await once.find(501, jpg(base, 62, 0.7))))
    check("telefon soati boshqa (o'sha chekning yangi skrinshoti) — taniladi",
          bool(await once.find(501, jpg(receipt(clock="14:41"), 85))))
    check("Telegram fayl raqami bir xil (qayta uzatildi) — taniladi", bool(await once.find(501, b"boshqa bayt", "uid-1")))
    for name, im in (("boshqa summa", receipt(amount="50 500")), ("boshqa vaqt", receipt(time_="14:35")),
                     ("ID dagi bitta raqam boshqa", receipt(rid="7731904563"))):
        check(f"{name} — yangi chek (to'silmaydi)", not await once.find(501, jpg(im, 85)))
    check("boshqa mijoz o'sha faylni yuborsa — bu tekshiruv to'smaydi (faqat o'z akkaunti bo'yicha)",
          not await once.find(502, first))
    pdf = b"%PDF-1.4 chek " * 50
    pid_pdf = await Database.create_payment(ali.id, 30000, "F", "")
    await once.remember(501, pdf, "", pid_pdf)
    check("PDF chek — o'sha fayl qayta yuborilsa taniladi", bool(await once.find(501, pdf)))
    await Database.update_payment_status(pid, "approved")
    check("tasdiqlangan chek qayta yuborilsa — «allaqachon qabul qilingan»",
          once.reply_key((await once.find(501, first))["status"]) == "own_done")
    await Database.update_payment_status(pid, "rejected")
    check("rad etilgan chek qayta yuborilsa — «ko'rib chiqilgan»",
          once.reply_key((await once.find(501, first))["status"]) == "once_rejected")

    print("2) Sayt orqali: ikkinchi marta adminga bormaydi")
    bot = FakeBot()
    shot = receipt(amount="70 000", rid="9911")
    r1 = await receipt_web.submit(bot, 502, 70000, "", jpg(shot, 90), "chek.jpg", "image/jpeg")
    to_admin = len(bot.sent)
    check("birinchi chek — adminga yuborildi", to_admin >= 2 and r1["pending"], (r1, bot.sent))
    r2 = await receipt_web.submit(bot, 502, 70000, "", jpg(shot, 70, 0.8), "IMG_2.jpg", "image/jpeg")
    check("o'sha chek qayta yuklandi — adminga BORMADI", len(bot.sent) == to_admin, bot.sent[to_admin:])
    check("mijozga «tasdiqlanishini kuting» (o'z tilida — ruscha)", "Дождитесь подтверждения" in r2["message"]
          and r2["pending"] and not r2["retry"], r2)
    r3 = await receipt_web.submit(bot, 502, 70000, "", jpg(receipt(amount="70 000", rid="9912"), 90), "c.jpg", "image/jpeg")
    check("yangi (boshqa) chek — adminga boradi", len(bot.sent) > to_admin and r3["pending"], r3)

    print("3) Faqat 2 kun saqlanadi")
    import aiosqlite, time as _time
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        await conn.execute("UPDATE receipt_once SET created_at = ? WHERE user_tg = 501", (_time.time() - 3 * 86400,))
        await conn.commit()
    check("3 kun oldingi chek izi — hisobga olinmaydi", not await once.find(501, first))
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        async with conn.execute("SELECT COUNT(*) FROM receipt_once WHERE user_tg = 501") as cur:
            left = (await cur.fetchone())[0]
    check("eski izlar bazadan o'chirildi (baza to'lmaydi)", left == 0, left)

    print("4) Faqat bitta rasm yoki PDF, 5 MB gacha")
    from services.receipts import accept
    cases = [("chek.jpg", "image/jpeg", 300_000, None), ("chek.PNG", "", 200_000, None), ("chek.pdf", "application/pdf", 90_000, None),
             ("", "image/webp", 50_000, None), ("taqdimot.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", 900_000, "bad_file"),
             ("app.apk", "application/vnd.android.package-archive", 4_000_000, "bad_file"), ("video.mp4", "video/mp4", 2_000_000, "bad_file"),
             ("chek.docx", "", 50_000, "bad_file"), ("arxiv.zip", "", 10_000, "bad_file"), ("katta.jpg", "image/jpeg", 9 * 1024 * 1024, "too_big")]
    for name, mime, size, want in cases:
        check(f"{name or mime}: {'qabul' if want is None else want}", accept.problem(name, mime, size) == want,
              accept.problem(name, mime, size))
    sent = len(bot.sent)
    for name, mime, blob in (("taqdimot.pptx", "application/octet-stream", b"PK\x03\x04" + b"x" * 500),
                             ("app.apk", "application/vnd.android.package-archive", b"PK" + b"y" * 500)):
        try:
            await receipt_web.submit(bot, 502, 70000, "", blob, name, mime)
            ok = False
        except ValueError as exc:
            ok = "rasm" in str(exc) and "PDF" in str(exc)
        check(f"sayt: {name} — qabul qilinmaydi, adminga bormaydi", ok and len(bot.sent) == sent)
    try:
        await receipt_web.submit(bot, 502, 70000, "", b"x" * (6 * 1024 * 1024), "katta.jpg", "image/jpeg")
        ok = False
    except ValueError as exc:
        ok = "5 MB" in str(exc)
    check("sayt: 6 MB rasm — «5 MB dan katta»", ok)

    print("5) Click/Payme/Uzum orqali to'langan pulning cheki «karta» orqali yana yuborilsa")
    from services.receipts import auto_paid
    await Database.create_user(503, "gani", "G'ani", "uz")
    gani = await Database.get_user(503)
    pay_id = await Database.create_payment(gani.id, 50000, "", "payme")
    await Database.update_payment_status(pay_id, "approved")
    bot5 = FakeBot()
    before = len(bot5.sent)
    r = await receipt_web.submit(bot5, 503, 50000, "", jpg(receipt(amount="50 000", rid="5501"), 90), "payme.jpg", "image/jpeg")
    check("o'sha summa (Payme'da qabul qilingan) — adminga BORMADI", len(bot5.sent) == before, bot5.sent)
    check("mijozga «Payme orqali allaqachon qabul qilingan»", "Payme orqali allaqachon qabul qilingan" in r["message"]
          and "50 000" in r["message"] and r["verdict"] == "auto_paid" and not r["pending"], r)
    r = await receipt_web.submit(bot5, 503, 50000, "", jpg(receipt(amount="50 000", rid="5502"), 90), "karta.jpg", "image/jpeg")
    check("yana yuborildi (alohida karta o'tkazmasi) — adminga boradi", len(bot5.sent) > before and r["pending"], r)
    check("admin kartochkasida ogohlantirish matni yo'q", not [t for t in bot5.texts if "Diqqat" in t or "Payme orqali" in t], bot5.texts)
    n = len(bot5.sent)
    r = await receipt_web.submit(bot5, 503, 30000, "", jpg(receipt(amount="30 000", rid="5503"), 90), "c.jpg", "image/jpeg")
    check("boshqa summa — adminga boradi", len(bot5.sent) > n and r["pending"], r)
    click_id = await Database.create_payment(gani.id, 20000, "", "click")
    await Database.update_payment_status(click_id, "rejected")
    check("rad etilgan Click to'lovi — hisobga olinmaydi", not await auto_paid.match(503, 20000))
    old_id = await Database.create_payment(gani.id, 40000, "", "uzum")
    await Database.update_payment_status(old_id, "approved")
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        await conn.execute("UPDATE payments SET created_at = datetime('now', '-7 hours') WHERE id = ?", (old_id,))
        await conn.commit()
    check("7 soat oldingi Uzum to'lovi — chek to'xtatilmaydi (faqat 6 soat)", not await auto_paid.match(503, 40000))
    check("boshqa mijozning Payme to'lovi — bu mijoz chekiga ta'sir qilmaydi", not await auto_paid.match(501, 50000))

    print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
