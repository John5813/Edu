"""Saytdagi «🧊 3D taqdimot»: mavzu 3D ga mosmi — bitta qaror (to'lovdan oldingi bepul tekshiruv va buyurtma).

Ikki manba bir vaqtda so'raladi: 3D Anatomiya (`services.med3d.auto.check_topic`) va umumiy 3D katalog
(`services.kat3d.qidiruv.top`). Qaror:

1. Mavzu tana tuzilishiga oid (AI tasdiqlagan) — 3D Anatomiya.
2. Katalog «to'liq mos» — katalog modellari bilan 3D taqdimot.
3. Katalog «qisman mos», lekin mavzuning o'zini ko'rsatadigan modellar bor (kamida 1 ta «asosiy», jami kamida
   `MIN_DIRECT` ta bevosita mos model) VA AI mavzuning kamida `PARTIAL_COVERAGE` foizini 3D bilan ko'rsatish
   mumkin deb baholagan — yaratiladi (masalan «Vulqonlar va zilzilalar»: vulqon modellari bor, qamrov 60%).
   Qamrov sharti shart: haqiqiy AI bilan sinovda «Plural Noun» ga AI 5 ta kitobni «asosiy» deb belgiladi
   (qamrov 40%), «Inflyatsiya» ga tarozilarni (35%) — faqat «asosiy» soniga ishonilsa, ular ham o'tib ketardi.
   AI bahosi barqaror emas (keyingi urinishda «Plural Noun» ga 60% berdi), shuning uchun yana bir AI'siz shart:
   bevosita mos modellardan kamida bittasining nomida mavzuning aniq so'zi bor («Vulqonlar» → «Vulqon» modeli;
   «Plural Noun» → «Eski kitob» emas). To'liq mos mavzularga bu shart qo'yilmaydi.
4. Faqat ramziy model, qamrovi past yoki nomi mavzuga mos kelmaydigan qisman mavzu, yoki hech narsa — rad etiladi
   (pul yechilmaydi).
5. Anatomiya tekshiruvi AI'siz o'tgan (javob kelmadi) va katalogda ham hech narsa yo'q — avvalgidek 3D Anatomiya
   (botdagi qoida; to'liq reja tuzilganda mavzu baribir tekshiriladi va mos bo'lmasa pul qaytadi).

Natija bir soat xotirada turadi: mijoz mavzuni yozganda tekshirilgan qaror buyurtmada qayta AI'ga so'ralmaydi va
tekshiruv bilan buyurtma bir-biriga zid chiqmaydi.
"""
import asyncio
import logging
import time
from collections import OrderedDict
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

MIN_DIRECT = 2
PARTIAL_COVERAGE = 50
CACHE_TTL = 3600.0
CACHE_MAX = 500
_cache: "OrderedDict[tuple, tuple]" = OrderedDict()

# 3D tanlanganda mijozga ko'rsatiladigan namuna mavzular — katalogda modellari ko'p yo'nalishlar va 3D Anatomiya.
EXAMPLES = [
    "Inson yuragining tuzilishi",
    "Quyosh tizimi sayyoralari",
    "Dinozavrlar va qazilma hayvonlar",
    "Avtomobil dvigatelining tuzilishi",
    "Dengiz va okean hayvonlari",
    "Qadimgi Misr yodgorliklari",
    "O'zbekiston me'moriy yodgorliklari",
    "Musiqa asboblari",
]

# Matn avvalgidek (saytdagi tarjimalar shu matn bo'yicha); oxiriga «... so'm qaytarildi» qo'shiladi.
NO_3D = "Bu mavzu uchun mos 3D model topilmadi. Infografik yoki Zamonaviy turini tanlang."
UNSURE = ("Hozir mavzuni oldindan tekshirib bo'lmadi. «Yaratish» bosilganda yana tekshiriladi: mos 3D topilmasa, "
          "pul hisobingizga to'liq qaytadi.")


def _named(topic: str, ids) -> bool:
    """Modellardan birining nomida (o'zbekcha yoki asl) mavzuning umumiy bo'lmagan so'zi bormi."""
    from services import katalog3d
    from services.kat3d import qidiruv

    keys = [k for k in dict.fromkeys(qidiruv._tokens(topic)) if k not in qidiruv._FRAME]
    cat = katalog3d.katalog()
    for mid in ids:
        m = cat.get(mid) or {}
        name = qidiruv._tokens(m.get("nom_uz", "") + " " + m.get("nom", ""))
        if any(qidiruv._match(t, k) for t in name for k in keys):
            return True
    return False


def decide(med: dict, kat: dict, topic: str = "") -> dict:
    """Ikki tekshiruv natijasidan qaror: {ok, mode: anatomy|catalog|"", ids, partial, sure}.

    `sure` = False — AI javob bermagan (5-qoida): buyurtma avvalgidek qabul qilinadi, lekin to'lovdan oldingi
    tekshiruv mijozga «mos» deb va'da bermaydi."""
    if med.get("ok") and med.get("checked", True):
        return {"ok": True, "mode": "anatomy", "ids": [], "partial": False, "sure": True}
    level = kat.get("level") or ("full" if kat.get("ok") else "none")
    ids = list(kat.get("ids") or [])
    direct = list(kat.get("direct") or kat.get("asosiy") or [])
    if ids and level == "full":
        return {"ok": True, "mode": "catalog", "ids": ids, "partial": False, "sure": True}
    coverage = kat.get("coverage")              # None — AI javob bermagan (nom bo'yicha topilgan modellar)
    if (ids and level == "partial" and kat.get("asosiy") and len(direct) >= MIN_DIRECT
            and (coverage is None or coverage >= PARTIAL_COVERAGE) and (not topic or _named(topic, direct))):
        return {"ok": True, "mode": "catalog", "ids": ids, "partial": True, "sure": True}
    if med.get("ok") and not kat.get("ok"):
        return {"ok": True, "mode": "anatomy", "ids": [], "partial": False, "sure": False}
    return {"ok": False, "mode": "", "ids": [], "partial": False, "sure": bool(kat.get("checked", True))}


def _key(topic: str, language: str) -> tuple:
    return (" ".join(str(topic or "").lower().split()), language or "uz")


def cached(topic: str, language: str) -> Optional[dict]:
    hit = _cache.get(_key(topic, language))
    if not hit or time.time() - hit[0] > CACHE_TTL:
        return None
    return hit[1]


def _store(topic: str, language: str, result: dict) -> None:
    key = _key(topic, language)
    _cache[key] = (time.time(), result)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)


async def check(topic: str, language: str = "uz", *, fresh: bool = False) -> dict:
    """Mavzuni tekshiradi (pul yechilmaydi). Qaytaradi: decide() natijasi + `names` (modellar nomi)."""
    from services.kat3d import qidiruv
    from services.med3d import auto as med3d_auto

    if not fresh:
        hit = cached(topic, language)
        if hit is not None:
            return hit
    loop = asyncio.get_running_loop()
    med_job = loop.run_in_executor(None, med3d_auto.check_topic, topic, language)
    kat_job = loop.run_in_executor(None, qidiruv.top, topic, language)
    try:
        med = await asyncio.wait_for(med_job, 60)
    except Exception as exc:                          # noqa: BLE001
        log.warning("3D anatomiya tekshiruvi (sayt): %s", exc)
        med = {"ok": False, "checked": False}
    try:
        kat = await asyncio.wait_for(kat_job, 90)
    except Exception as exc:                          # noqa: BLE001
        log.warning("3D katalog qidiruvi (sayt): %s", exc)
        kat = {"ok": False, "ids": []}
    result = decide(med, kat, topic)
    result["names"] = names(result, med)
    log.info("3D tekshiruv (sayt): «%s» → %s (anatomiya %s/%s, katalog %s, %d model)", topic[:60],
             result["mode"] or "rad", med.get("ok"), med.get("checked", True), kat.get("level"), len(result["ids"]))
    # AI javob bermagan holat saqlanmaydi: keyingi urinishda qayta so'raladi.
    if med.get("checked", True) or kat.get("checked"):
        _store(topic, language, result)
    return result


def names(result: dict, med: Optional[dict] = None, limit: int = 6) -> List[str]:
    """Mijozga ko'rsatiladigan misollar: katalog modellari yoki anatomiya a'zolari nomi."""
    if result.get("mode") == "catalog":
        from services import katalog3d

        cat = katalog3d.katalog()
        return [cat[i]["nom_uz"] for i in result["ids"][:limit] if i in cat]
    if result.get("mode") == "anatomy" and med:
        try:
            from services.med3d import auto as med3d_auto

            by_id: Dict[str, dict] = getattr(med3d_auto, "BY_ID", {})
            return [str(by_id[o].get("uz") or o) for o in (med.get("organs") or [])[:limit] if o in by_id]
        except Exception:                              # noqa: BLE001
            return []
    return []


def public(result: dict) -> dict:
    """Brauzerga: {ok, mode, names, previews, message}."""
    previews = []
    if result.get("mode") == "catalog":
        from services import katalog3d

        previews = [i for i in result["ids"][:6] if katalog3d.preview_yoli(i)]
    sure = bool(result.get("sure", True))
    return {"ok": bool(result.get("ok")), "sure": sure, "mode": result.get("mode") or "",
            "partial": bool(result.get("partial")), "names": list(result.get("names") or []) if sure else [],
            "previews": previews if sure else [],
            "message": NO_3D if not result.get("ok") else ("" if sure else UNSURE)}
