"""Hozir nechta og'ir ish bajarilayotganini sanaydi.

Botni qayta ishga tushirish ishlab turgan generatsiyani uzib qo'yadi, mijoz
esa buning uchun pul to'lagan. Shuning uchun admin paneldagi yangilash
tugmasi avval shu yerdan so'raydi.

Hujjat navbati o'z holatini biladi, lekin premium taqdimot ham, loyiha ishi
ham navbatdan tashqarida ishlaydi — ular alohida sanalmasa, "hozir hech
narsa bajarilmayapti" degan noto'g'ri javob chiqardi.

Hisoblagich faqat xotirada: qayta ishga tushgach nolga qaytadi, bu esa
to'g'ri — uzilgan ishlar baribir davom etmaydi.

Har yozuv boshlanish vaqtini ham saqlaydi. Sabab: generatsiya bosqichi
javob bermay qolsa (tarmoq uzilsa, tashqi xizmat osilib qolsa) ish
tugamaydi va yozuv abadiy qolib ketardi — o'sha paytda hech narsa
yaratilmayotgan bo'lsa ham admin panel "hozir ish bajarilmoqda" deb
turaverar va yangilash tugmasi umuman ishlamasdi. Endi belgilangan
vaqtdan oshgan yozuv "javob bermayapti" deb belgilanadi: u ro'yxatda
ko'rinadi, lekin yangilashni to'xtatmaydi.
"""

import contextlib
import itertools
import logging
import threading
import time

logger = logging.getLogger(__name__)

# Shu vaqtdan oshgan ish tirik hisoblanmaydi. Eng uzun premium taqdimot
# ham yigirma daqiqada tugaydi; undan oshgani osilib qolgan.
STALE_AFTER = 25 * 60

_lock = threading.Lock()
_running: dict = {}          # {kalit: (nom, boshlangan_vaqt)}
_counter = itertools.count(1)


@contextlib.contextmanager
def track(label: str):
    """Og'ir ish davomida uni ro'yxatga qo'yadi.

    Xato yuz bersa ham ro'yxatdan chiqadi — aks holda bitta yiqilgan
    generatsiya "hamisha band" holatini qoldirardi va yangilash tugmasi
    boshqa ishlamasdi.
    """
    key = begin(label)
    try:
        yield
    finally:
        end(key)


def begin(label: str) -> int:
    """`track` ishlatib bo'lmaydigan joylar uchun — masalan katta `try`
    blokini qayta chekinishga tekkizmaslik kerak bo'lganda.

    Qaytgan raqam `end` ga beriladi; chaqiruvchi buni `finally` ichida
    bajarishi shart.
    """
    key = next(_counter)
    with _lock:
        _running[key] = (label, time.time())
    return key


def end(key: int) -> None:
    with _lock:
        _running.pop(key, None)


def snapshot() -> list:
    """Hamma yozuv: [(nom, necha soniyadan beri, tirikmi), ...]."""
    now = time.time()
    with _lock:
        items = list(_running.values())
    return [(label, now - started, (now - started) < STALE_AFTER)
            for label, started in items]


def active() -> int:
    """Haqiqatan bajarilayotgan ishlar soni — osilib qolganlari sanalmaydi."""
    return sum(1 for _label, _age, alive in snapshot() if alive)


def stale() -> int:
    """Javob bermay qolgan yozuvlar soni."""
    return sum(1 for _label, _age, alive in snapshot() if not alive)


def labels() -> list:
    """Hozir nima bajarilayapti — admin ko'radigan ro'yxat."""
    return [label for label, _age, _alive in snapshot()]


def describe() -> list:
    """Admin uchun tavsif: nomi, qancha vaqtdan beri, holati."""
    lines = []
    for label, age, alive in snapshot():
        minutes = int(age // 60)
        since = f"{minutes} daqiqadan beri" if minutes else "hozirgina boshlandi"
        lines.append(f"{label} — {since}" if alive
                     else f"{label} — {since}, javob bermayapti")
    return lines


def drop_stale() -> int:
    """Osilib qolgan yozuvlarni ro'yxatdan olib tashlaydi.

    Yozuvni o'chirish ishning o'zini to'xtatmaydi (u alohida oqimda
    qolishi mumkin), lekin u allaqachon tugamaydigan bo'lib qolgan:
    mijozga xato xabari ketgan yoki ketadi.
    """
    now = time.time()
    with _lock:
        dead = [key for key, (_label, started) in _running.items()
                if now - started >= STALE_AFTER]
        for key in dead:
            label, started = _running.pop(key)
            logger.warning("Osilib qolgan ish ro'yxatdan olindi: %s (%.0f daqiqa)",
                           label, (now - started) / 60)
    return len(dead)
