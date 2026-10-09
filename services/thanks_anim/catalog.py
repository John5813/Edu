""""Rahmat" sahifasiga qo'yiladigan animatsiyalar ro'yxati.

Fayllar `assets/thanks_anim/<key>/` da (`tools/thanks_anim/prepare.py` yasaydi): `packed.mp4` — taqdimot
uchun manba, `preview.mp4` va `poster.jpg` — mini oyna uchun.
"""
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(ROOT, "assets", "thanks_anim")


@dataclass(frozen=True)
class Animation:
    key: str
    names: Dict[str, str]
    source: str                 # xom video (faqat tayyorlashda kerak)
    start: float = 0.0
    seconds: float = 0.0        # 0 — butun video (10 soniyagacha)
    similarity: float = 0.2     # yashil fonni ajratish chegarasi

    def name(self, lang: str) -> str:
        return self.names.get(lang) or self.names["uz"]

    def path(self, name: str) -> str:
        return os.path.join(ASSETS, self.key, name)

    @property
    def ready(self) -> bool:
        return all(os.path.exists(self.path(n)) for n in ("packed.mp4", "preview.mp4"))


def _a(key, uz, ru, en, source, **kw):
    return Animation(key, {"uz": uz, "ru": ru, "en": en}, source, **kw)


ANIMATIONS: List[Animation] = [
    _a("anime_qiz", "Anime qiz", "Аниме-девочка", "Anime girl", "m16.mp4"),
    _a("pul_mushuk", "Pul sanayotgan mushuk", "Кот считает деньги", "Cat counting money", "m10.mp4"),
    _a("hamster", "Hamster", "Хомяк", "Hamster", "m01.mp4"),
    _a("parik_hamster", "Pariklik hamster", "Хомяк в парике", "Hamster in a wig", "m04.mp4"),
    _a("raqs_mushuk", "Raqsga tushayotgan mushuk", "Танцующий кот", "Dancing cat", "m06.mp4"),
    _a("mushukchalar", "Ikki mushukcha", "Два котёнка", "Two kittens", "m11.mp4"),
    _a("kuchukcha", "Raqqosa kuchukcha", "Танцующий щенок", "Dancing puppy", "m12.mp4"),
    _a("paxmoq", "Paxmoq", "Пушистик", "Fluffy", "m09.mp4"),
    _a("timsoh", "Raqsga tushayotgan timsoh", "Танцующий крокодил", "Dancing crocodile", "m14.mp4"),
    _a("robot", "Robot", "Робот", "Robot", "m05.mp4"),
    _a("pul_yomgiri", "Pul yomg'iri", "Денежный дождь", "Money rain", "m15.mp4"),
    _a("kok_bolakay", "Ko'k bolakay", "Малыш в синем", "Kid in blue", "m02.mp4"),
    _a("oshpaz", "Oshpaz", "Повар", "Chef", "m07.mp4"),
    _a("qahramon", "Qahramon", "Герой", "Hero", "m08.mp4"),
    _a("qizcha", "Qizcha", "Девочка", "Little girl", "m13.mp4"),
]
BY_KEY = {a.key: a for a in ANIMATIONS}


def available() -> List[Animation]:
    return [a for a in ANIMATIONS if a.ready]


def get(key: str) -> Optional[Animation]:
    anim = BY_KEY.get(key or "")
    return anim if anim and anim.ready else None
