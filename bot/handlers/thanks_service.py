"""«🟩 Boshqa professional xizmatlar» → «🎬 Personaj qo'shish» — BEPUL, faqat Telegram botida.

Mijoz tugmani bosadi → taqdimotdagi o'sha mini ilova (personajlar, `/anim?mode=add`) darhol ochiladi → personajni
tanlaydi → mini ilova `/start thxadd_<kalit>` bilan botga qaytaradi → bot tayyor taqdimotni (.pptx) so'raydi →
mijoz o'z faylini yuboradi → oxiriga tanlangan personajli animatsiyali «Rahmat» sahifasi qo'shilib, fayl qaytariladi.

Istalgan PPTX bo'ladi: 4:3, A4 yoki boshqa o'lchamdagi sahifaga ham sahifa moslashtiriladi (`thanks_anim.slide._fit`).
Pul yechilmaydi, balans tekshirilmaydi.
"""
import asyncio
import contextlib
import html
import logging
import os
import shutil
import tempfile

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message,
                           WebAppInfo)

from bot.states import ThanksAddStates

router = Router()
log = logging.getLogger(__name__)

MAX_MB = 20                 # Telegram bot 20 MB dan katta faylni yuklab ololmaydi
CB_CANCEL = "thxadd:cancel"

TXT = {
    "uz": {
        "send": ("🎬 Tanlandi: <b>{name}</b>\n\nEndi taqdimotingizni (<b>.pptx</b> fayl) shu yerga yuboring — "
                 "oxiriga shu personajli animatsiyali «Rahmat» sahifasi qo'shiladi. Bu <b>bepul</b>."),
        "other": "🎬 Boshqa personaj", "cancel": "❌ Bekor qilish",
        "cancelled": "Bekor qilindi.",
        "not_pptx": "📎 Faqat PowerPoint taqdimoti (<b>.pptx</b>) yuboring. Eski .ppt bo'lsa — PowerPoint'da .pptx qilib saqlang.",
        "big": "⚠️ Fayl {mb} MB — Telegram bot {limit} MB dan katta faylni qabul qila olmaydi. Rasmlarini siqib, qayta yuboring.",
        "work": "⏳ Personaj qo'shilmoqda… (bir daqiqagacha)",
        "done": "✅ Tayyor! Oxirgi sahifaga «{name}» personaji qo'shildi.",
        "bad": "❌ Faylni ochib bo'lmadi. Taqdimot buzilmaganini tekshirib, qayta yuboring.",
        "expired": "Bu tanlov eskirgan. «🟩 Boshqa professional xizmatlar» → «🎬 Personaj qo'shish» ni qayta bosing.",
    },
    "ru": {
        "send": ("🎬 Выбрано: <b>{name}</b>\n\nТеперь отправьте свою презентацию (файл <b>.pptx</b>) — в конец "
                 "добавится анимированная страница «Спасибо» с этим персонажем. Это <b>бесплатно</b>."),
        "other": "🎬 Другой персонаж", "cancel": "❌ Отмена",
        "cancelled": "Отменено.",
        "not_pptx": "📎 Отправьте только презентацию PowerPoint (<b>.pptx</b>). Если файл .ppt — сохраните его в PowerPoint как .pptx.",
        "big": "⚠️ Файл {mb} МБ — бот Telegram не принимает файлы больше {limit} МБ. Сожмите картинки и отправьте снова.",
        "work": "⏳ Добавляю персонажа… (до минуты)",
        "done": "✅ Готово! На последнюю страницу добавлен персонаж «{name}».",
        "bad": "❌ Не удалось открыть файл. Проверьте, что презентация не повреждена, и отправьте снова.",
        "expired": "Этот выбор устарел. Снова нажмите «🟩 Другие профессиональные услуги» → «🎬 Добавить персонажа».",
    },
    "en": {
        "send": ("🎬 Selected: <b>{name}</b>\n\nNow send your presentation (a <b>.pptx</b> file) — an animated "
                 "“Thank you” page with this character will be added to the end. It is <b>free</b>."),
        "other": "🎬 Another character", "cancel": "❌ Cancel",
        "cancelled": "Cancelled.",
        "not_pptx": "📎 Please send a PowerPoint presentation (<b>.pptx</b>). If it is .ppt, save it as .pptx in PowerPoint.",
        "big": "⚠️ The file is {mb} MB — a Telegram bot can't take files over {limit} MB. Compress the pictures and send it again.",
        "work": "⏳ Adding the character… (up to a minute)",
        "done": "✅ Done! The “{name}” character was added to the last page.",
        "bad": "❌ Couldn't open the file. Make sure the presentation isn't damaged and send it again.",
        "expired": "This choice has expired. Tap «🟩 Other Professional Services» → «🎬 Add a character» again.",
    },
    "kk": {
        "send": ("🎬 Таңдалды: <b>{name}</b>\n\nЕнді презентацияңызды (<b>.pptx</b> файл) жіберіңіз — соңына осы "
                 "кейіпкері бар анимациялы «Рахмет» беті қосылады. Бұл <b>тегін</b>."),
        "other": "🎬 Басқа кейіпкер", "cancel": "❌ Болдырмау",
        "cancelled": "Болдырылмады.",
        "not_pptx": "📎 Тек PowerPoint презентациясын (<b>.pptx</b>) жіберіңіз. Файл .ppt болса — PowerPoint-та .pptx етіп сақтаңыз.",
        "big": "⚠️ Файл {mb} МБ — Telegram боты {limit} МБ-тан үлкен файлды қабылдай алмайды. Суреттерді сығып, қайта жіберіңіз.",
        "work": "⏳ Кейіпкер қосылуда… (бір минутқа дейін)",
        "done": "✅ Дайын! Соңғы бетке «{name}» кейіпкері қосылды.",
        "bad": "❌ Файлды ашу мүмкін болмады. Презентацияның бүтін екенін тексеріп, қайта жіберіңіз.",
        "expired": "Бұл таңдау ескірген. «🟩 Басқа кәсіби қызметтер» → «🎬 Кейіпкер қосу» түймесін қайта басыңыз.",
    },
}


def _lang(user_lang: str) -> str:
    return user_lang if user_lang in TXT else "uz"


def _t(user_lang: str) -> dict:
    return TXT[_lang(user_lang)]


def _markup(user_lang: str) -> InlineKeyboardMarkup:
    from services.thanks_anim import picker
    t = _t(user_lang)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["other"], web_app=WebAppInfo(url=picker.add_service_url(user_lang)))],
        [InlineKeyboardButton(text=t["cancel"], callback_data=CB_CANCEL)]])


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("thxadd_")))
async def thanks_chosen(message: Message, command: CommandObject, state: FSMContext, user_lang: str):
    """Mini ilovada personaj tanlandi: endi taqdimot fayli so'raladi."""
    from services.thanks_anim import catalog, picker

    key = (command.args or "")[len(picker.ADD_PREFIX):]
    with contextlib.suppress(Exception):                # «/start …» xabari suhbatda qolmasin
        await message.delete()
    t = _t(user_lang)
    if key == picker.NO_KEY:
        await state.clear()
        await message.answer(t["cancelled"])
        return
    if catalog.get(key) is None:
        await message.answer(t["expired"])
        return
    await state.clear()
    await state.set_state(ThanksAddStates.waiting_for_file)
    await state.update_data(thanks_key=key)
    await message.answer(t["send"].format(name=html.escape(picker.name_of(key, user_lang))),
                         parse_mode="HTML", reply_markup=_markup(user_lang))


@router.callback_query(F.data == CB_CANCEL)
async def thanks_cancel(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    if await state.get_state() == ThanksAddStates.waiting_for_file.state:
        await state.clear()
    with contextlib.suppress(Exception):
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(_t(user_lang)["cancelled"])


def _apply(src: str, out_dir: str, key: str, name: str, language: str) -> str:
    """Faylga «Rahmat» sahifasini qo'shadi (alohida oqimda). Qaytaradi: tayyor fayl yo'li."""
    from services import heavy_gate
    from services.thanks_anim import picker

    target = os.path.join(out_dir, name)
    shutil.copyfile(src, target)
    with heavy_gate.slot("Rahmat sahifasi (personaj qo'shish)", heavy_gate.OFFICE_MB):
        done = picker.apply(target, key, topic=os.path.splitext(name)[0], style="", volume="kop", theme_key="",
                            language=language, author="")
    if not done:
        raise RuntimeError("personaj qo'shilmadi")
    return target


def _out_name(file_name: str) -> str:
    base = os.path.splitext(os.path.basename(file_name or ""))[0].strip() or "Taqdimot"
    return base[:80] + ".pptx"


@router.message(ThanksAddStates.waiting_for_file, F.document)
async def thanks_file(message: Message, state: FSMContext, user_lang: str):
    from services.thanks_anim import picker

    t = _t(user_lang)
    doc = message.document
    name = doc.file_name or ""
    if not name.lower().endswith(".pptx"):
        await message.answer(t["not_pptx"], parse_mode="HTML")
        return
    if (doc.file_size or 0) > MAX_MB * 1024 * 1024:
        await message.answer(t["big"].format(mb=round(doc.file_size / 1048576, 1), limit=MAX_MB))
        return
    key = (await state.get_data()).get("thanks_key") or ""
    work_msg = await message.answer(t["work"])
    work = tempfile.mkdtemp(prefix="thxadd_")
    try:
        src = os.path.join(work, "in.pptx")
        await message.bot.download(doc, destination=src)
        out_dir = os.path.join(work, "out")
        os.makedirs(out_dir)
        try:
            path = await asyncio.to_thread(_apply, src, out_dir, key, _out_name(name), _lang(user_lang))
        except Exception as exc:
            log.warning("Personaj qo'shilmadi (%s, %s): %s", message.from_user.id, name, exc)
            await message.answer(t["bad"])
            return                                      # holat qoladi: mijoz boshqa faylni yuborishi mumkin
        caption = t["done"].format(name=html.escape(picker.name_of(key, user_lang))) + "\n\n" + html.escape(picker.note(user_lang))
        await message.answer_document(FSInputFile(path, filename=os.path.basename(path)), caption=caption[:1024],
                                      parse_mode="HTML")
        await state.clear()
    finally:
        with contextlib.suppress(Exception):
            await work_msg.delete()
        shutil.rmtree(work, ignore_errors=True)


@router.message(ThanksAddStates.waiting_for_file, ~F.text)
async def thanks_wrong(message: Message, user_lang: str):
    """Fayl kutilmoqda, lekin rasm, video va h.k. keldi: eslatiladi. Matn (menyu tugmalari) o'z joyiga o'tadi."""
    await message.answer(_t(user_lang)["not_pptx"], parse_mode="HTML", reply_markup=_markup(user_lang))
