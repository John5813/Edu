"""Qozoq tili: bot interfeysi va qozoqcha hujjatlar.

    python test_qozoq_tili.py
"""
import asyncio, json, os, re, string, sys, tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import translations as T
from translations_kk import KK
from services import kazakh_doc


def flat(table, prefix=""):
    out = {}
    for key, value in table.items():
        if isinstance(value, dict):
            out.update(flat(value, prefix + key + "."))
        else:
            out[prefix + key] = value
    return out


def fields(text):
    return sorted(name for _, name, _, _ in string.Formatter().parse(text) if name)


print("1) Interfeys matnlari")
ru, kk = flat(T.TRANSLATIONS["ru"]), flat(KK)
missing = sorted(set(ru) - set(kk))
check("ruscha jadvaldagi har kalitning qozoqchasi bor", not missing, missing[:8])
bad = [key for key in kk if key in ru and fields(ru[key]) != fields(kk[key])]
check("qozoqcha matnlarda {o'rinbosarlar} ruscha bilan bir xil", not bad, bad[:6])
cyrillic = re.compile(r"[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі]")
latin_only = [key for key, text in kk.items() if not cyrillic.search(text) and not re.fullmatch(r"[\W\d_]*PDF.*|.*→.*", text)]
check("qozoqcha matnlar kirillda", not latin_only, latin_only[:5])
check("qozoq harflari ishlatilgan", any(ch in "".join(kk.values()) for ch in "әғқңөұүһі"))
check("get_text('kk') qozoqcha", T.get_text("kk", "main_menu.settings") == "⚙️ Баптаулар")
check("kalit yo'q bo'lsa qozoqcha o'rniga ruscha (kalit emas)", T.get_text("kk", "select_source").startswith("📋"))
check("uch tilli kalitlar (samples_title) endi topiladi", "Примеры" in T.get_text("ru", "samples_title")
      and "Xizmat" in T.get_text("uz", "samples_title") and "үлгілері" in T.get_text("kk", "samples_title"))
with T.kazakh_scope(True):
    check("qozoq belgisi: 'ru' qozoqcha beradi", T.get_text("ru", "main_menu.help") == "📞 Көмек")
    check("qozoq belgisi uz/en ga tegmaydi", T.get_text("uz", "main_menu.help") == "📞 Yordam" and T.get_text("en", "main_menu.help") == "📞 Help")
check("belgi chiqqach ruscha", T.get_text("ru", "main_menu.help") == "📞 Помощь")
check("yo'q kalit — kalitning o'zi", T.get_text("kk", "no.such.key") == "no.such.key")
check("legacy_language", T.legacy_language("kk") == ("ru", True) and T.legacy_language("uz") == ("uz", False))

print("\n2) Foydalanuvchi va bazadagi til")
from database.models import User
user = User(1, 2, None, None, "kk", 0, None, None, None, 0, "", "")
check("bazadagi 'kk' → language 'ru' + kazakh", user.language == "ru" and user.kazakh is True, (user.language, user.kazakh))
plain = User(1, 2, None, None, "uz", 0, None, None, None, 0, "", "")
check("boshqa tillar o'zgarmaydi", plain.language == "uz" and plain.kazakh is False)

print("\n3) Middleware")
from bot.middlewares import LanguageMiddleware
async def run_middleware(db_user):
    seen = {}
    async def handler(event, data):
        seen["text"] = T.get_text(data["user_lang"], "main_menu.help"); seen["lang"] = data["user_lang"]
        return "ok"
    db = MagicMock()
    db.get_user = AsyncMock(return_value=db_user)
    db.get_feature_status = AsyncMock(return_value=True)
    event = SimpleNamespace(from_user=SimpleNamespace(id=2))
    await LanguageMiddleware()(handler, event, {"db": db})
    return seen
seen = asyncio.run(run_middleware(user))
check("qozoq foydalanuvchi: user_lang 'ru', matn qozoqcha", seen == {"text": "📞 Көмек", "lang": "ru"}, seen)
seen = asyncio.run(run_middleware(plain))
check("o'zbek foydalanuvchi: matn o'zbekcha", seen["text"] == "📞 Yordam", seen)
check("middleware tugagach belgi tozalanadi (keyingi so'rovga o'tmaydi)", T.get_text("ru", "main_menu.help") == "📞 Помощь")

print("\n4) Tugmalar va filtrlar")
from bot import keyboards
from bot.handlers import documents, payments, settings, samples, project_work, book_translate, premium_presentation
texts = lambda kb: [b.text for row in kb.inline_keyboard for b in row]
check("til tanlash tugmasida qozoqcha", "lang_kk" in [b.callback_data for row in keyboards.get_language_keyboard().inline_keyboard for b in row])
doc_kb = keyboards.get_doc_language_keyboard("ru")
check("hujjat tili tugmasida qozoqcha", "doc_lang_kk" in [b.callback_data for row in doc_kb.inline_keyboard for b in row])
check("kitob tarjimasi: qozoq tiliga", "bt_lang_kk" in [b.callback_data for row in keyboards.get_book_translate_lang_keyboard("uz").inline_keyboard for b in row])
checks = {
    "Sozlamalar": ("main_menu.settings", settings.SETTINGS_TEXTS),
    "To'lov": ("main_menu.payment", payments.PAYMENT_TEXTS),
    "Hisob": ("main_menu.my_account", payments.ACCOUNT_TEXTS),
    "Referal": ("main_menu.referral", payments.REFERRAL_TEXTS),
    "Namunalar": ("main_menu.samples", samples.SAMPLES_TEXTS),
    "Loyiha ishi": ("main_menu.project_work", project_work.MENU_TEXTS),
    "Yordam": ("main_menu.help", documents.HELP_BUTTON_TEXTS),
    "Boshqa xizmatlar": ("main_menu.other_services", documents.OTHER_SERVICES_BUTTON_TEXTS),
    "Taqdimot": ("main_menu.presentation", premium_presentation.ENTRY_TEXTS),
    "Zamonaviy taqdimot": ("main_menu.premium_presentation", premium_presentation.ENTRY_TEXTS),
    "Kitob tarjimasi": ("main_menu.book_translate", list(book_translate.BOOK_TRANSLATE_TEXTS.values())),
}
for name, (key, texts_list) in checks.items():
    label = KK["main_menu"][key.split(".")[1]]
    check(f"qozoqcha «{name}» tugmasi filtrga kiradi", label in texts_list, label)
for key, kind in (("independent_work", "independent_work"), ("referat", "referat"), ("course_work", "course_work"),
                  ("diploma_work", "bitiruv_ishi"), ("tezis", "tezis"), ("maqola", "maqola")):
    label = KK["main_menu"][key]
    check(f"qozoqcha «{label}» hujjat turiga o'tadi", documents.DOCUMENT_TYPES.get(label) == kind, label)
from bot.middlewares import CommandResetMiddleware
labels = CommandResetMiddleware.menu_labels()
check("menyu tugmasi bosilsa holat tozalanadi (qozoqcha ham)", KK["main_menu"]["settings"] in labels and KK["main_menu"]["help"] in labels)
main_kb = keyboards.get_main_keyboard("ru")
with T.kazakh_scope(True):
    kz_main = keyboards.get_main_keyboard("ru")
check("bosh menyu: qozoq foydalanuvchiga qozoqcha tugmalar",
      KK["main_menu"]["settings"] in [b.text for row in kz_main.keyboard for b in row]
      and KK["main_menu"]["settings"] not in [b.text for row in main_kb.keyboard for b in row])
direct = keyboards.get_slide_count_keyboard("kk")
check("klaviaturaga 'kk' to'g'ridan-to'g'ri berilsa — o'zbekcha emas", "слайд" in " ".join(texts(direct)) and "slayd" not in " ".join(texts(direct)), texts(direct))
check("hajm so'rovi qozoqcha", "Бет санын" in documents._count_prompt("kk", "pages"))

print("\n5) Mavzu tili")
check("qozoqcha mavzu → kk", documents._topic_language("Қазақстан экономикасының даму бағыттары") == "kk")
check("o'zbek kirill → uz", documents._topic_language("Ўзбекистон иқтисодиётининг ривожланиши ҳақида") == "uz")
check("ruscha → ru", documents._topic_language("Развитие экономики Республики Казахстан") == "ru")

print("\n6) Qozoqcha yorliqlar")
cases = {"Введение": "Кіріспе", "ЗАКЛЮЧЕНИЕ": "ҚОРЫТЫНДЫ", "Рисунок 3": "3-сурет", "Таблица 12": "12-кесте",
         "Спасибо за внимание!": "Назарларыңызға рахмет!", "Список использованной литературы": "Пайдаланылған әдебиеттер тізімі",
         "Тема: ": "Тақырыбы: ", "1. Введение": "1. Кіріспе", "Введение\t.....3": "Кіріспе\t.....3",
         "____ УНИВЕРСИТЕТ": "____ УНИВЕРСИТЕТІ", "Выполнил(а):\tАли": "Орындаған:\tАли"}
for source, expected in cases.items():
    check(f"{source!r} → {expected!r}", kazakh_doc.translate_loose(source) == expected, kazakh_doc.translate_loose(source))
body = "Введение в экономику — это наука о том, как люди принимают решения."
check("jumla ichidagi ruscha so'z o'zgarmaydi (faqat butun yorliq)", kazakh_doc.translate_loose(body) == body)
check("modelning qozoqcha matni o'zgarmaydi", kazakh_doc.translate("Қорытынды") == "Қорытынды")

print("\n7) Model so'rovi")
messages = [{"role": "user", "content": "Напишите введение на русском языке. Translate into Russian."}]
check("qoida yoqilmaguncha so'rov o'zgarmaydi", kazakh_doc.with_rule(messages) == messages)
token = kazakh_doc.use(True)
ruled = kazakh_doc.with_rule(messages)
kazakh_doc.reset(token)
check("qozoq qoidasi qo'shildi", kazakh_doc.RULE in ruled[0]["content"])
check("'на русском языке' → 'на казахском языке'", "на казахском языке" in ruled[0]["content"] and "на русском" not in ruled[0]["content"])
check("'Russian' → 'Kazakh'", "into Kazakh" in ruled[0]["content"])
check("asl xabar o'zgartirilmadi", "Russian" in messages[0]["content"])

print("\n8) Servis metodlarini o'rash")
class Fake:
    async def make(self, topic, language, content=None):
        Fake.seen = (language, kazakh_doc.active(), (content or {}).get("language"))
        return {"title": "Введение", "language": language}
    def sync(self, language="uz"):
        return ["Заключение", language]
kazakh_doc.wrap_class(Fake)
fake = Fake()
data = {"language": "kk"}
result = asyncio.run(fake.make("t", "kk", content=data))
check("ichkarida 'ru' va qoida yoqiq", Fake.seen == ("ru", True, "ru"), Fake.seen)
check("natija qozoqchaga o'girildi va til 'kk'", result == {"title": "Кіріспе", "language": "kk"}, result)
check("mijoz lug'ati qaytarib 'kk' qilindi", data["language"] == "kk")
check("tashqarida qoida o'chiq", kazakh_doc.active() is False)
check("boshqa tillarga tegmaydi", asyncio.run(fake.make("t", "uz")) == {"title": "Введение", "language": "uz"} and Fake.seen[0] == "uz" and Fake.seen[1] is False)
check("sinxron metod ham", fake.sync("kk") == ["Қорытынды", "ru"], fake.sync("kk"))

print("\n9) Referat (soxta model)")
from services import ai_service as ais, document_service as ds
from docx import Document
KK_TEXT = ("Қазақстанның экономикалық дамуы әлемдік нарықтағы орнын нығайтуға ықпал етеді. "
           "Бұл үдеріс ұлттық өндірістің тұрақтылығын қамтамасыз етеді және инновацияны ынталандырады. ") * 40
prompts = []
async def create(**kw):
    text = "\n".join(m["content"] for m in kw["messages"]); prompts.append(text)
    if '"sections"' in text and "JSON" in text:
        out = json.dumps({"sections": ["Кіріспе", "Теориялық негіздер", "Қазіргі жағдайды талдау", "Даму перспективалары", "Қорытынды"]}, ensure_ascii=False)
    elif '"references"' in text:
        out = json.dumps({"references": ["Назарбаев Н. Қазақстан жолы. Астана: Елорда, 2019.", "Әбілқасымов Б. Экономика негіздері. Алматы: Қазақ университеті, 2020."]}, ensure_ascii=False)
    else:
        out = KK_TEXT
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=out), finish_reason="stop")])
ai = ais.AIService.__new__(ais.AIService)
ai.client = MagicMock(); ai.client.chat.completions.create = create
ai._get_current_model_id = AsyncMock(return_value="m")
topic = "Қазақстан экономикасының дамуы"

async def build_referat():
    content = await ai.generate_document_content(topic, 5, "referat", "kk", 10, 15)
    content["language"] = "kk"; content["author_name"] = "Серіков Алмас"
    service = ds.DocumentService.__new__(ds.DocumentService)
    service.documents_dir = tempfile.mkdtemp(); service.temp_dir = tempfile.mkdtemp(); service.use_icons = False
    service._last_used_icons = set(); service.together = AsyncMock()
    return content, await service.create_referat(topic, content, extras=None)
content, path = asyncio.run(build_referat())
lines = [p.text for p in Document(path).paragraphs if p.text.strip()]
joined = "\n".join(lines)
check("barcha so'rovlarda qozoq qoidasi bor", prompts and all(kazakh_doc.RULE in text for text in prompts), len(prompts))
check("so'rovda 'на русском' qolmadi", not any("на русском" in text for text in prompts))
check("titul varag'i qozoqcha (Қазақстан, РЕФЕРАТ, Тақырыбы, Орындаған)",
      all(word in joined for word in ("ҚАЗАҚСТАН РЕСПУБЛИКАСЫ", "РЕФЕРАТ", "Тақырыбы", "Орындаған", "Қабылдаған", "УНИВЕРСИТЕТІ")), lines[:12])
check("Ўзбекистон ramzi/yozuvi yo'q", "УЗБЕКИСТАН" not in joined.upper() and "O'ZBEKISTON" not in joined.upper())
check("mundarija: ЖОСПАР, Кіріспе, Қорытынды, Пайдаланылған әдебиеттер",
      "ЖОСПАР" in joined and re.search(r"^Кіріспе\t\d+", joined, re.M) and re.search(r"^Қорытынды\t\d+", joined, re.M)
      and re.search(r"^Пайдаланылған әдебиеттер\t\d+", joined, re.M), [l for l in lines if "\t" in l][:8])
check("adabiyotlar sarlavhasi qozoqcha", "ПАЙДАЛАНЫЛҒАН ӘДЕБИЕТТЕР" in joined)
check("ruscha qat'iy yorliq qolmadi", not re.search(r"Введение|Заключение|Список|Литература|Содержание|СОДЕРЖАНИЕ|Выполнил|Принял", joined))
check("matn qozoqcha (modeldan)", "Қазақстанның экономикалық дамуы" in joined)
check("kontent tili 'kk' qoldi (keyingi qadamlar uchun)", content.get("language") == "kk")

print("\n10) Premium taqdimot jadvallari")
from services.premium_presentation import html_slides, llm_client, deck_logic
check("til talabi: qozoqcha", "kk" in html_slides._LANGUAGE and "kk" in llm_client.PRESENTATION_LANGUAGE_INSTRUCTIONS)
check("xulosa, reja, muallif yorlig'i qozoqcha", "kk" in html_slides._CONCLUSION_BRIEF and "kk" in deck_logic.PLAN_LABEL
      and "kk" in html_slides._CREDIT_LABEL and "kk" in html_slides._ESTIMATE)
check("reja slaydi qozoqcha sarlavhali", "Презентация жоспары" in deck_logic.plan_slide([("Бірінші бөлім", "Мәтін")], "kk"))
check("reja sarlavhasi qozoqcha tanilmaydi → takror emas", deck_logic.is_plan_title("Жоспар") and deck_logic.is_plan_title("Презентация жоспары"))
from services import timeframe
check("yil qoidasi 'kk' da ham ishlaydi", "2026" in timeframe.year_rule("kk") or str(timeframe.current_year()) in timeframe.year_rule("kk"))
from utils.ai_text import token_budget
plain_budget = token_budget("300-400", "ru")
_token = kazakh_doc.use(True); kk_budget = token_budget("300-400", "ru"); kazakh_doc.reset(_token)
check("tokenlar byudjeti qozoqchada kattaroq (so'zlar ko'p bo'lakka bo'linadi)", kk_budget > plain_budget, (plain_budget, kk_budget))

print("\n11) Kitob tarjimasi")
from services import book_translate_service as bts, book_pdf_translate as bpt
check("qozoq tili ro'yxatda", "kk" in bts.LANG_NAMES and "kk" in bts.LANG_SUFFIXES and "kk" in bpt.LANG_NAMES)
check("qozoqcha matn manba tili sifatida aniqlanadi", bpt.detect_language("Қазақстанның ғылыми дамуы әлемдік үрдістерге сәйкес келеді. " * 40) == "kk")
check("ruscha matn 'ru' qoladi", bpt.detect_language("Развитие экономики страны определяется множеством факторов. " * 40) == "ru")

print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
