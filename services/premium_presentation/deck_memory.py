"""Taqdimot xotirasi: bitta taqdimot yozilayotganda AI oldin yozganlarini chatdagidek ko'rib turadi.

Slaydlar 3 tadan bo'laklab yoziladi. Ilgari har bo'lak oldingi slaydlarning faqat sarlavhasini ko'rardi:
model 9-slaydda nima deyilganini bilmay, 10-slaydda boshqa davrga sakrab yoki o'sha faktni boshqa raqam bilan
qayta aytib yuborardi. Endi har so'rovda oldingi bo'laklar suhbat tarixi sifatida ketadi
(foydalanuvchi: «N-slayddan boshlab ...» → assistent: o'sha slaydlar), qayta yozilgan slayd tarixda ham
yangilanadi.

Xotira bitta taqdimotga tegishli (`session()`): taqdimot mijozga yetib borishi bilan (yaratish tugaganda)
o'chadi va boshqa buyurtmalarga o'tmaydi — har buyurtma o'z oqimida (`contextvars`) ishlaydi.
"""
import contextlib
import contextvars
import re
from typing import Dict, List, Optional

# Tarixning taxminiy chegarasi (belgi). Undan oshsa eng eski bo'laklar HTML o'rniga qisqa matn bo'lib
# qoladi: mazmun (sarlavha, fakt, sana, raqam) saqlanadi, so'rov esa haddan oshib ketmaydi.
MAX_CHARS = 30000
PLAIN_LIMIT = 600            # qisqartirilgan slayd matni (belgi)

_CURRENT: contextvars.ContextVar = contextvars.ContextVar("deck_memory", default=None)

_SVG = re.compile(r"(<svg\b[^>]*>).*?</svg>", re.IGNORECASE | re.DOTALL)
_DATA_URI = re.compile(r"data:[^\"'\s)]{200,}", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_TITLE = re.compile(r"<h[12]\b[^>]*>(.*?)</h[12]>", re.IGNORECASE | re.DOTALL)
_SPACE = re.compile(r"\s+")


def compact(body: str) -> str:
    """Slayd HTML'i tarix uchun: ikonka chizmalari va ichiga joylangan rasmlarsiz (mazmun o'zgarmaydi)."""
    text = _SVG.sub(r"\1</svg>", body or "")
    text = _DATA_URI.sub("data:…", text)
    return _SPACE.sub(" ", text).strip()


def plain(body: str, number: int) -> str:
    """Slaydning qisqa matn ko'rinishi: «N. Sarlavha — matn»."""
    match = _TITLE.search(body or "")
    title = _SPACE.sub(" ", _TAG.sub(" ", match.group(1))).strip() if match else ""
    text = _SPACE.sub(" ", _TAG.sub(" ", body or "")).strip()
    if title and text.startswith(title):
        text = text[len(title):].strip()
    if len(text) > PLAIN_LIMIT:
        text = text[:PLAIN_LIMIT].rsplit(" ", 1)[0] + " …"
    return f"{number}. {title} — {text}" if title else f"{number}. {text}"


class Memory:
    """Bitta taqdimotning suhbat tarixi."""

    def __init__(self):
        self.turns: List[Dict] = []          # [{"ask": str, "numbers": [int, ...]}] — yozilish tartibida
        self.slides: Dict[int, str] = {}     # slayd raqami -> joriy (oxirgi) HTML

    def remember(self, first: int, bodies: List[str], ask: str) -> None:
        """`first`-slayddan boshlab yozilgan slaydlar. Allaqachon bor slayd yangilanadi, yangisi — yangi navbat."""
        fresh = []
        for offset, body in enumerate(bodies):
            number = first + offset
            if number not in self.slides:
                fresh.append(number)
            self.slides[number] = body
        if fresh:
            self.turns.append({"ask": ask, "numbers": fresh})

    def update(self, number: int, body: str) -> None:
        """Qayta yozilgan slayd: tarixda ham yangi varianti turadi (eski varianti chalg'itmasin)."""
        if number in self.slides and body:
            self.slides[number] = body

    def messages(self) -> List[Dict[str, str]]:
        """Suhbat tarixi: foydalanuvchi so'rovi → assistent yozgan slaydlar, yozilish tartibida."""
        full = [" ".join(compact(self.slides[n]) for n in turn["numbers"]) for turn in self.turns]
        replies = list(full)
        total = sum(len(r) for r in replies)
        # Chegaradan oshsa — eng eskilaridan boshlab qisqa matnga.
        for index, turn in enumerate(self.turns):
            if total <= MAX_CHARS:
                break
            short = "\n".join(plain(self.slides[n], n) for n in turn["numbers"])
            total -= len(replies[index]) - len(short)
            replies[index] = short
        result = []
        for turn, reply in zip(self.turns, replies):
            result.append({"role": "user", "content": turn["ask"]})
            result.append({"role": "assistant", "content": reply})
        return result

    def __bool__(self) -> bool:
        return bool(self.turns)


def current() -> Optional[Memory]:
    return _CURRENT.get()


def history() -> List[Dict[str, str]]:
    """Joriy taqdimotning suhbat tarixi (xotira yo'q yoki bo'sh bo'lsa — bo'sh ro'yxat)."""
    memory = _CURRENT.get()
    return memory.messages() if memory else []


def remember(first: int, bodies: List[str], ask: str) -> None:
    memory = _CURRENT.get()
    if memory is not None and bodies:
        memory.remember(first, bodies, ask)


def update(number: int, body: str) -> None:
    memory = _CURRENT.get()
    if memory is not None:
        memory.update(number, body)


@contextlib.contextmanager
def session():
    """Taqdimot yaratilishi davomidagi xotira. Ichma-ich chaqirilsa tashqi xotira davom etadi."""
    if _CURRENT.get() is not None:
        yield _CURRENT.get()
        return
    memory = Memory()
    token = _CURRENT.set(memory)
    try:
        yield memory
    finally:
        _CURRENT.reset(token)
