"""Slaydlarni HTML qilib yozdiradi — qat'iy shablonsiz.

Eski ikki tizimda joylashuv koddan kelardi: avval AI koordinata aytar,
keyin biz uni tuzatardik; so'ngra 24 ta qat'iy qolip qildik va AI faqat
o'rinlarni to'ldirardi. Ikkalasida ham slaydning ko'rinishi kodda
qamalib qolgan — dizayn boyimaydi.

Bu yerda boshqacha: AI butun slaydni HTML/CSS/SVG qilib chizadi, biz
uni brauzerda 1920×1080 da suratga olamiz va PowerPointga qo'yamiz.
Kod slaydning ichki ko'rinishiga aralashmaydi — u faqat QOBIQ qoidalarini
(o'lcham, shrift, rang, tashqi fayl yo'qligi) va joylashuv
KATEGORIYALARINI aytadi. Qolganini AI har safar yangidan chizadi.

Slaydlar bo'laklab so'raladi: bitta so'rovda o'nta to'liq HTML hujjat
so'ralsa, javob token chegarasiga urilib oxirgisi chala keladi.
"""

import logging
import os
import re
from typing import Callable, Dict, List, Optional

from . import (deck_calc, deck_charts, deck_logic, deck_math, deck_shape, deck_style, deck_styles,
               llm_client)
from services import uz_script

log = logging.getLogger("html_slides")

SLIDE_W_PX = 1920
SLIDE_H_PX = 1080

# AI slaydlarni shu qator bilan ajratadi.
MARKER = "===SLIDE_BREAK==="

# Bitta so'rovda shuncha slayd. To'liq HTML hujjat uzun bo'ladi, shuning
# uchun bo'lak kichik.
CHUNK = 3

# Shrift ikki tomonga mos kelishi kerak: brauzer slaydni shu shrift
# bilan joylashtiradi, PowerPoint esa uni Arial (yoki Times New Roman)
# bilan chizadi. Liberation Sans/Serif aynan o'sha ikkisi bilan
# o'lchovdosh — harflar kengligi bir xil, shuning uchun matn
# PowerPointda ham o'sha joyni egallaydi va qutisidan toshmaydi.
FONT_STACK = "Arial, 'Liberation Sans', 'DejaVu Sans', sans-serif"
SERIF_STACK = "'Times New Roman', 'Liberation Serif', 'DejaVu Serif', serif"

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"```(?:html)?", re.IGNORECASE)

# Soya PowerPointga umuman o'tmaydi: shakl soyasini biz o'chiramiz,
# matn soyasi esa model uni matnning ikkinchi nusxasi bilan chizishga
# urinishiga olib keladi. Shuning uchun soya HTML dan butunlay
# kesib tashlanadi — model qoidani unutsa ham slaydda soya qolmaydi.
_SHADOW_DECL = re.compile(
    r"(?:-webkit-|-moz-|-ms-)?(?:box|text)-shadow\s*:[^;}\"']*;?",
    re.IGNORECASE)
# `drop-shadow(...)` `filter` qiymatining ichida turadi; ichida
# `rgba(...)` bo'lishi mumkin, shuning uchun bir qavat qavs hisobga
# olinadi.
_DROP_SHADOW = re.compile(
    r"drop-shadow\s*\([^()]*(?:\([^()]*\)[^()]*)*\)", re.IGNORECASE)
# Ichidagi yagona qiymat olib tashlangach bo'sh qolgan `filter:`.
_EMPTY_FILTER = re.compile(
    r"(?:-webkit-)?filter\s*:\s*([;}\"'])", re.IGNORECASE)


def strip_shadows(html: str) -> str:
    """Slayddan har qanday soyani olib tashlaydi."""
    text = _SHADOW_DECL.sub("", html)
    text = _DROP_SHADOW.sub("", text)
    text = _EMPTY_FILTER.sub(r"\1", text)
    text = re.sub(r";\s*;+", "; ", text)
    # Qoida olib tashlangach qolgan bo'sh nuqtali vergul.
    return re.sub(r"([{\"'])\s*;\s*", r"\1", text)


_LANGUAGE = {
    "ru": "русском языке",
    "en": "in English",
    # Qozoq tili: kirill, qozoq harflari bilan; o'zbek yoki rus so'zlari aralashmasin.
    "kk": "qozoq tilida, kirill alifbosida (ә, ғ, қ, ң, ө, ұ, ү, һ, і harflari bilan; "
          "masalan «Қорытынды», «Тарих», «Экономика»). Rus yoki o'zbek jumlalarini aralashtirmang",
    "uz": "o'zbek tilida (FAQAT lotin alifbosida, kirill harflarisiz)",
    # Kirill yozuvi: sarlavhalar va barcha so'zlar kirillda, ikki yozuv aralashmasin.
    "uz-cyrl": "o'zbek tilida, FAQAT KIRILL alifbosida (ў, қ, ғ, ҳ harflari bilan; "
               "masalan «Таҳлил», «Ўзбекистон»). Lotin harflarini ishlatmang va "
               "ikki yozuvni aralashtirmang",
}

# Joylashuv kategoriyalari — qat'iy shablon emas, lug'at. AI ulardan
# tanlaydi va o'zicha aralashtiradi.
_CATEGORIES = (
    ("muqova", "katta sarlavha, ostida ingichka aksent chiziq, pastda "
               "muallif va fan qatori"),
    ("reja", "TAQDIMOT REJASI (mundarija): 01, 02, 03 deb raqamlangan "
             "kartalar. FAQAT 2-slaydda; boshqa joyda ishlatilmaydi"),
    ("matn_rasm", "bir tomonda 2-3 yaxlit abzats (to'liq, bog'langan gaplar), "
                  "bir tomonda rasm (rasm chiqmasa o'rnida qo'shimcha matn)"),
    ("ikki_ustun", "chapda matn, o'ngda kartalar yoki jadval"),
    ("korsatkichlar", "2-4 ta juda yirik raqam, har birining ostida qisqa "
                      "izoh"),
    ("jarayon", "o'qlar bilan bog'langan qadamlar qatori"),
    ("vaqt_oqi", "gorizontal chiziq ustidagi sana va voqealar"),
    ("qiyoslash", "ikki ustunli qiyos yoki 2×2 matritsa (masalan SWOT)"),
    ("jadval", "QISQA jadval (ko'pi bilan 4 qator, 3 ustun, har katak 1-5 "
               "so'z) — faqat boshqa mazmun bilan birga; zich jadval emas"),
    ("diagramma", "faqat diagramma (chiziqli, ustunli yoki halqa) va uni "
                  "tushuntiradigan matn"),
    ("tuzilma", "qutilar va ularni bog'lovchi chiziqlar — ierarxiya yoki "
                "tarkib sxemasi"),
    ("iqtibos", "yirik tirnoq belgisi, kursiv matn, muallif qatori"),
    ("formula", "tushunchaning formulasi yirik, ostida belgilar izohi va "
                "u nimani hisoblashi"),
    ("misol", "masala sharti, qadamma-qadam yechim va javob"),
    ("kartalar", "bir xil o'lchamdagi kartalar, har birida sarlavha va "
                 "bir-ikki gaplik izoh"),
    ("yakun", "faqat xulosa matni — rahmat va savollar qatorisiz"),
)

CATEGORY_KEYS = tuple(key for key, _ in _CATEGORIES)


def catalogue_text() -> str:
    return "\n".join(f"  {key} — {note}" for key, note in _CATEGORIES)


# ────────────────────────────────────────────────────────── qobiq qoidalari

def icon_list() -> str:
    """Mavjud ikonkalar nomi — promptga qo'yiladi."""
    try:
        from . import icon_render

        names = icon_render.icon_names()
    except Exception:
        names = ()
    if not names:
        return "  (ikonka yo'q)"
    # Uzun bitta qator o'rniga o'nta ustunli ro'yxat: model uni
    # oson o'qiydi.
    rows = []
    for start in range(0, len(names), 10):
        rows.append("  " + ", ".join(names[start:start + 10]))
    return "\n".join(rows)


def shell_rules(theme, language: str) -> str:
    """Modelga beriladigan qoidalar — dizayn emas, MAZMUN uchun.

    Ilgari bu yerda "shriftni shunday ber, rangni bunday qil" degan
    o'nlab qoida turardi va model ularning yarmini unutardi. Endi
    dizayn CSS da qat'iy turibdi (`deck_style`), shuning uchun model
    bilan faqat mazmun haqida gaplashamiz: qaysi blok va ichida
    qanday matn.
    """
    target = _LANGUAGE.get(language, _LANGUAGE["uz"])
    return f"""Sen taqdimot muallifi va kompozitorisan. Matnni {target}
yozasan.

Dizayn TAYYOR: shrift, rang, chet, oraliq va kartochkaning ko'rinishi
CSS da qat'iy berilgan. Sen CSS yozmaysan, rang tanlamaysan, o'lcham
bermaysan. Sen faqat SLAYD MAZMUNINI va uning tuzilishini yozasan —
tayyor bloklardan foydalanib.

{deck_style.BLOCKS}

IKONKA nomlari faqat shu ro'yxatdan olinadi:
{icon_list()}

QAT'IY QOIDALAR:
1. Javobda faqat `<section class="slide">` ... `</section>` bo'ladi.
   Har slayddan keyin alohida qatorda {MARKER} yoziladi.
2. `<style>`, `style="..."`, `<script>`, `<html>`, `<head>`, `<body>`
   YOZMA. Rang, shrift, piksel, `width`, `height`, `margin`, `padding`
   — hech qaysisi yozilmaydi. Faqat yuqoridagi sinf nomlari.
3. `<img>` faqat ikonka uchun: `<img class="ikon" data-icon="NOM" alt="">`.
   Rasm faqat MATN VA RASM blokidagi `rasm` orqali so'raladi.
   Tashqi havola, emoji — yo'q.
4. DIAGRAMMA uchun faqat ma'lumot ber: `.chart` blokiga yorliqlar va
   qiymatlarni yoz — halqa, chiziqli va ustunli diagrammani tizim
   o'zi chiroyli chizadi (o'q, shkala, ranglar bilan). Shu sababli
   diagrammadan qo'rqma, undan keng foydalan; faqat `<svg>` yozma.
5. Bir varaqqa qancha sig'ishining YUQORI chegarasi (bu talab
   emas — shuncha bo'lishi kerak emas, shundan OSHMASIN):
   - kartochka 4 tadan oshmasin, izohi 2 gapdan oshmasin;
   - ro'yxat bandi 5 tadan oshmasin;
   - ko'rsatkich 4 tadan oshmasin; har birining ostidagi izoh
     yolg'iz yorliq emas, raqamning ma'nosi va sababini
     tushuntiruvchi 1-2 to'liq gap bo'lsin;
   - vaqt o'qida 5 tadan ortiq to'xtash bo'lmasin.
   Varaq 1920x1080 — bundan ko'pi sig'maydi va kesiladi.
6. BO'SH BLOK QOLDIRMA. Har kartochkaning sarlavhasi ham, izohi ham
   bo'lsin. Mazmun topolmasang kartochkani butunlay olib tashla va
   qolganlarini kamroq ustunga joyla. Slayd sarlavha va bitta
   jumladan iborat bo'lib qolmasin — sarlavhadagi fikr slaydda
   ochilsin; fikr bitta bo'lsa MATN VA RASM bloki bor.
7. BLOKNI TO'G'RI TANLANG va bir xillikka tushib qolmang. Har
   slayddan oldin o'ylang: "bu fikr qanday ko'rinishda eng yaxshi
   ochiladi?" Tanlov mazmunga qarab:
   - raqam, foiz yoki o'lchov bor fikr → ko'rsatkich (faqat
     8-qoidadagi HAQIQIY raqam bo'lsa);
   - ketma-ketlik, bosqich, tarix → qadamlar yoki vaqt o'qi;
   - ikki narsani qiyoslash → qiyoslash (ikki ustun);
   - tasnif, turlar → kartochkalar yoki qiyoslash; JADVAL faqat
     QISQA bo'lsa (ko'pi bilan 4 qator va 3 ustun, har katak 1-5
     so'z) va boshqa mazmun bilan birga — butun slaydni egallovchi,
     "tahlil jadvali" kabi zich jadval YOZILMAYDI: tinglovchi uni
     auditoriyada o'qiy olmaydi;
   - ulushlar, dinamika yoki solishtirish → diagramma (halqa,
     chiziqli, ustunli);
   - ta'rif, atama, bitta chuqur fikr → matn va rasm yoki oddiy
     ro'yxat (kartochkasiz);
   - mashhur so'z yoki ta'rif parchasi → iqtibos;
   - kartochka — faqat 3-4 ta teng huquqli, bir-biriga o'xshash
     element bo'lganda.
   Kartochkaga qaytaverish — xato: u eng oson yo'l, lekin taqdimot
   bir xil chiqadi. Ketma-ket ikki slayd bir xil blokdan iborat
   bo'lmasin va butun taqdimotda bitta blok qayta-qayta
   chiqmasin. Ikki slayd bir xil shaklni talab qilsa, birini
   boshqa blok bilan ifodalang. Lekin blokni faqat "boshqacha
   bo'lsin" deb tanlamang: avval mazmun, keyin shakl.
   Slayd NAFAS OLSIN: matn kam, bo'sh joy ko'p; bir blokda bitta
   fikr; uzun matn bo'lsa ikki slaydga bo'ling.
8. RAQAM VA DIAGRAMMA — taqdimotni jonlantiradi, ulardan
   foydalaning. Raqam uch xil bo'ladi:
   a) HISOBLANGAN raqam — formuladan va boshlang'ich qiymatdan
      kelgan. U RUXSAT: uni o'zingiz hisoblamang, `calc` yoki
      `data-calc` bilan bering — kod hisoblaydi.
   b) HAQIQIY statistik fakt — siz ishonadigan va manbasini ayta
      oladigan ma'lumot. Manba nomini yozing; manbaga
      bugungi va kelgusi yillar uchun "BMT, 2026" kabi yil
      qo'yilmaydi (bunday raqam "taxminiy" deyiladi).
   v) SHARTLI MISOL — haqiqiy raqamni bilmasangiz, tushunchani
      ko'rsatadigan, mavzuga mos taxminiy ma'lumot bilan diagramma
      tuzing va slaydning izohi oxiriga "Shartli misol." deb yozing.
      Shartli misolni haqiqiy statistika kabi ko'rsatmang (manba,
      yil yoki "tadqiqotlar ko'rsatdi" demang).
   Diagramma soni: kamida 6 slaydli taqdimotda bittadan kam
   bo'lmasin, 10 va undan ko'pida ikkitadan; ulardan biri halqa
   (ulushlar) bo'lsa yaxshi. Turini mazmun tanlaydi: ulush → halqa,
   vaqt bo'yicha o'zgarish → chiziqli (X o'qi yil), solishtirish →
   ustunli. Diagramma slaydida diagramma va uni tushuntiradigan 2-4
   gap bo'ladi: nima ko'rsatilgani va qanday xulosa chiqishi.
   Hisob-kitob mavzusida formulaning natijasi diagramma yoki
   ko'rsatkich bilan ko'rsatiladi. Ko'rsatkich (kpi) raqami
   izohida manbasi aytiladi (masalan: Statistika agentligi, 2024)
   yoki "Shartli misol" deyiladi.
9. Bir slaydda bir xil matnni ikki marta yozma.
9a. IQTIBOS faqat HAQIQIY, mashhur va muallifi aniq so'z bo'lsa
   (masalan, tarixiy shaxs, olim yoki davlat rahbarining ma'lum
   gapi). "Tashkilot hisobotidan", "BMT hisobotida aytilgan" kabi
   gap iqtibos emas — uni o'z so'zingiz bilan, manbasiz yozing.
   Aniq iqtibosni eslay olmasangiz iqtibos bloki shart emas: fikrni
   oddiy matn qilib yozing. Manba yili faqat aniq bilganingizda
   qo'yiladi.
10. Yorliqlar qisqa: kartochka sarlavhasi 1-4 so'z, vaqt o'qidagi
   izoh bir jumla. Sarlavhalar oddiy gap kabi yoziladi — faqat birinchi
   so'z va atoqli otlar bosh harf bilan: «Iqtisodiy o'sish omillari»,
   «Факторы экономического роста», «Экономикалық өсу факторлары».
11. Birinchi slayd — MUQOVA: sarlavha va bir jumlalik izoh (muallif ismi,
   fan va yilni tizim o'zi qo'yadi). Taqdimot XULOSA slaydi bilan
   tugaydi: unda faqat xulosa matni, rasmsiz. Har varaq mazmun beradi
   (bo'lim nomi yozilgan alohida varaq kerak emas).
12. Matn haqiqiy va aniq bo'lsin: nom, misol, manba bilan. "Lorem
   ipsum", "Matn shu yerda" kabi o'rin egallovchi yozma.
13. SARLAVHADA VA'DA QILINGAN NARSA SLAYDDA BO'LSIN. Sarlavhada
   "misollar" desangiz — ishlangan misol bo'lsin; "formula"
   desangiz — formula ko'rinsin; "qiyoslash" desangiz — ikki tomon
   yonma-yon tursin; ko'plikda "olimlar", "usullar" desangiz —
   bittasi emas, bir nechtasi bo'lsin (bitta iqtibosli varaqni
   "Mashhur olimlar" deb atamang). Va'dani bajarolmasangiz sarlavhani
   o'zgartiring.
14. Tushuncha formula bilan ta'riflansa (o'rtacha, dispersiya,
   korrelatsiya koeffitsiyenti, tezlanish, foiz stavkasi...), o'sha
   tushuncha kiritilgan slaydda uning formulasi `formula` blokida
   ko'rsatiladi — so'z bilan tasvirlab qo'yish yetmaydi. Formulani
   matn ichiga tiqmang va LaTeX bilan yozing — tizim uni belgilarga
   o'giradi. Mavzuda formula yo'q bo'lsa, bu blok ishlatilmaydi.
15. Qonun, farmon, qaror, nutq yoki dastur matnini so'zma-so'z
   KO'CHIRMANG. Hujjatning nomi, raqami va yilini ayting, mazmunini
   o'z so'zlaringiz bilan qisqa bayon qiling.
16. Imlo adabiy tilda: kirish qismi "Kirish" deb yoziladi
   ("Kiritish" emas), atamalar fan darsliklaridagidek.
17. HAR SLAYDDA UMUMLASHTIRUVCHI GAP BO'LSIN. Sarlavhadan keyin
   `<p class="lead">` — slaydning bosh fikri (bitta jumla, 12-25
   so'z): nima haqida va nima uchun muhim. Undan keyin dalil,
   misol va tafsilotlar. Slayd faqat qisqa bandlardan iborat
   bo'lmasin — har band avvalgi gapni davom ettirsin.
18. RAQAM — HAQIQIY TARTIB UCHUN: qadamlar, bosqichlar va reja
   raqamlanadi; kartochka va ro'yxat bandlari raqamsiz, bosh fikr bilan
   boshlanadi — shunda matn tabiiy o'qiladi. Fikrni ba'zan ravon
   abzats, ba'zan misol, ba'zan qiyoslash bilan ifodalang — slaydlar
   bir-biridan farq qilsin.
19. HAR SLAYD BOSHQA FIKRNI OCHSIN. Oldingi slaydlarda aytilgan
   fakt, sana yoki ta'rifni qayta yozmang; taqdimot rejasidagi har
   slayd o'z sarlavhasidagi masalani ochadi, boshqasini emas."""


def _shapes_note(shapes: Optional[List[tuple]], start: int, count: int) -> str:
    """Oldingi slaydlarda ISHLATILGAN blok kombinatsiyalari — modelga ko'rsatiladi.

    Slaydlar bo'laklab yoziladi va har bo'lak oldingilarning HTML'ini
    ko'rmaydi: "takrorlama" degan qoida modelga nimani takrorlamaslikni
    bilmasdan beriladi. Til sabab emas — ko'rinmaslik sabab. Shuning uchun
    aynan nima ishlatilgani (haqiqiy sinf nomlari bilan) aytiladi.
    Qoida inglizcha va qat'iy: model uni aniqroq bajaradi.
    """
    if not shapes:
        return ""
    names = lambda sig: "+".join(sig) if sig else "plain text"
    lines = [f"  slide {i}: {names(sig)}" for i, sig in enumerate(shapes, 1)]
    counts: Dict[tuple, int] = {}
    for sig in shapes[1:]:           # muqova hisobga olinmaydi
        if sig:
            counts[sig] = counts.get(sig, 0) + 1
    banned = [names(sig) for sig, n in counts.items() if n >= MAX_SAME_SHAPE]
    last = names(shapes[-1]) if shapes[-1] else ""
    rules = [
        f"HARD CONSTRAINT for slides {start}-{start + count - 1}: every slide must use a DIFFERENT "
        "block combination (the CSS classes you write inside <div class=\"body\">) from the slide "
        "right before it and from the other slides in this batch."]
    if last:
        rules.append(f"The previous slide already uses [{last}] — do NOT use it again.")
    if banned:
        rules.append("These combinations are already used " + str(MAX_SAME_SHAPE) +
                     " times and are FORBIDDEN now: " + "; ".join(f"[{b}]" for b in banned) + ".")
    rules.append("If the content seems to fit a used shape, express it with another block "
                 "(steps, timeline, table, two-column compare, quote, cards, plain list without photo). "
                 "Content comes first, but never repeat a shape without a real reason.")
    return ("Block combinations used so far:\n" + "\n".join(lines) + "\n" + " ".join(rules))


def _user_prompt(topic: str, start: int, count: int, total: int,
                 outline: List[Dict], used: List[str], level: int,
                 source: str, preferences: str, author: str,
                 family: str = "umumiy",
                 shapes: Optional[List[tuple]] = None,
                 written: Optional[List[str]] = None) -> str:
    depth = {
        1: "Tinglovchi — maktab o'quvchisi: sodda til, kundalik misollar.",
        2: "Tinglovchi — talaba: akademik, lekin ravon til.",
        3: "Tinglovchi — mutaxassis: atamalar, raqamlar, manbalar.",
    }.get(level, "Tinglovchi — talaba: akademik, lekin ravon til.")

    parts = [
        f'Mavzu: "{topic}"',
        f"Taqdimot jami {total} slayddan iborat.",
        f"Hozir {start}-slayddan boshlab {count} ta slayd kerak.",
        depth,
        deck_shape.guidance(family),
        "BLOKNI TO'G'RI TANLANG: raqam bo'lsa ko'rsatkich, ketma-ketlik "
        "bo'lsa qadam yoki vaqt o'qi, ikki narsa qiyoslansa ikki ustun "
        "yoki jadval, tasnif bo'lsa jadval, ta'rif yoki bitta fikr bo'lsa "
        "matn va rasm yoki kartochkasiz ro'yxat, mashhur so'z bo'lsa "
        "iqtibos. Kartochka faqat 3-4 ta teng huquqli element uchun — "
        "unga qaytaverma. Ketma-ket ikki slayd bir xil shaklda bo'lmasin "
        "va bitta blok qayta-qayta chiqmasin; lekin mazmun birinchi, "
        "shakl ikkinchi.",
    ]

    if outline:
        lines = []
        for index, item in enumerate(outline, 1):
            if start <= index < start + count:
                mark = "  →"
            else:
                mark = "   "
            title = item.get("title") or ""
            lines.append(f"{mark} {index}. [{item['category']}] "
                         + (f"«{title}» — " if title else "") + item["brief"])
        parts.append("Taqdimot rejasi (→ bilan belgilangani hozir "
                     "yoziladi). Slayd sarlavhasi rejadagi «sarlavha» bilan bir "
                     "xil bo'lsin; har slayd faqat o'z sarlavhasidagi masalani "
                     "ochsin:\n" + "\n".join(lines))
    if written:
        parts.append("Yozib bo'lingan slaydlar sarlavhalari (mazmunini "
                     "takrorlamang, ularning davomi bo'ling): "
                     + "; ".join(f"{i}. {t}" for i, t in enumerate(written, 1) if t))
    if used:
        parts.append("Oldingi slaydlarda ochilgan fikrlar (ularni qayta "
                     "aytmang): " + "; ".join(used[-5:]))
    if start <= 2 < start + count:
        parts.append("2-slayd — REJA: uni tizim yozilgan slaydlar sarlavhalaridan "
                     "o'zi yig'adi, shuning uchun bu o'rinda faqat bitta "
                     "<section class=\"slide\"> ichida «Taqdimot rejasi» "
                     "sarlavhasini yozing.")
    if start + count - 1 >= total:
        parts.append("Oxirgi slayd — faqat XULOSA: taqdimotdagi asosiy fikrlar va "
                     "yakuniy fikr. Taqdimot rejasini yoki mavzu ta'rifini "
                     "qaytarmang, yangi mavzu ochmang.")
    note = _shapes_note(shapes, start, count)
    if note:
        parts.append(note)
    if preferences:
        parts.append(f"Mijoz istagi: {preferences}")
    if source:
        parts.append("Mijoz bergan material (shundan foydalanib yoz):\n"
                     + source[:4000])

    return "\n\n".join(parts)


# ────────────────────────────────────────────────────────────── reja

_CONCLUSION_WORDS = re.compile(
    r"xulosa|yakun|natija|conclusion|summary|takeaway|заключен|вывод|итог", re.IGNORECASE)
_CONCLUSION_BRIEF = {
    "uz": "Xulosa: taqdimotdagi asosiy fikrlarni umumlashtirish va yakuniy xulosa "
          "(yangi mavzu ochmang, ta'rif yoki rejani takrorlamang)",
    "ru": "Заключение: обобщение главных мыслей и итоговый вывод "
          "(не открывайте новых тем, не повторяйте определения и план)",
    "en": "Conclusion: summary of the key points and a final takeaway "
          "(no new topics, do not repeat definitions or the agenda)",
    "kk": "Қорытынды: презентациядағы негізгі ойларды жинақтау және түпкілікті тұжырым "
          "(жаңа тақырып ашпаңыз, анықтама мен жоспарды қайталамаңыз). Қазақ тілінде.",
    "uz-cyrl": "Хулоса: тақдимотдаги асосий фикрларни умумлаштириш ва якуний хулоса "
               "(янги мавзу очманг, таъриф ёки режани такрорламанг). Кирилл ёзувида.",
}


def plan_outline(topic: str, count: int, language: str,
                 level: int = 2) -> Dict:
    """Har slayd uchun sarlavha, bir qatorli mazmun va joylashuv kategoriyasi.

    Slaydlar bo'laklab yoziladi va har bo'lak avvalgisining HTML'ini
    ko'rmaydi. Reja oldindan tuzilsa, har bo'lak o'z o'rnini biladi va
    bir mavzu ikki slaydda takrorlanmaydi. Sarlavhalar shu yerda
    belgilanadi: slaydlar ularni aynan ishlatadi, reja slaydi esa
    yozilgan slaydlarning sarlavhalaridan yig'iladi — shunda reja bilan
    taqdimot bir-biriga zid kelmaydi.
    """
    quota = deck_logic.chart_quota(count)
    chart_rule = (
        f"Rejada kamida {quota} ta slayd 'diagramma' kategoriyasida bo'lsin"
        + (" (ulardan biri ulushlar uchun halqa)" if quota >= 2 else "")
        + ": diagramma taqdimotni jonlantiradi. Ma'lumot haqiqiy bo'lsa "
          "manbasi bilan, bo'lmasa shartli misol sifatida beriladi.\n"
        if quota else "")
    prompt = (
        f'Mavzu: "{topic}"\n\n'
        f"Shu mavzuda {count} slaydli taqdimot rejasini tuz. Har slayd "
        "uchun qisqa sarlavha (2-6 so'z), bir qatorli mazmun va unga mos "
        "joylashuv kategoriyasini ayt.\n\n"
        "Kategoriyalar:\n" + catalogue_text() + "\n\n"
        "MANTIQIY KETMA-KETLIK: slaydlar bir-biridan keyin tabiiy kelsin — "
        "har slayd oldingisining davomi. Har slayd mavzuning BOSHQA jihatini "
        "ochsin: ikki slaydda bir xil voqea, ta'rif yoki fakt "
        "takrorlanmasin va ikkita sarlavha bir narsani aytmasin. Nimadan "
        "boshlash, nima bilan davom etish va qayerda yakunlash kerakligini "
        "mavzuning o'zi aytadi.\n"
        "Birinchisi — muqova, ikkinchisi — 'reja' (uning mazmunini tizim "
        "o'zi yig'adi), oxirgisi — yakun (XULOSA: shu mavzu bo'yicha asosiy "
        "fikrlar va yakuniy fikr). Xulosa FAQAT oxirgi slaydda. 'reja' "
        "kategoriyasi faqat 2-slayd.\n"
        "Kategoriyani MAZMUNGA QARAB tanlang va bir xillikdan qoching: "
        "raqam → korsatkichlar, ketma-ketlik → jarayon yoki vaqt_oqi, "
        "ikki narsa → qiyoslash, ulush yoki dinamika → diagramma, ta'rif "
        "yoki bitta fikr → matn_rasm yoki iqtibos. 'kartalar' faqat 3-4 ta "
        "teng huquqli element uchun; unga qaytaverma. Ketma-ket ikki slayd "
        "bir xil kategoriyada bo'lmasin (mantiq buni majburlamasa); bir "
        "kategoriya butun rejada 2 martadan ko'p takrorlanmasin ('matn_rasm' "
        "bundan mustasno). 'jadval' kategoriyasi faqat qisqa (3-4 qator) "
        "taqqoslash uchun. Har 10 ta slaydning taxminan 3 tasi 'matn_rasm' "
        "(matn + rasm) bo'lsin, ular bir-biriga ketma-ket kelmasin.\n"
        + chart_rule
        + ("Bu HISOB-KITOB mavzusi: rejada formula, ishlangan misol va "
           "diagramma kategoriyalari ham bo'lsin — har formula misol bilan "
           "tasdiqlansin, natijalar diagramma bilan ko'rsatilsin.\n"
           if deck_shape.is_calculation(topic) else "")
        + "Shuningdek mavzu qaysi oilaga tegishli ekanini ayting: "
        + deck_shape.names() + "\n\n"
        f"Matn {_LANGUAGE.get(language, _LANGUAGE['uz'])}.\n"
        'Faqat JSON: {"fan": "...", '
        '"slides": [{"title": "...", "brief": "...", "category": "..."}]}'
    )
    raw, hint = [], ""
    for attempt in range(2):
        try:
            data = llm_client._call_openrouter(
                "Sen taqdimot rejasini tuzasan. Faqat JSON qaytar.",
                prompt, temperature=0.6, max_tokens=900 + 200 * count)
            raw = data.get("slides") or []
            hint = data.get("fan") or ""
        except llm_client.NoCredits:
            raise
        except Exception as exc:
            log.warning("Reja olinmadi, kategoriyalar o'zimiz tanlaymiz: %s", exc)
            raw, hint = [], ""
        # Chala reja (kam slayd) bir marta qayta so'raladi: yetmagan o'rinlar
        # mavzu nomi bilan to'ldirilsa, model o'sha slaydlarda mavzuning
        # ta'rifini qayta yozib yuboradi.
        if len(raw) >= count:
            break
        log.warning("Reja %d ta slayd uchun keldi, %d kerak", len(raw), count)

    family = deck_shape.of(topic, hint)
    log.info("Mavzu oilasi: %s", family)

    outline: List[Dict] = []
    for index in range(count):
        item = raw[index] if index < len(raw) and isinstance(raw[index], dict) else {}
        brief = str(item.get("brief") or "").strip()
        title = deck_logic.short_title(str(item.get("title") or ""))
        category = str(item.get("category") or "").strip().lower()
        if category not in CATEGORY_KEYS:
            category = _fallback_category(index, count)
        if index == 0:
            category = "muqova"
        elif index == 1:
            category = "reja"
            title = deck_logic.PLAN_LABEL.get(language, deck_logic.PLAN_LABEL["uz"])
        elif index == count - 1:
            category = "yakun"
            # Oxirgi slayd — XULOSA. Reja boshqa narsa yozgan bo'lsa (masalan
            # mavzu nomi), model uni shunday yozib yuboradi: ta'rif qayta chiqadi.
            if not _CONCLUSION_WORDS.search(brief):
                brief = _CONCLUSION_BRIEF.get(language, _CONCLUSION_BRIEF["uz"])
        elif category in ("muqova", "yakun"):
            category = _fallback_category(index, count)
        elif category == "reja":
            # "Taqdimot rejasi" faqat 2-slayd; boshqa joyda u xulosa oldidan
            # yoki oxirida reja slaydini takrorlab yuborardi.
            category = _fallback_category(index, count)
        if not brief:
            brief = (f"{topic} — {index + 1}-slayd: mavzuning oldingi slaydlarda "
                     "ochilmagan YANGI jihati (ta'rif yoki rejani takrorlamang)")
        if not title:
            title = deck_logic.short_title(deck_logic.short_note(brief, 60))
        outline.append({"title": title, "brief": brief, "category": category})

    outline = ensure_charts(outline, language)
    outline = ensure_photos(outline)
    # Kod darajasida kategoriya almashtirilmaydi (ilgari shunday edi va
    # mantiqan ketma-ket kelishi kerak bo'lgan ikki ro'yxatni ajratib,
    # fikrni uzardi). Bir xillikdan qochishni model promptdagi yo'riqnoma
    # bo'yicha o'zi qiladi. Faqat diagramma soni kafolatlanadi.
    return {"family": family, "slides": outline}


# Diagramma soni promptdagi iltimosga qoldirilmaydi: ilgari "raqam
# bo'lmasa diagramma yozmang" qoidasi modelni diagrammani butunlay
# chetlab o'tishga olib kelgan edi. Reja yetarli diagramma bermasa, mos
# slaydlar shu yerda diagrammali qilib belgilanadi.
_CHART_CANDIDATES = ("korsatkichlar", "kartalar", "ikki_ustun", "qiyoslash",
                     "jadval", "tuzilma")


def ensure_charts(outline: List[Dict], language: str = "uz") -> List[Dict]:
    count = len(outline)
    want = deck_logic.chart_quota(count)
    have = [i for i, item in enumerate(outline) if item["category"] == "diagramma"]
    need = want - len(have)
    if need <= 0:
        return outline
    candidates = [i for i in range(2, count - 1)
                  if outline[i]["category"] in _CHART_CANDIDATES]
    if len(candidates) < need:       # mos kategoriya yetmasa boshqa oddiy slaydlardan
        extra = [i for i in range(2, count - 1)
                 if outline[i]["category"] not in ("diagramma", "formula", "misol", "iqtibos", "matn_rasm")
                 and i not in candidates]
        candidates += extra
    candidates = [i for i in candidates if i not in have]
    if not candidates:
        return outline
    chosen = deck_logic.pick_even(candidates, min(need, len(candidates)))
    for order, index in enumerate(chosen):
        item = outline[index]
        kind = deck_logic.chart_kind_for(f"{item['title']} {item['brief']}",
                                         order + len(have))
        if want >= 2 and order == 0 and not any(i.get("chart_kind") == "halqa" for i in outline):
            kind = "halqa"            # bir nechta diagrammadan biri halqa bo'lsin
        item["category"] = "diagramma"
        item["brief"] = (f"{item['brief']} — DIAGRAMMA bilan ko'rsating: "
                         f"{deck_logic.KIND_TEXT[kind]}. Ma'lumot haqiqiy "
                         "bo'lmasa izohda \"Shartli misol\" deb yozing.")
        item["chart_kind"] = kind
        log.info("%d-slayd diagrammali qilib belgilandi (%s)", index + 1, kind)
    return outline


# Rasmli slaydlar soni ham promptga qoldirilmaydi: har 10 ta asosiy slaydning
# 3 tasida rasm bo'lsin (deck_logic.photo_quota). Reja kam rasmli slayd bersa,
# mos slaydlar shu yerda "matn_rasm" qilib belgilanadi.
_PHOTO_CANDIDATES = ("kartalar", "ikki_ustun", "qiyoslash", "tuzilma", "jarayon")


def ensure_photos(outline: List[Dict]) -> List[Dict]:
    count = len(outline)
    want = deck_logic.photo_quota(count)
    have = [i for i, item in enumerate(outline) if item["category"] == "matn_rasm"]
    need = want - len(have)
    if need <= 0:
        return outline
    candidates = [i for i in range(2, count - 1)
                  if outline[i]["category"] in _PHOTO_CANDIDATES and i not in have]
    if len(candidates) < need:
        extra = [i for i in range(2, count - 1)
                 if outline[i]["category"] not in ("diagramma", "formula", "misol", "iqtibos",
                                                   "korsatkichlar", "jadval", "vaqt_oqi", "matn_rasm")
                 and i not in candidates]
        candidates += extra
    if not candidates:
        return outline
    # Rasmli slaydlar bir-biriga tegib turmasin: mavjudlardan uzoqroqlar afzal.
    chosen = []
    pool = list(candidates)
    while pool and len(chosen) < need:
        taken = have + chosen
        best = max(pool, key=lambda i: min([abs(i - t) for t in taken] or [99]))
        chosen.append(best)
        pool.remove(best)
    for index in sorted(chosen):
        item = outline[index]
        item["category"] = "matn_rasm"
        item["brief"] = (f"{item['brief']} — MATN VA RASM bloki bilan ko'rsating: bir tomonda "
                         "fikrni ochgan 2-3 yaxlit abzats (to'liq, bog'langan gaplar), bir tomonda "
                         "mavzuga mos real fotosurat.")
        log.info("%d-slayd rasmli qilib belgilandi", index + 1)
    return outline


# Reja kelmaganda ishlatiladigan zaxira. Unda raqamga tayanadigan
# kategoriyalar YO'Q: mavzu qanday ekanini bilmay turib diagramma yoki
# ko'rsatkich so'rash — modelni statistika o'ylab topishga majburlash
# demakdir. Zaxira har doim mazmunga neytral bloklardan boshlanadi.
_SAFE_CATEGORIES = ("kartalar", "matn_rasm", "ikki_ustun", "reja",
                    "jarayon", "tuzilma", "qiyoslash", "iqtibos")


def _fallback_category(index: int, count: int) -> str:
    """Reja kelmaganda tanlanadigan neytral kategoriya."""
    return _SAFE_CATEGORIES[index % len(_SAFE_CATEGORIES)]


# ───────────────────────────────────────────────────────── slayd yozish

_SECTION = re.compile(r"<section\b[^>]*\bclass\s*=\s*[\"'][^\"']*\bslide\b"
                      r"[^\"']*[\"'][^>]*>.*?</section>",
                      re.IGNORECASE | re.DOTALL)
# Model ba'zan sinf nomiga qo'shimcha yozadi yoki `style=` tiqadi —
# ikkalasi ham dizayn tizimini buzadi.
_STYLE_ATTR = re.compile(r"\sstyle\s*=\s*([\"'])(.*?)\1",
                         re.IGNORECASE | re.DOTALL)
_STYLE_TAG = re.compile(r"<style\b.*?</style>|<script\b.*?</script>",
                        re.IGNORECASE | re.DOTALL)


def split_slides(raw: str) -> List[str]:
    """Javobni slayd mazmunlariga ajratadi.

    Model endi to'liq HTML hujjat emas, `<section class="slide">`
    bloklarini yozadi. Chala kelgani (yopilmagani) tashlab
    yuboriladi: uni chizsak yarim slayd chiqadi.
    """
    text = _FENCE.sub("", _THINK.sub("", str(raw or "")))
    text = _STYLE_TAG.sub("", text)
    bodies = []
    for part in text.split(MARKER):
        for match in _SECTION.finditer(part):
            body = _STYLE_ATTR.sub("", match.group(0))
            bodies.append(strip_shadows(body).strip())
    if not bodies:
        log.warning("Javobda slayd topilmadi (%d belgi)", len(text))
    return bodies


_DARK_SLIDE = re.compile(
    r'(<section\b[^>]*\bclass\s*=\s*(["\'])[^"\']*\bdark\b[^"\']*\2'
    r'[^>]*>)', re.IGNORECASE)


_ROW_OPEN = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])(?:cols|steps)(?![-\w])'
    r'[^"\']*["\'][^>]*>', re.IGNORECASE)
_LIST_OPEN = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])list(?![-\w])'
    r'[^"\']*["\'][^>]*>', re.IGNORECASE)
_DIV_TAG = re.compile(r"<div\b[^>]*>|</div\s*>", re.IGNORECASE)
_CARD_OPEN = re.compile(
    r'^<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])card(?![-\w])',
    re.IGNORECASE)
_ITEM_OPEN = re.compile(
    r'^<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])item(?![-\w])',
    re.IGNORECASE)
_CARD_TITLE = re.compile(
    r'class\s*=\s*["\'][^"\']*\bcard-title\b[^"\']*["\'][^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL)
_HAS_DOT = re.compile(r'^\s*<div\b[^>]*\bikon-dot\b', re.IGNORECASE)
_ITEM_DOT = re.compile(
    r'<span\b[^>]*\bclass\s*=\s*["\']item-dot["\'][^>]*>\s*</span>',
    re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]+>")
# Kalit so'z bo'yicha topilmasa beriladigan umumiy ikonkalar.
_SPARE_ICONS = ("idea", "target", "star", "strategy", "success",
                "research", "project", "innovation", "award", "team")


def _pick_icon(texts, used: set) -> str:
    """Kartochka yoki band matniga mos ikonka nomi.

    Matnlar tartib bilan sinaladi: avval sarlavha (u mavzuni aniq
    aytadi), keyin butun matn. Aks holda izohdagi tasodifiy so'z
    sarlavhadan ustun kelardi.
    """
    if isinstance(texts, str):
        texts = [texts]
    name, known = "", set()
    try:
        from . import icon_render

        known = set(icon_render.icon_names())
        for text in texts:
            if not text:
                continue
            path = icon_render.resolve(None, text,
                                       used={n + ".png" for n in used})
            name = os.path.basename(path)[:-4] if path else ""
            if name and name != "default" and name not in used:
                return name
    except Exception as exc:
        log.warning("Ikonka tanlanmadi: %s", exc)
    for spare in _SPARE_ICONS:
        if spare not in used and (not known or spare in known):
            return spare
    return name or _SPARE_ICONS[0]


def _plain(fragment: str, limit: int = 120) -> str:
    return " ".join(_ANY_TAG.sub(" ", fragment).split())[:limit]


def _children(body: str, opening):
    """Blokning bevosita bola `<div>` lari: (ochuvchi teg, butun blok)."""
    depth, child = 1, None
    for tag in _DIV_TAG.finditer(body, opening.end()):
        if tag.group(0).startswith("</"):
            depth -= 1
            if depth == 1 and child is not None:
                yield child, body[child.start():tag.end()]
                child = None
            if depth == 0:
                return
        else:
            if depth == 1:
                child = tag
            depth += 1


def _inside_card(body: str, at: int) -> bool:
    """`at` o'rni kartochka ichidami."""
    stack = []
    for tag in _DIV_TAG.finditer(body, 0, at):
        if tag.group(0).startswith("</"):
            if stack:
                stack.pop()
        else:
            stack.append(bool(_CARD_OPEN.match(tag.group(0))))
    return any(stack)


def _auto_icons(body: str) -> str:
    """Kartochka, qadam va ro'yxat bandlariga ikonka qo'yadi.

    Eski tizimda promptda "har kartochka yonida ikonka tursin" degan
    talab bor edi. Kvotalar olib tashlanganda u ham ketdi va model
    ixtiyoriy ikonkani deyarli qo'ymay qo'ydi — slaydlar yana quruq
    bo'lib qoldi. Ikonka — dizayn, mazmun emas, shuning uchun uni
    modeldan so'ramaymiz: kod har kartochka va bandning matniga
    qarab o'zi tanlaydi. Bir slaydda ikonka takrorlanmaydi.

    Kartochka ichidagi kichik ro'yxatga tegilmaydi — u yerda
    kartochkaning o'z ikonkasi yetarli.
    """
    inserts = []
    used: set = set(re.findall(r'data-icon\s*=\s*["\']([^"\']+)', body))

    for opening in _ROW_OPEN.finditer(body):
        for child, card in _children(body, opening):
            inner = card[len(child.group(0)):]
            if not _CARD_OPEN.match(child.group(0)) or _HAS_DOT.match(inner):
                continue
            title = _CARD_TITLE.search(card)
            name = _pick_icon([_plain(title.group(1)) if title else "",
                               _plain(card, 160)], used)
            used.add(name)
            inserts.append((child.end(), child.end(),
                            '<div class="ikon-dot"><img class="ikon" '
                            f'data-icon="{name}" alt=""></div>'))

    for opening in _LIST_OPEN.finditer(body):
        if _inside_card(body, opening.start()):
            continue
        for child, item in _children(body, opening):
            if not _ITEM_OPEN.match(child.group(0)):
                continue
            dot = _ITEM_DOT.search(item)
            if not dot:
                continue
            bold = re.search(r"<b>(.*?)</b>", item, re.IGNORECASE | re.DOTALL)
            name = _pick_icon([_plain(bold.group(1)) if bold else "",
                               _plain(item)], used)
            used.add(name)
            start = child.start() + dot.start()
            inserts.append((start, child.start() + dot.end(),
                            '<span class="item-ikon"><img class="ikon" '
                            f'data-icon="{name}" data-icon-color="FFFFFF" '
                            'alt=""></span>'))

    for start, end, piece in sorted(inserts, reverse=True):
        body = body[:start] + piece + body[end:]
    return body


_DOT_ICON = re.compile(
    r'(class\s*=\s*["\'][^"\']*\bikon-dot\b[^"\']*["\'][^>]*>\s*<img\b)'
    r'(?![^>]*data-icon-color)', re.IGNORECASE)


def _whiten_icons(body: str) -> str:
    """Rangli doira ichidagi ikonka oq rangga bo'yalsin.

    Doira endi kartochka rangida to'la bo'yalgan — ikonka o'sha rangda
    bo'lsa ko'rinmay qoladi. Doiradan tashqaridagi ikonka esa aksent
    rangida qoladi.
    """
    return _DOT_ICON.sub(lambda m: m.group(1) + ' data-icon-color="FFFFFF"',
                         body)


def _decorate(body: str) -> str:
    """To'q varaqqa yumshoq bezak doiralarini qo'yadi.

    Yassi to'q fon quruq ko'rinadi. Ikkita katta, kam farq qiladigan
    doira unga chuqurlik beradi. Ular `position:fixed` bilan
    qo'yilgani uchun joylashuvga tegmaydi va matnning orqasida
    turadi; PowerPointda oddiy shakl bo'lib chiqadi.
    """
    if not _DARK_SLIDE.search(body):
        return body
    bits = '<div class="bezak bezak-a"></div><div class="bezak bezak-b"></div>'
    return _DARK_SLIDE.sub(lambda m: m.group(1) + bits, body, count=1)


# `quote-by`dagi "— Tashkilot, 2026-yil hisobotidan": yil bugungi yoki
# kelgusi bo'lsa, bu o'ylab topilgan manba — yil va hisobot nomi olib
# tashlanadi, muallif nomi qoladi.
_QUOTE_BY = re.compile(
    r'(<p\b[^>]*class\s*=\s*["\'][^"\']*quote-by[^"\']*["\'][^>]*>)(.*?)(</p>)',
    re.IGNORECASE | re.DOTALL)
_BY_YEAR = re.compile(r",?\s*(?:\w+\s+)?((?:19|20)\d\d)\b[^<]*$")


def guard_quote_sources(body: str) -> str:
    """Iqtibos muallifidagi bugungi/kelgusi yilli "hisobot"ni olib tashlaydi."""
    from services import timeframe

    limit = timeframe.current_year()

    def swap(match):
        found = _BY_YEAR.search(match.group(2))
        if not found or int(found.group(1)) < limit:
            return match.group(0)
        return match.group(1) + match.group(2)[:found.start()].rstrip(" ,") \
            + match.group(3)

    return _QUOTE_BY.sub(swap, body)


# "(BMT, 2026)" — model bugungi yil ma'lumotini bilmaydi, shuning uchun bunday
# manba o'ylab topilgan bo'ladi. Yil o'rniga "taxminiy" yoziladi.
_SOURCE_YEAR = re.compile(r"\(([^()<>]{2,60}?),\s*((?:19|20)\d\d)\)")
_ESTIMATE = {"uz": "taxminiy", "uz-cyrl": "тахминий", "ru": "оценка", "en": "estimate", "kk": "болжамды"}


def guard_source_years(body: str, language: str = "uz") -> str:
    """Manbaga yozilgan bugungi/kelgusi yilni "taxminiy" ga almashtiradi."""
    from services import timeframe

    limit = timeframe.current_year()
    label = _ESTIMATE.get(language, _ESTIMATE["uz"])

    def swap(match):
        return (f"({match.group(1)}, {label})" if int(match.group(2)) >= limit
                else match.group(0))

    return _SOURCE_YEAR.sub(swap, body)


def build_pages(bodies: List[str], theme, language: str = "uz") -> List[str]:
    """Slayd mazmunlarini chizishga tayyor HTML hujjatlarga aylantiradi.

    Diagrammalar shu yerda chiziladi: model faqat ma'lumot beradi,
    SVG ni kod yasaydi — shunda ustunning balandligi ham, yozuvning
    o'rni ham har safar to'g'ri chiqadi.
    """
    # O'zbekcha taqdimotda barcha matn tanlangan yozuvda bo'ladi: model
    # adashib boshqa yozuvda yozgan yoki kod qo'ygan so'zlar shu yerda tuzatiladi.
    script = uz_script.script_of_language(language)
    if script:
        bodies = [uz_script.normalize_html(body, script) for body in bodies]

    # Hisob-kitobni kod bajaradi: `calc` va `data-calc` shu yerda raqamga
    # aylanadi, so'ng diagramma chiziladi.
    drawn = [deck_charts.draw(
        _half_charts(deck_math.render(deck_styles.decorate(
            _whiten_icons(_auto_icons(_decorate(
                guard_quote_sources(guard_source_years(deck_calc.apply(body), language))))), theme))),
        theme)
             for body in bodies]
    try:
        from . import html_images

        drawn, placed = html_images.apply_icons(drawn, theme)
        # Ikonkasi topilmagani rangli belgiga aylanadi — buzuq rasm
        # belgisi slaydga tushmaydi.
        drawn = html_images.sweep(drawn, theme)
        log.info("Ikonkalar: %d ta", placed)
    except Exception as exc:
        log.warning("Ikonkalar qo'yilmadi: %s", exc)
    return [_keep_source(deck_style.page(theme, page), body)
            for page, body in zip(drawn, bodies)]


# Modelning o'zi yozgan slayd sahifaning boshida izoh sifatida
# saqlanadi. Tuzatish kerak bo'lsa modelga AYNAN shu yuboriladi —
# ikonkalar data-URI, diagrammalar tayyor SVG bo'lib ketgan chizilgan
# nusxa emas. U nusxa minglab token bo'lardi: model uni qayta yoza
# olmay, o'rniga yangi, sodda slayd yozib qo'yardi.
_SOURCE = re.compile(r"<!--manba:([A-Za-z0-9+/=]*)-->")


def _keep_source(page: str, body: str) -> str:
    import base64

    token = base64.b64encode(body.encode("utf-8")).decode("ascii")
    return page.replace("</head>", f"<!--manba:{token}--></head>", 1)


def source_of(page: str) -> str:
    """Sahifadan modelning asl yozgan slaydini oladi ("" — topilmasa)."""
    import base64

    match = _SOURCE.search(page or "")
    if not match:
        return ""
    try:
        return base64.b64decode(match.group(1)).decode("utf-8")
    except Exception:
        return ""


def write_slides(topic: str, slide_count: int, theme, language: str = "uz",
                 level: int = 2, preferences: str = "", source_text: str = "",
                 author: str = "",
                 progress_cb: Optional[Callable] = None) -> List[str]:
    """Butun taqdimotni HTML hujjatlar ro'yxati qilib qaytaradi."""
    # Mijoz tanlagan son — muqova va rejadan KEYINGI slaydlar (xulosa shu songa
    # kiradi). Muqova va reja slaydi qo'shimcha yoziladi: ilgari ular ham
    # hisobga kirar, 10 slaydda asosiy mavzuga 8 tadan kam slayd qolardi.
    slide_count = max(4, int(slide_count or 8)) + 2
    plan = plan_outline(topic, slide_count, language, level)
    outline = plan["slides"]
    family = plan["family"]
    system = shell_rules(theme, language)

    slides: List[str] = []
    used: List[str] = []
    start = 1
    while start <= slide_count:
        count = min(CHUNK, slide_count - start + 1)
        if progress_cb:
            try:
                progress_cb(start - 1, slide_count)
            except Exception:
                pass

        user = _user_prompt(topic, start, count, slide_count, outline,
                            used, level, source_text, preferences, author,
                            family, shapes=[shape_signature(b) for b in slides],
                            written=[deck_logic.title_of(b) for b in slides])
        chunk = _write_chunk(system, user, count)
        if len(chunk) < count:
            # Bir marta qayta so'raymiz: chala javob har safar emas,
            # ba'zan keladi.
            log.warning("%s-%s slaydlardan %d tasi keldi, qayta so'raladi",
                        start, start + count - 1, len(chunk))
            retry = _write_chunk(system, user, count)
            if len(retry) > len(chunk):
                chunk = retry
        # Hali ham yetmasa — yetmaganlari BITTADAN so'raladi. Uch
        # slaydlik katta so'rov vaqt chegarasiga, hisobdagi mablag'
        # chegarasiga yoki model javob uzunligi chegarasiga urilishi
        # mumkin; bitta slaydlik kichik so'rov esa o'tadi. Ilgari
        # yetmagan slaydlar jimgina tashlab yuborilardi va mijozga
        # ikki slaydlik taqdimot borardi.
        for number in range(start + len(chunk), start + count):
            single = _user_prompt(topic, number, 1, slide_count, outline,
                                  used, level, source_text, preferences,
                                  author, family,
                                  shapes=[shape_signature(b) for b in slides]
                                  + [shape_signature(b) for b in chunk],
                                  written=[deck_logic.title_of(b) for b in slides + chunk])
            one = _write_chunk(system, single, 1)
            if not one:
                # Oxirgi chora: kichik JSON so'rov, slaydni kod yig'adi.
                # Katta HTML javobni filtr kesadigan mavzularda ham u
                # odatda o'tadi — mijoz taqdimotsiz qolmaydi.
                item = outline[number - 1] if number <= len(outline) else {}
                plain = _plain_slide(topic, item.get("brief") or topic,
                                     number, slide_count, language, author)
                one = [plain] if plain else []
            if one:
                chunk.append(one[0])
            else:
                log.error("%d-slayd yozilmadi", number)

        for offset, body in enumerate(chunk[:count]):
            number = start + offset
            if number == 1:
                body = _cover_credit(body, author, language)
            if number == slide_count:
                body = _drop_thanks(body)
            if 1 < number and _thin(body):
                body = _thicken(body, system, theme)
            if number == slide_count:
                body = _no_photo(body)
            slides.append(body)
        used.extend(item["brief"] for item in outline[start - 1:start - 1 + count])
        start += count

    log.info("HTML slaydlar tayyor: %d/%d ta", len(slides), slide_count)
    if not slides:
        raise RuntimeError("AI birorta to'liq slayd qaytarmadi")
    # Chala taqdimot mijozga berilmaydi: pul qaytariladi va qayta
    # urinish mumkin. Bir-ikki slayd yetmasa — taqdimot baribir to'liq
    # ko'rinadi, u topshiriladi.
    if len(slides) < _enough(slide_count):
        raise RuntimeError(
            f"AI {slide_count} ta slayddan faqat {len(slides)} tasini yozdi")
    ctx = _Deck(topic, slide_count, outline, family, system, theme, language, level,
                source_text, preferences, author)
    slides = repair_deck(slides, ctx)
    slides = diversify(slides, theme, language)
    return build_pages(slides, theme, language)


# ───────────────────────────────────────────── mantiq va sifat tekshiruvi

MAX_FIXES = 6               # bitta taqdimotda ko'pi bilan shuncha slayd qayta yoziladi


class _Deck:
    """Taqdimotni yozishda ishlatilgan sozlamalar (qayta yozish uchun kerak)."""

    def __init__(self, topic, total, outline, family, system, theme, language, level,
                 source_text, preferences, author):
        self.topic, self.total, self.outline, self.family = topic, total, outline, family
        self.system, self.theme, self.language, self.level = system, theme, language, level
        self.source_text, self.preferences, self.author = source_text, preferences, author


def _rewrite_slide(slides: List[str], index: int, note: str, ctx: "_Deck") -> Optional[str]:
    """`index`-slaydni ko'rsatma bilan qayta yozdiradi; yaroqli natija bo'lmasa None."""
    number = index + 1
    others = [b for i, b in enumerate(slides) if i != index]
    user = _user_prompt(
        ctx.topic, number, 1, ctx.total, ctx.outline,
        [o.get("brief", "") for i, o in enumerate(ctx.outline) if i != index][:8],
        ctx.level, ctx.source_text, ctx.preferences, ctx.author, ctx.family,
        shapes=[shape_signature(b) for b in others],
        written=[deck_logic.title_of(b) for i, b in enumerate(slides) if i != index])
    user += "\n\n" + note
    try:
        fresh = _write_chunk(ctx.system, user, 1)
    except Exception as exc:
        log.warning("%d-slayd qayta yozilmadi: %s", number, exc)
        return None
    if not fresh:
        return None
    return fresh[0]


def repair_deck(slides: List[str], ctx: "_Deck") -> List[str]:
    """Yozilgan slaydlarni mantiq jihatidan tekshiradi va nuqsonlisini qayta yozdiradi.

    1. O'rtada yoki oxirda takrorlangan "reja" slaydi;
    2. avvalgi slaydning takrori (bir xil sarlavha yoki bir xil matn);
    3. zich jadval (butun varaq jadval — auditoriyada o'qib bo'lmaydi);
    4. diagramma bo'lishi kerak edi, lekin yozilmagan;
    keyin: umumlashtiruvchi gap, kartochka raqamlarini olib tashlash va reja
    slaydini HAQIQIY sarlavhalardan yig'ish.
    """
    result = list(slides)
    count = len(result)
    if count < 4:
        return result
    fixes = 0
    last = count - 1

    def fix(index: int, note: str, accept) -> bool:
        nonlocal fixes
        if fixes >= MAX_FIXES:
            return False
        fixes += 1
        fresh = _rewrite_slide(result, index, note, ctx)
        if fresh and accept(fresh):
            result[index] = fresh
            log.info("%d-slayd mantiq tekshiruvi bo'yicha qayta yozildi", index + 1)
            return True
        log.info("%d-slaydning qayta yozilishi qabul qilinmadi", index + 1)
        return False

    def own_brief(index: int) -> str:
        item = ctx.outline[index] if index < len(ctx.outline) else {}
        title = item.get("title") or ""
        return (f"«{title}» — " if title else "") + (item.get("brief") or "")

    # 1) Boshqa joydagi "reja" slaydlari
    for index in deck_logic.stray_plans(result):
        if index == last:
            continue
        fix(index,
            "BU SLAYD TAQDIMOT REJASINI TAKRORLAYAPTI — reja faqat 2-slayd. "
            "Quyidagi mavzu bo'yicha MAZMUNLI slayd yozing (reja yoki mundarija "
            "emas): " + own_brief(index),
            lambda body: not deck_logic.is_plan_title(deck_logic.title_of(body)))

    # 2) Takrorlangan slaydlar
    for later, earlier in sorted(deck_logic.duplicates(result).items()):
        before = deck_logic.title_of(result[earlier])
        fix(later,
            f"BU SLAYD {earlier + 1}-slaydni («{before}») TAKRORLAYAPTI: bir xil mavzu va "
            "bir xil faktlar. Uni BUTUNLAY BOSHQA masalaga bag'ishlang — rejadagi shu "
            "o'rin uchun belgilangan mavzu: " + own_brief(later) +
            ". Oldingi slaydlardagi sana, nom va faktlarni qaytarmang.",
            lambda body, e=earlier: not (
                deck_logic.similar_titles(deck_logic.title_of(body), deck_logic.title_of(result[e]))
                or deck_logic.same_content(body, result[e])))

    # 3) Zich jadval
    for index in range(2, last):
        if deck_logic.oversized_table(result[index]):
            fix(index,
                "BU SLAYDDA ZICH JADVAL BOR — tinglovchi uni auditoriyada o'qiy olmaydi. "
                "Xuddi shu mazmunni JADVALSIZ ifodalang: kartochkalar, qiyoslash (ikki "
                "ustun), qadamlar yoki oddiy ro'yxat bilan; slayd oxirida bitta umumlashtiruvchi "
                "gap bo'lsin. Zarur bo'lsa faqat QISQA jadval (ko'pi bilan 4 qator, 3 ustun, "
                "har katak 1-5 so'z) qoldiring. Slayd:\n" + (source_of(result[index]) or result[index]),
                lambda body: not deck_logic.oversized_table(body))

    # 4) Diagramma bo'lishi kerak bo'lgan slaydlar
    for index in range(2, last):
        item = ctx.outline[index] if index < len(ctx.outline) else {}
        if item.get("category") == "diagramma" and not deck_logic.has_chart(result[index]):
            kind = item.get("chart_kind") or deck_logic.chart_kind_for(own_brief(index), index)
            fix(index,
                "BU SLAYD DIAGRAMMALI BO'LISHI SHART (rejada shunday belgilangan). "
                f"Tur: {deck_logic.KIND_TEXT[kind]}. Slaydda `.chart` bloki (yoki hisob uchun "
                "`.calc`) va uni tushuntiruvchi 2-4 gap bo'lsin. Ma'lumot haqiqiy "
                "bo'lmasa, izoh oxiriga «Shartli misol.» deb yozing. Mavzu: " + own_brief(index),
                deck_logic.has_chart)

    # 4b) Rasmli bo'lishi kerak bo'lgan slaydlar
    for index in range(2, last):
        item = ctx.outline[index] if index < len(ctx.outline) else {}
        if item.get("category") == "matn_rasm" and not deck_logic.has_photo(result[index]):
            fix(index,
                "BU SLAYDDA RASM BO'LISHI SHART (rejada shunday belgilangan). Slaydni "
                "MATN VA RASM bloki bilan yozing: bir tomonda fikrni ochgan 2-3 yaxlit "
                "abzats (`par-col` ichida `par`; to'liq, bog'langan gaplar), bir "
                "tomonda `.rasm` bloki (`data-prompt` — rasmning inglizcha tavsifi: "
                "oddiy realistik fotosurat). Mavzu: " + own_brief(index),
                deck_logic.has_photo)

    # 5) Umumlashtiruvchi gap
    result = add_leads(result, ctx)

    # 6) Kartochka raqamlari (faqat reja slaydida qoladi)
    result = [deck_logic.strip_numbering(b) for b in result]

    # 6b) Sarlavha harflari (birinchi so'z bosh harf) va yolg'iz qolgan kartochka (3+1).
    # Bu ikki narsa kod bilan tuzatiladi: modelga "shunday yozma" deyish o'rniga natija to'g'rilanadi.
    result = [b if i == 0 else deck_logic.fix_columns(deck_logic.fix_title_case(b))
              for i, b in enumerate(result)]
    # 6c) Rasmli slayd: matn yaxlit abzatslar bo'lsin (mayda bandlar va ikonkali qatorlar emas).
    result = [b if i == 0 else deck_logic.flow_photo_text(b) for i, b in enumerate(result)]

    # 7) Reja slaydi — yozilgan slaydlarning haqiqiy sarlavhalaridan
    items = []
    for index in range(2, last):
        title = deck_logic.title_of(result[index]) or (
            ctx.outline[index].get("title", "") if index < len(ctx.outline) else "")
        brief = ctx.outline[index].get("brief", "") if index < len(ctx.outline) else ""
        if title:
            items.append((title, brief))
    if items:
        result[1] = deck_logic.plan_slide(items, ctx.language)
    return result


def add_leads(slides: List[str], ctx: "_Deck") -> List[str]:
    """Umumlashtiruvchi gapi yo'q slaydlarga bitta bosh fikr jumlasi qo'shadi.

    Model slaydni faqat bandlar bilan to'ldirib qo'ysa, tinglovchi nima
    haqida ekanini bilmay qoladi va matn sun'iy ko'rinadi. Jumla slaydning
    o'z matnidan olinadi: yangi fakt qo'shilmaydi.
    """
    last = len(slides) - 1
    wanted = [i for i in range(2, last) if deck_logic.needs_lead(slides[i])]
    if not wanted:
        return slides
    listing = "\n\n".join(
        f"{i + 1}. Sarlavha: {deck_logic.title_of(slides[i])}\nMatn: {deck_logic.plain(slides[i])[:420]}"
        for i in wanted[:20])
    prompt = (
        f'Taqdimot mavzusi: "{ctx.topic}".\n'
        "Quyidagi slaydlarning har biri uchun BITTA umumlashtiruvchi gap yozing: slaydning "
        "bosh fikri (12-25 so'z) — nima haqida va nima uchun muhim. Gap slaydning o'z matniga "
        "tayansin, yangi fakt, sana yoki raqam qo'shmang va sarlavhani so'zma-so'z "
        "takrorlamang. Bandlarni sanab chiqmang.\n"
        f"Matn {_LANGUAGE.get(ctx.language, _LANGUAGE['uz'])}.\n\n{listing}\n\n"
        'Faqat JSON: {"leads": [{"n": 3, "lead": "..."}]}')
    try:
        data = llm_client._call_openrouter(
            "Sen taqdimot muharririsan. Faqat JSON qaytar.", prompt,
            temperature=0.4, max_tokens=300 + 120 * len(wanted[:20]))
    except Exception as exc:
        log.warning("Umumlashtiruvchi gaplar olinmadi: %s", exc)
        return slides
    result = list(slides)
    added = 0
    for item in (data.get("leads") or []):
        try:
            index = int(item.get("n")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        lead = str(item.get("lead") or "").strip()
        if index in wanted and lead and 4 <= len(lead.split()) <= 40:
            result[index] = deck_logic.insert_lead(result[index], lead)
            added += 1
    log.info("Umumlashtiruvchi gap: %d ta slaydga qo'shildi", added)
    return result


# ───────────────────────────────────────────── bir xil slaydlarga qarshi

# Taqdimot bir xil ko'rinadigan bo'lib qolsa (masalan, uch slayd "ro'yxat +
# rasm"), mijoz buni darhol payqaydi. Prompt va reja modelga "takrorlama"
# deydi, lekin model baribir eng oson shaklga qaytadi. Shuning uchun yozib
# bo'lingach slaydlar shakli solishtiriladi va takrorlangan slayd boshqa blok
# bilan QAYTA yozdiriladi — mazmuni saqlanadi, faqat shakl o'zgaradi.
# Bu qat'iy kvota emas: mazmun uchun boshqa shakl topilmasa, qayta yozish
# rad etiladi va slayd o'zgarmaydi.
MAX_SAME_SHAPE = 2          # bir shakl butun taqdimotda ko'pi bilan shuncha
MAX_REWORKS = 3             # bitta taqdimotda ko'pi bilan shuncha qayta yozish

_SHAPE_NAMES = {
    "split": "matn+rasm yoki ikki ustun", "list": "ro'yxat", "cols": "kartochkalar",
    "steps": "qadamlar", "timeline": "vaqt o'qi", "table": "jadval", "kpi": "ko'rsatkichlar",
    "quote": "iqtibos", "chart": "diagramma", "calc": "diagramma", "formula": "formula",
    "misol": "misol", "rasm": "rasm", "lead": "asosiy fikr",
}


def shape_signature(body: str) -> tuple:
    """Slaydning asosiy bloklari (masalan, ('list', 'rasm', 'split'))."""
    counts = _shape(body)
    return tuple(sorted(name for name, n in counts.items() if n and name != "ikon-row"))


def repeated_slides(bodies: List[str]) -> List[int]:
    """Shakli takrorlangan slaydlar indekslari (muqova va yakundan tashqari)."""
    flagged, seen = [], {}
    last = len(bodies) - 1
    previous = None
    for index, body in enumerate(bodies):
        signature = shape_signature(body)
        if index in (0, 1, last) or not signature:
            previous = None
            continue
        seen[signature] = seen.get(signature, 0) + 1
        # Rasmli slaydlar soni kvota bilan belgilanadi (har 10 tada 3 ta): ularni
        # "bir xil shakl" deb qayta yozish rasmni yo'qotardi. Faqat ketma-ket kelsa belgilanadi.
        repeated_too_often = seen[signature] > MAX_SAME_SHAPE and "rasm" not in signature
        if signature == previous or repeated_too_often:
            flagged.append(index)
        previous = signature
    return flagged


def _shape_label(signature: tuple) -> str:
    return " + ".join(dict.fromkeys(_SHAPE_NAMES.get(n, n) for n in signature)) or "oddiy matn"


def rework_slide(body: str, signature: tuple, used: List[tuple], theme,
                 language: str = "uz") -> str:
    """Takrorlangan slaydni boshqa blok bilan qayta yozdiradi (yoki o'zini qaytaradi)."""
    import difflib

    taken = "; ".join(sorted({_shape_label(u) for u in used if u}))
    user = (
        f"Bu slayd boshqa slaydlar bilan bir xil shaklda ({_shape_label(signature)}) "
        "va taqdimot bir xil ko'rinib qolmoqda.\n\n"
        "SHU SLAYDNING O'ZINI qayta yozing: sarlavha va MAZMUN (fikrlar, faktlar) "
        "saqlansin, lekin ularni BOSHQA blok bilan ifodalang.\n"
        f"Bu taqdimotda allaqachon ishlatilgan shakllar (ularni QAYTARMANG): {taken}.\n"
        "Mazmunga mos tanlang: ketma-ketlik → qadamlar yoki vaqt o'qi; ikki narsa → "
        "qiyoslash (ikki ustun) yoki jadval; tasnif → jadval; 2-4 teng element → "
        "kartochkalar (agar ular ko'p ishlatilmagan bo'lsa); bitta chuqur fikr → "
        "kartochkasiz oddiy ro'yxat yoki iqtibos. Yangi fakt o'ylab topmang, "
        "raqam qo'shmang. Rasm ixtiyoriy.\n\n"
        "Javobda faqat bitta <section class=\"slide\"> ... </section> bo'lsin.\n\n"
        "Slayd:\n" + (source_of(body) or body)
    )
    try:
        raw = llm_client._call_openrouter_text(
            shell_rules(theme, language), user, temperature=0.6,
            max_tokens=max(2600, len(body) // 2))
    except Exception as exc:
        log.warning("Takrorlangan slayd qayta yozilmadi: %s", exc)
        return body

    fresh = split_slides(raw)
    if not fresh:
        return body
    new_signature = shape_signature(fresh[0])
    if not new_signature or new_signature == signature or new_signature in used:
        log.info("Qayta yozish qabul qilinmadi: shakl baribir takror (%s)", _shape_label(new_signature))
        return body
    if bool(_DARK_SLIDE.search(body)) != bool(_DARK_SLIDE.search(fresh[0])):
        return body
    words = lambda text: _plain(text, 100000).lower().split()
    before, after = words(body), words(fresh[0])
    if before and difflib.SequenceMatcher(None, before, after).ratio() < 0.3:
        log.info("Qayta yozish qabul qilinmadi: mazmun yo'qolgan")
        return body
    return fresh[0]


def diversify(bodies: List[str], theme, language: str = "uz") -> List[str]:
    """Bir xil shakldagi slaydlarni boshqa blok bilan almashtiradi."""
    result = list(bodies)
    reworked = 0
    for index in repeated_slides(result):
        if reworked >= MAX_REWORKS:
            break
        # Oldingi qayta yozish bu slaydni allaqachon hal qilgan bo'lishi mumkin.
        if index not in repeated_slides(result):
            continue
        signature = shape_signature(result[index])
        # Muqova va reja slaydi (kartochkalar) o'zgartirish uchun taqiqlangan shakllarga kirmaydi.
        used = [shape_signature(b) for i, b in enumerate(result) if i not in (index, 0, 1)]
        updated = rework_slide(result[index], signature, used, theme, language)
        if updated is not result[index]:
            result[index] = updated
            reworked += 1
            log.info("%d-slayd boshqa shaklda qayta yozildi", index + 1)
    return result


# Muqovadagi "Tayyorladi: ... | Fan: ... | 2026" qatori. Model uni namunadan
# ko'chirib, ism, fan va yilni o'zi o'ylab topardi — mijoz ism kiritmagan
# bo'lsa ham muqovada begona ism turardi. Endi bunday qator kod bilan
# olib tashlanadi, ism esa faqat mijoz kiritgan bo'lsa qo'yiladi.
_CREDIT_LABEL = {"uz": "Tayyorladi", "uz-cyrl": "Тайёрлади", "ru": "Подготовил(а)", "en": "Prepared by", "kk": "Дайындаған"}
_CREDIT_LINE = re.compile(
    r"<(p|div|span)\b[^>]*>(?:(?!</?\1\b).)*?"
    r"(?:tayyorladi|bajardi|muallif|topshirdi|fan\s*:|yo.nalish\s*:|"
    r"подготовил|выполнил|автор|предмет\s*:|prepared\s+by|author|subject\s*:)"
    r"(?:(?!</?\1\b).)*?</\1>",
    re.IGNORECASE | re.DOTALL)
_NOTE_LINE = re.compile(r"<p\b[^>]*\bclass\s*=\s*[\"'][^\"']*\bnote\b[^\"']*[\"'][^>]*>.*?</p>",
                        re.IGNORECASE | re.DOTALL)


def _cover_credit(body: str, author: str = "", language: str = "uz") -> str:
    """Muqovadan ism/fan/yil qatorini olib, mijoz ismini (bo'lsa) qo'yadi."""
    body = _NOTE_LINE.sub("", body)
    body = _CREDIT_LINE.sub("", body)
    author = (author or "").strip()
    if not author:
        return body
    label = _CREDIT_LABEL.get(language, _CREDIT_LABEL["uz"])
    note = f'<p class="note">{_escape(label)}: {_escape(author)}</p>'
    # Muqova `.body` ichining oxiriga qo'yiladi.
    match = re.search(r"</div>\s*</section>\s*$", body, re.IGNORECASE)
    if match:
        return body[:match.start()] + note + body[match.start():]
    return re.sub(r"</section>\s*$", note + "</section>", body, count=1,
                  flags=re.IGNORECASE)


def _enough(slide_count: int) -> int:
    """Topshirish uchun kerakli eng kam slayd soni."""
    return max(3, -(-slide_count * 4 // 5))


# Varaqni mazmunli qiladigan bloklar. Ularning birortasi ham bo'lmasa
# varaq faqat sarlavha va bir-ikki jumladan iborat — bunday varaq
# (bo'lim ajratkichi ham) taqdimotda kerak emas.
_CONTENT_CLASSES = ("cols", "steps", "list", "timeline", "split", "formula",
                    "misol", "chart", "kpi", "quote", "ikon-row", "rasm",
                    "card")


# Xulosa varag'idagi "rahmat" va "savollar" qatorlari. Qisqa matnli
# elementgina olib tashlanadi — mazmunli gap ichida "savol" so'zi
# uchrasa tegilmaydi.
_THANKS = re.compile(
    r"rahmat|e[\'ʼ‘’`]?tiboringiz|savollar|savolingiz|спасибо|"
    r"благодар|вопрос|thank|questions", re.IGNORECASE)
_SHORT_TEXT = re.compile(
    r"<(p|h[1-6]|div|span)\b[^>]*>((?:(?!<div\b|</div>|<p\b|</p>).){0,120}?)"
    r"</\1\s*>", re.IGNORECASE | re.DOTALL)
_TITLE_CLASS = re.compile(r'class\s*=\s*["\'][^"\']*\btitle\b', re.IGNORECASE)


def _drop_thanks(body: str) -> str:
    """Xulosadan "rahmat" va "savollar" qatorlarini olib tashlaydi."""

    def drop(match):
        text = _plain(match.group(2), 200)
        if (text and len(text) <= 80 and _THANKS.search(text)
                and not _TITLE_CLASS.search(match.group(0))):
            return ""
        return match.group(0)

    return _SHORT_TEXT.sub(drop, body)


_SPLIT_OPEN = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])split(?![-\w])'
    r'[^"\']*["\'][^>]*>', re.IGNORECASE)
_RASM_OPEN = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])rasm(?![-\w])'
    r'[^"\']*["\'][^>]*>', re.IGNORECASE)
_RASM_TEXT = re.compile(
    r'<p\b[^>]*\bclass\s*=\s*["\'][^"\']*\brasm-matn\b[^"\']*["\'][^>]*>'
    r'(.*?)</p>', re.IGNORECASE | re.DOTALL)


def _close_of(body: str, opening) -> int:
    """Ochuvchi `<div>` ning yopuvchi tegidan keyingi o'rin (-1 — yo'q)."""
    depth = 1
    for tag in _DIV_TAG.finditer(body, opening.end()):
        depth += -1 if tag.group(0).startswith("</") else 1
        if depth == 0:
            return tag.end()
    return -1


def _no_photo(body: str) -> str:
    """Xulosadagi rasm blokini oddiy matnga aylantiradi.

    Xulosaga rasm kerak emas. Rasm o'rnidagi qo'shimcha matn
    yo'qotilmaydi — u xulosa matnining davomi bo'lib, to'liq enli
    qatorga o'tadi; rasm bloki turgan `split` esa yechiladi.
    """
    while True:
        opening = _RASM_OPEN.search(body)
        if not opening:
            return body
        end = _close_of(body, opening)
        if end < 0:
            return body
        texts = _RASM_TEXT.findall(body[opening.start():end])
        plain = "".join(f'<p class="note">{text.strip()}</p>'
                        for text in texts if _plain(text))
        # Rasm bloki turgan `split` (bo'lsa) yechiladi.
        holder = None
        for split in _SPLIT_OPEN.finditer(body, 0, opening.start()):
            close = _close_of(body, split)
            if close >= end:
                holder = (split, close)
        body = body[:opening.start()] + plain + body[end:]
        if holder:
            split, close = holder
            close += len(plain) - (end - opening.start())
            inner = body[split.end():close]
            inner = inner[:inner.lower().rfind("</div")]
            body = body[:split.start()] + inner + body[close:]


_CHART_OPEN = re.compile(
    r'<div\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bchart\b)'
    r'(?![^>]*\bdata-size\s*=)', re.IGNORECASE)


def _half_charts(body: str) -> str:
    """Ikki ustunli joydagi diagramma yarim o'lchamda chizilsin.

    To'liq enli chizma yarim ustunga siqilsa, yozuvlari o'qib
    bo'lmas darajada mayda chiqadi.
    """
    spans = []
    for split in _SPLIT_OPEN.finditer(body):
        close = _close_of(body, split)
        if close > 0:
            spans.append((split.end(), close))

    def mark(match):
        inside = any(start <= match.start() < end for start, end in spans)
        return match.group(0) + (' data-size="half"' if inside else "")

    return _CHART_OPEN.sub(mark, body)


def _thin(body: str) -> bool:
    """Varaq faqat sarlavha va qisqa matndan iboratmi."""
    if re.search(r"<table\b", body, re.IGNORECASE):
        return False
    for value in _CLASS_ATTR.findall(body):
        if any(name in _CONTENT_CLASSES for name in value.split()):
            return False
    return True


def _thicken(body: str, system: str, theme) -> str:
    """Yupqa varaqni MATN VA RASM varag'iga aylantiradi."""
    user = (
        "Quyidagi slayd faqat sarlavha va bir-ikki jumladan iborat "
        "(yoki faqat bo'lim nomi yozilgan ajratkich). Bunday varaq "
        "taqdimotda kerak emas.\n\n"
        "Shu slaydni MATN VA RASM bloki bilan qayta yozing: sarlavhadagi "
        "fikr o'sha qolsin, chap tomonda u 2-3 yaxlit abzats bilan ochilsin, o'ng "
        "tomonda `rasm` bloki (ichida rasm chiqmasa turadigan qo'shimcha "
        "matn) bo'lsin. Oddiy `<section class=\"slide\">` — `dark` va "
        "`title big` emas.\n\n"
        "Javobda faqat bitta <section class=\"slide\"> ... </section> "
        "bo'lsin.\n\nSlayd:\n" + body
    )
    try:
        raw = llm_client._call_openrouter_text(
            system, user, temperature=0.5, max_tokens=3000)
    except Exception as exc:
        log.warning("Yupqa slayd to'ldirilmadi: %s", exc)
        return body
    fixed = split_slides(raw)
    if not fixed or _thin(fixed[0]):
        log.warning("Yupqa slayd to'ldirilmadi: javob ham yupqa")
        return body
    log.info("Yupqa slayd matn va rasm bilan to'ldirildi")
    return fixed[0]


_DATA_SRC = re.compile(r'src\s*=\s*(["\'])\s*(data:[^"\']+)\1',
                       re.IGNORECASE)


def _park_images(html: str) -> tuple:
    """Rasmlarni qisqa belgiga almashtiradi."""
    store = {}

    def hide(match):
        token = f"#rasm{len(store) + 1}"
        store[token] = match.group(2)
        return f'src="{token}"'

    return _DATA_SRC.sub(hide, html), store


def _unpark_images(html: str, store: dict) -> str:
    """Belgilarni rasmning o'ziga qaytaradi."""
    for token, uri in store.items():
        html = html.replace(token, uri)
    return html


def fix_slide(html: str, problems: List[str], theme, language: str = "uz") -> str:
    """Joylashuvi buzilgan slaydning O'ZINI tuzattiradi.

    Yangi slayd yozdirilmaydi. Modelga o'zi yozgan slayd va unda
    brauzer topgan xatolar — qaysi matn, qayerda — aniq aytiladi va
    faqat o'sha joylar tuzatiladi. Javob asl slaydga solishtiriladi:
    tuzilishi o'zgargan yoki mazmuni yo'qolgan bo'lsa, u tuzatish
    emas, qayta yozish — qabul qilinmaydi.
    """
    if not problems:
        return html

    source = source_of(html)
    if not source:
        match = _SECTION.search(html)
        if not match:
            return html
        source = _park_images(match.group(0))[0]

    listed = "\n".join(f"- {item}" for item in problems)
    user = (
        "Bu slaydni siz yozgansiz. Brauzerda ochilganda quyidagi xatolar "
        f"topildi (« » ichida — xato turgan matn):\n{listed}\n\n"
        "SHU SLAYDNI QAYTARING — yangisini yozmang. Faqat xato "
        "ko'rsatilgan joylarni tuzating. Qolgan hamma narsa — "
        "`<section>` sinfi, sarlavha, bloklar, ularning tartibi, "
        "sinf nomlari va matnlar — o'zgarmasin.\n\n"
        "Tuzatish yo'llari:\n"
        "- matn qutisiga sig'magan yoki varaqdan chiqib ketgan bo'lsa — "
        "o'sha matnni qisqartiring (ma'nosini saqlab); faqat bu yetmasa "
        "o'sha blokdagi bitta band yoki kartochkani olib tashlang;\n"
        "- matn ustiga matn tushgan bo'lsa — ikkalasidan biri keraksiz "
        "bo'lsa o'chiring, aks holda ikkalasini qisqartiring;\n"
        "- matn ikki marta yozilgan bo'lsa — nusxasini o'chiring;\n"
        "- matn juda mayda bo'lib qolgan bo'lsa — slaydda mazmun ortiqcha: "
        "har matnni 1-2 qisqa gapga keltiring, uzun izohlarni o'chiring, "
        "kerak bo'lsa 1-2 ta band yoki kartochkani olib tashlang (blok "
        "turi o'zgarmasin);\n"
        "- varaqda katta bo'sh joy qolgan bo'lsa — mavjud izohlarni "
        "to'liqroq yozing, yangi blok qo'shmang.\n\n"
        "Javobda faqat bitta <section class=\"slide\"> ... </section> "
        "bo'lsin.\n\nSlayd:\n" + source
    )

    try:
        raw = llm_client._call_openrouter_text(
            shell_rules(theme, language), user,
            temperature=0.2, max_tokens=max(2600, len(source) // 2))
    except Exception as exc:
        log.error("Slaydni tuzatib bo'lmadi: %s", exc)
        return html

    fixed = split_slides(raw)
    if not fixed:
        return html
    reason = _rewritten(source, fixed[0],
                        any("mayda" in item for item in problems))
    if reason:
        log.warning("Tuzatish qabul qilinmadi — slayd qayta yozilgan: %s",
                    reason)
        return html
    return build_pages(fixed[:1], theme, language)[0]


# Slaydning tuzilishini belgilaydigan bloklar. Tuzatishda ularning
# biri yo'qolsa yoki yangisi paydo bo'lsa — bu tuzatish emas.
_BLOCK_CLASSES = ("cols", "steps", "list", "timeline", "split", "formula",
                  "misol", "chart", "calc", "kpi", "quote", "ikon-row", "lead",
                  "rasm")
_CLASS_ATTR = re.compile(r'class\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def _shape(body: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in _CLASS_ATTR.findall(body):
        for name in value.split():
            if name in _BLOCK_CLASSES:
                counts[name] = counts.get(name, 0) + 1
    counts["table"] = len(re.findall(r"<table\b", body, re.IGNORECASE))
    return counts


def _rewritten(before: str, after: str, shrunk: bool = False) -> str:
    """Tuzatilgan slayd asl slaydning o'zimi. Bo'lmasa — sababi."""
    import difflib

    dark = lambda body: bool(_DARK_SLIDE.search(body))
    if dark(before) != dark(after):
        return "slayd turi (dark) o'zgargan"
    old, new = _shape(before), _shape(after)
    changed = sorted(name for name in set(old) | set(new)
                     if bool(old.get(name)) != bool(new.get(name)))
    if changed:
        return "bloklar o'zgargan: " + ", ".join(changed)
    words = lambda body: _plain(body, 100000).lower().split()
    first, second = words(before), words(after)
    if first:
        kept = difflib.SequenceMatcher(None, first, second).ratio()
        # Mayda matn xatosida mazmunni sezilarli qisqartirish — aynan
        # kerakli tuzatish, shuning uchun chegara pastroq.
        if kept < (0.3 if shrunk else 0.55):
            return f"matnning faqat {kept:.0%} i qolgan"
    return ""


# Bo'sh yonga qo'yiladigan izohning uzunligi. Uzun matn qutisidan
# toshib, diagrammaning ustiga chiqib ketadi.
_GAP_WORDS = 45


def explain_visual(html: str, theme, language: str = "uz") -> str:
    """Slayddagi diagrammani tushuntiruvchi qisqa matn.

    Slaydning bir yoni bo'sh qolganda ishlatiladi: slaydni qayta
    chizish shart emas, bo'sh joyga diagrammaning ma'nosini
    aytadigan matn qo'yilsa yetadi.
    """
    target = _LANGUAGE.get(language, _LANGUAGE["uz"])
    match = _SECTION.search(html)
    parked = _park_images(match.group(0) if match else html)[0]
    system = ("Sen taqdimot matnlarini yozadigan muharrirsan. "
              f"Javobni {target} yozasan.")
    user = (
        "Quyida taqdimot slaydining mazmuni berilgan. Undagi "
        "diagramma, jadval yoki ko'rsatkichlarni tushuntiruvchi "
        f"2-3 gaplik matn yoz ({_GAP_WORDS} so'zdan oshmasin): raqamlar "
        "nimani bildiradi, nega shunday va undan qanday xulosa "
        "chiqadi.\n"
        "Slaydda allaqachon yozilgan gaplarni takrorlama. Sarlavha, "
        "ro'yxat belgisi, HTML teg va qo'shtirnoq yozma — faqat "
        "tayyor matnning o'zini ber.\n\nSlayd:\n" + parked
    )

    try:
        raw = llm_client._call_openrouter_text(
            system, user, temperature=0.5, max_tokens=400)
    except Exception as exc:
        log.warning("Diagramma izohi olinmadi: %s", exc)
        return ""

    text = _THINK.sub("", str(raw or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip().strip('"').strip()
    words = text.split()
    if len(words) > _GAP_WORDS:
        text = " ".join(words[:_GAP_WORDS]).rstrip(".,;:") + "."
    return text


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def fill_gap(html: str, area: Dict, theme, language: str = "uz") -> str:
    """Slaydning bo'sh yoniga diagramma izohini qo'yadi.

    Slayd qayta chizilmaydi: mavjud joylashuvga tegilmay, bo'sh
    maydonga bitta matn bloki qo'shiladi. Blok `position: fixed`
    bilan qo'yiladi — slayd aynan brauzer oynasi o'lchamida
    (1920x1080) bo'lgani uchun u varaqning o'sha joyiga tushadi.
    Ko'rinishi dizayn tizimidan olinadi: aksent chizig'i va `note`.
    """
    if not area:
        return html
    # Izoh diagramma, jadval yoki ko'rsatkichni tushuntiradi. Ular
    # bo'lmagan varaqda "bo'sh joy" — rasm kartochkasi yoki ataylab
    # qoldirilgan nafas; u yerga matn qo'yilsa kartochka ustiga
    # chiqib qolardi.
    section = _SECTION.search(html)
    visual = section.group(0) if section else html
    if not re.search(r"<svg\b|<table\b|\bkpi\b", visual, re.IGNORECASE):
        return html

    pad = 48
    x = float(area.get("x") or 0) + pad
    y = float(area.get("y") or 0)
    width = float(area.get("w") or 0) - pad * 2
    height = float(area.get("h") or 0)
    if width < 220 or height < 120:
        return html

    text = explain_visual(html, theme, language)
    if not text:
        return html

    block = (
        f'<div style="position:fixed;left:{x:.0f}px;top:{y:.0f}px;'
        f'width:{width:.0f}px;height:{height:.0f}px;display:flex;'
        'flex-direction:column;justify-content:center;gap:24px">'
        '<div class="rule"></div>'
        f'<p class="note">{_escape(text)}</p></div>'
    )

    lower = html.lower()
    cut = lower.rfind("</body>")
    if cut < 0:
        return html + block
    return html[:cut] + block + html[cut:]


def _restore(html: str, theme) -> str:
    """Qayta chizilgan slaydning rasmlarini joyiga qo'yadi.

    Model belgini tushirib qoldirsa yoki yangi `<img>` qo'shsa, u
    brauzerda buzuq rasm belgisi bo'lib, alt matni bilan slaydga
    tushardi. Shuning uchun ikonkalar qaytadan qo'yiladi, egasiz
    qolgan `<img>` esa o'sha o'lchamdagi rangli blokka aylanadi.
    """
    try:
        from . import html_images

        page = html_images.apply_icons([html], theme)[0][0]
        return html_images.sweep([page], theme)[0]
    except Exception as exc:
        log.warning("Tuzatilgan slayd rasmlari tiklanmadi: %s", exc)
        return html


def _write_chunk(system: str, user: str, count: int) -> List[str]:
    try:
        # Birorta ham yopilgan slayd bo'lmagan javob (filtr kesgan, token
        # chegarasida uzilgan) keyingi modelga o'tkaziladi.
        raw = llm_client._call_openrouter_text(
            system, user, temperature=0.75, max_tokens=4200 * count,
            accept=lambda text: bool(split_slides(text)))
    except llm_client.NoCredits:
        raise
    except Exception as exc:
        log.error("Slayd bo'lagi olinmadi: %s", exc)
        return []
    return split_slides(raw)


def _plain_slide(topic: str, brief: str, number: int, total: int,
                 language: str = "uz", author: str = "") -> str:
    """Hech bir model HTML slayd bermaganda — oddiy ro'yxatli slayd.

    Muqovaga AI kerak emas: u mavzu va muallifdan yig'iladi.
    """
    if number == 1:
        note = (f'<p class="note">{_escape(_CREDIT_LABEL.get(language, _CREDIT_LABEL["uz"]))}: '
                f'{_escape(author)}</p>') if author else ""
        return ('<section class="slide dark"><div class="body">'
                f'<h1 class="title big">{_escape(topic)}</h1>'
                f'<div class="rule"></div>{note}</div></section>')
    target = _LANGUAGE.get(language, _LANGUAGE["uz"])
    kind = "xulosa" if number == total else "mazmun"
    prompt = (
        f'Mavzu: "{topic}". Taqdimotning {number}-slaydi ({kind}): {brief}\n\n'
        f"Matn {target}. Hujjat yoki nutq matnini so'zma-so'z ko'chirmang, "
        "o'z so'zlaringiz bilan yozing.\n"
        'Faqat JSON: {"title": "slayd sarlavhasi (2-7 so\'z)", '
        '"points": [{"key": "kalit so\'z", "text": "bir-ikki to\'liq gap"}]} '
        "— 3 tadan 5 tagacha band."
    )
    try:
        data = llm_client._call_openrouter(
            "Sen taqdimot slaydi matnini yozasan. Faqat JSON qaytar.",
            prompt, temperature=0.5, max_tokens=1500)
    except llm_client.NoCredits:
        raise
    except Exception as exc:
        log.error("%d-slayd zaxira yo'li bilan ham yozilmadi: %s", number, exc)
        return ""
    if not isinstance(data, dict):
        data = {}
    title = str(data.get("title") or brief).strip()
    items = []
    for point in data.get("points") or []:
        if not isinstance(point, dict):
            continue
        text = str(point.get("text") or "").strip()
        if not text:
            continue
        key = str(point.get("key") or "").strip()
        lead = f"<b>{_escape(key)}.</b> " if key else ""
        items.append('<div class="item"><span class="item-dot"></span>'
                     f'<div class="item-text">{lead}{_escape(text)}</div></div>')
    if len(items) < 2:
        log.error("%d-slayd zaxira javobi bo'sh", number)
        return ""
    log.warning("%d-slayd zaxira yo'li bilan yozildi", number)
    return ('<section class="slide"><div class="head">'
            f'<h2 class="title">{_escape(title)}</h2><div class="rule"></div>'
            '</div><div class="body"><div class="list">'
            + "".join(items[:5]) + '</div></div></section>')
