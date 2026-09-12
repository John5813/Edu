"""Hozir nechta og'ir ish bajarilayotganini sanaydi.

Botni qayta ishga tushirish ishlab turgan generatsiyani uzib qo'yadi, mijoz
esa buning uchun pul to'lagan. Shuning uchun admin paneldagi yangilash
tugmasi avval shu yerdan so'raydi.

Hujjat navbati o'z holatini biladi, lekin premium taqdimot ham, loyiha ishi
ham navbatdan tashqarida ishlaydi — ular alohida sanalmasa, "hozir hech
narsa bajarilmayapti" degan noto'g'ri javob chiqardi.

Hisoblagich faqat xotirada: qayta ishga tushgach nolga qaytadi, bu esa
to'g'ri — uzilgan ishlar baribir davom etmaydi.
"""

import contextlib
import itertools
import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_running: dict = {}
_counter = itertools.count(1)


@contextlib.contextmanager
def track(label: str):
    """Og'ir ish davomida uni ro'yxatga qo'yadi.

    Xato yuz bersa ham ro'yxatdan chiqadi — aks holda bitta yiqilgan
    generatsiya "hamisha band" holatini qoldirardi va yangilash tugmasi
    boshqa ishlamasdi.
    """
    key = next(_counter)
    with _lock:
        _running[key] = label
    try:
        yield
    finally:
        with _lock:
            _running.pop(key, None)


def begin(label: str) -> int:
    """`track` ishlatib bo'lmaydigan joylar uchun — masalan katta `try`
    blokini qayta chekinishga tekkizmaslik kerak bo'lganda.

    Qaytgan raqam `end` ga beriladi; chaqiruvchi buni `finally` ichida
    bajarishi shart.
    """
    key = next(_counter)
    with _lock:
        _running[key] = label
    return key


def end(key: int) -> None:
    with _lock:
        _running.pop(key, None)


def active() -> int:
    with _lock:
        return len(_running)


def labels() -> list:
    """Hozir nima bajarilayapti — admin ko'radigan ro'yxat."""
    with _lock:
        return list(_running.values())
