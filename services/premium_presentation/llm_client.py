import json
import logging
import random
import re
import requests
from typing import Callable, Optional

from . import config
from services import timeframe

log = logging.getLogger("llm_client")

# Narrativ burchaklar — mavzuga mos keladigani tanlanadi
_NARRATIVE_ANGLES = [
    ("sabab-oqibat tahlili",
     "Mavzuning asosiy sabablari va ularning oqibatlarini chuqur ko'rsat. "
     "Har 'detail' slaydida bitta sabab va uning aniq oqibatlarini tushuntir."),
    ("muammo-yechim",
     "Avval hozirgi muammolarni aniq ko'rsat, keyin har biriga yechim taklif qil. "
     "'breakdown' va 'detail' slaydlari muammoni, 'application' esa yechimlarni ochsin."),
    ("tarixiy evolyutsiya",
     "Mavzuni vaqt o'qi bo'ylab ko'rsat: qanday boshlangan, qanday rivojlangan, hozir qayerda. "
     "Har 'detail' slaydida muayyan sana yoki davr bo'lsin."),
    ("amaliy qo'llanma",
     "Nazariyadan ko'ra amaliyotga e'tibor ber. Qadamlar, maslahatlar, nima qilish kerak. "
     "Har qadam 'application' slaydlarida batafsil ko'rsatilsin."),
    ("taqqosli tahlil",
     "Turli yondashuvlar, variantlar yoki tomonlarni qiyoslab ko'rsat. "
     "'comparison' slaydlarida ikki tomonning afzalliklari va kamchiliklari aniq ko'rinsin."),
    ("raqamlar va dalillar",
     "Mazmunni aniq statistika, o'lchovlar va faktlar orqali qur. "
     "Har slaydda kamida bitta aniq raqam yoki o'lchov bo'lsin — manbasi bilan."),
    ("kelajakka nazar",
     "Hozirgi holat + kelgusi 5-10 yildagi o'zgarishlar va imkoniyatlar. "
     "'application' va 'synthesis' slaydlari kelajakdagi qadamlarga yo'naltirilsin."),
    ("mif va haqiqat",
     "Keng tarqalgan noto'g'ri tushunchalarni ko'rsat, so'ng haqiqiy ma'lumot bilan rad qil. "
     "Har 'detail' slaydida bitta mif va uning haqiqiy yechimi."),
]

# ─────────────────────────────────────────── ASOSIY SYSTEM PROMPT

SYSTEM_PROMPT_BRIEF = """Sen professional biznes va ilmiy taqdimot mutaxassisissan. Sening slaydlaring aniq, mazmunli va ko'rinishda professional — McKinsey, TED yoki akademik konferensiyalar darajasida.

ASOSIY TAMOYIL:
Har slayd — bitta aniq g'oyani to'liq tushuntiradi. Matn, raqam va vizual element birgalikda ishlaydi.
Mavzudan KELIB CHIQQAN holda kontent yoz — global bozor ulushi, xalqaro statistika har doim ham kerak emas.
Agar mavzu mahalliy, texnik, shaxsiy yoki ijodiy bo'lsa — shu doiradagi faktlar, misollar, tafsilotlar ishlatilsin.

══════════════════════════════════════════════════
SLAYD O'LCHAMI: 13.333" × 7.5"  |  (0,0) = yuqori-chap
══════════════════════════════════════════════════

ELEMENT TURLARI:

① rect
{"type":"rect","x":0.0,"y":0.0,"w":4.2,"h":7.5,"fill":"1B2A4A","radius":false}
• radius:true — faqat kichik aksent bloklari uchun

② text
{"type":"text","x":0.5,"y":1.0,"w":5.5,"h":1.2,"text":"Matn","size":20,"bold":true,"color":"FFFFFF","align":"left","font":"Calibri"}
• Ko'p qatorli matn: \n bilan ajrating
• size: sarlavha 28–40pt | kichik sarlavha 16–22pt | tana 13–16pt | izoh 11–12pt
• font: "Calibri" | "Georgia" | "Trebuchet MS"

③ circle — kichik aksent uchun, d ≤ 2.0", slayd ichida
{"type":"circle","x":3.8,"y":0.6,"d":0.9,"fill":"E8A020"}

④ image — AI rasm
{"type":"image","x":7.5,"y":0.8,"w":5.5,"h":5.8,"prompt":"detailed descriptive English prompt, photorealistic, professional, 20-30 words"}

  MAJBURIY: BIRINCHI slaydda albatta bitta image elementi bo'lsin.
  Undan tashqari har 4 slaydda kamida bitta image bo'lsin.
  ⚠️ Rasm promptida MATN so'ramang — "text", "label", "caption", "sign"
  yozilgan rasm buzuq chiqadi. Faqat vizual tasvir tasvirlansin.

⑤ kpi — ko'rsatkich kartochkasi (bitta katta raqam + izoh)
{"type":"kpi","x":1.0,"y":4.2,"w":3.4,"h":1.8,"value":"78%","label":"O'simlik turlarining ulushi","fill":"F4F6F9","color":"1B2A4A"}

  Bitta muhim raqamni diagramma qilmang — kpi kartochkasi qiling.
  Yonma-yon 2–4 ta kpi qo'yilsa, slayd ko'rsatkichlar qatoriga aylanadi.

⑥ chart — diagramma
{"type":"chart","x":1.0,"y":1.8,"w":8.5,"h":4.2,
 "chart_type":"column",   // column | bar | line | area | pie | donut | radar | scatter
 "chart_title":"Diagramma sarlavhasi",
 "caption":"Bu diagrammada nima ko'rsatilgani — aniq va ravshan izohlang (1-2 jumla)",
 "categories":["Kat1","Kat2","Kat3"],
 "series":[{"name":"Qator1","values":[45,30,25]}]}

  MAJBURIY: har taqdimotda KAMIDA 2 ta diagramma bo'lsin, 4 tadan oshmasin.

  Turni ma'lumot vazifasiga qarab tanlang, hammasini "column" qilmang:
  → column/bar — kattaliklarni taqqoslash
  → line/area  — vaqt bo'yicha o'zgarish
  → pie/donut  — butunning ulushlari (5 tagacha bo'lak)
  → radar      — bir nechta mezon bo'yicha profil (5-7 mezon)
  → scatter    — ikki son o'rtasidagi bog'liqlik

  Har qanday mavzuda raqam topiladi — uni izlang:
  → tarixiy sanalar va davrlar, ulushlar va foizlar, bosqichlar soni,
    tarqalish geografiyasi, o'sish sur'ati, taqqoslash ko'rsatkichlari
  → falsafiy yoki adabiy mavzuda ham: asrlar bo'yicha tarqalish, mualliflar
    soni, tadqiqotlar ulushi, ta'sir darajasi
  Raqam haqiqiy va mavzuga tegishli bo'lsin, o'ylab topilgan bo'lmasin.

  MAJBURIY: "caption" maydoni HAR DOIM to'ldirilsin — diagrammada nima ko'rsatilgani
  aniq bir-ikki jumlada yozilsin. Masalan:
  "{YEAR_SPAN} yillarda O'zbekistonda yalpi ichki mahsulot o'sishi (mlrd. so'm)"

⑦ icon — tayyor ikonka (rasm generatsiyasi EMAS, lokal fayl)
{"type":"icon","x":1.2,"y":2.4,"w":0.7,"h":0.7,"icon":"innovation","fill":"2A78D6","color":"FFFFFF","shape":"circle"}
• "icon" — quyidagi ro'yxatdagi ANIQ nom bo'lsin
• shape: "circle" (rangli doira ichida) | "square" | "none" (fonsiz)
• Ikonkani matn yoki blok yoniga qo'ying — bo'sh joyga emas

⑧ infographic — ikonkali kompozitsiya (ENG KUCHLI element)
{"type":"infographic","x":0.6,"y":1.9,"w":12.1,"h":4.4,"preset":"cards",
 "items":[{"title":"Qisqa sarlavha","text":"1-2 jumla izoh","icon":"idea","value":"{LAST_YEAR}"}]}

• Sen faqat MAZMUN berasan — koordinata, rang, chiziq, raqamni kod hisoblaydi
• items: 3–5 band (6 dan oshmasin), har bandda "icon" nomi MAJBURIY
• presetlar:
  → "cards"    — teng darajali 3–5 xususiyat/omil/yo'nalish
  → "steps"    — tartibli bosqichlar (raqamlanadi)
  → "timeline" — yillar yoki davrlar ketma-ketligi ("value" ga yil yozing)
  → "cycle"    — takrorlanadigan aylanma jarayon
  → "pyramid"  — darajali ierarxiya (yuqoridan pastga kengayadi)
• title: 2–4 so'z | text: 1–2 qisqa jumla (90 belgigacha)

  MAJBURIY: har taqdimotda KAMIDA 2 ta infographic bo'lsin.
  Bullet ro'yxati o'rniga infographic ishlating — u ancha professional ko'rinadi.

⑨ scheme — tuzilma sxemasi (kartochka to'ri EMAS)
{"type":"scheme","x":0.8,"y":1.7,"w":11.7,"h":4.8,
 "scheme_kind":"process",   // hierarchy | components | process | cycle | levels
 "scheme_root":"Markazdagi tushuncha",
 "items":[{"title":"Tarmoq nomi","text":"tarkibi, vergul bilan, 2-3 ta"}]}

• Sen faqat MAZMUN berasan — shaklni kod tanlaydi: daraxt, radial,
  oqim, chevron, halqa, bosqichlar yoki piramida
• scheme_kind mazmunga qarab: bo'linadigan butun — hierarchy, teng
  qismlar — components, ketma-ket bosqichlar — process, takrorlanadigan
  jarayon — cycle, bir-birining ustiga qurilgan qatlamlar — levels
• items: 2-6 ta tarmoq; "title" — 1-3 so'z, "text" — tarkibi (2-3 ta
  qisqa ibora, vergul bilan ajratilgan) yoki bo'sh
• Tizim, tuzilma, jarayon yoki tasnif haqidagi slaydda infographic
  o'rniga SHUNI ishlating — u butunlay boshqacha ko'rinadi

══════════════════════════════════════════════════
BITTA SLAYD — BITTA INSTRUMENT (eng muhim qoida):

Instrument — image, chart, infographic, scheme yoki kpi kartochkalari
qatori. Bitta slaydda ULARDAN FAQAT BITTASI bo'lsin.

✗ Rasm + diagramma bir varaqda — ular bir-birini yopadi va o'quvchi
  ikkalasini birdan o'zlashtira olmaydi
✗ Diagramma + kartochkalar qatori — slayd raqamlar to'plamiga aylanadi
✓ Diagramma + uni tushuntiruvchi matn
✓ Rasm + uni tushuntiruvchi matn

Qaysi birini tanlash — slayd nimani aytmoqchi bo'lsa o'shanga qarab:
  → raqam gapiradi (o'sish, ulush, taqqoslash)   → chart
  → mavzuni ko'z bilan ko'rsatish kerak          → image
  → bandlar, bosqichlar, davrlar                 → infographic
  → tizim, tuzilma, tasnif, jarayon oqimi        → scheme
  → bitta hal qiluvchi raqam                     → kpi

TANLANGAN INSTRUMENT TO'LIQ YORITILSIN:
• U slaydning kamida yarmini egallasin — kichik qilib burchakka qo'ymang
• Yonida yoki ostida uni TUSHUNTIRUVCHI matn bo'lsin: nima ko'rsatilgan,
  raqamlar nimani anglatadi va bundan qanday xulosa chiqadi
• Diagramma uchun "caption" MAJBURIY; rasm va infografika esa slayd
  matnida izohlansin
• Bitta instrument bilan slayd bo'sh ko'rinmaydi — bo'shagan joy izoh,
  tahlil va misol bilan to'ldiriladi

══════════════════════════════════════════════════
TUZILMA TAKRORLANMASIN:

✗ Ketma-ket ikki slaydda bir xil tuzilma (masalan ikkalasida ham
  to'rtta ikonkali kartochka — faqat matni boshqa)
✗ DASTLABKI 5 SLAYD bir-birini takrorlasa — taqdimot aynan shu yerda
  baholanadi

Har slaydda boshqa vosita va boshqa joylashuv bo'lsin. Masalan:
  1 — mavzu sahifasi (rasm + sarlavha)
  2 — infographic (cards)
  3 — scheme yoki chart
  4 — rasm + tahlil matni
  5 — infographic (steps/timeline) yoki kpi qatori
Bu shunchaki misol — mavzuga qarab o'zgartiring, lekin ketma-ket
takrorlanmasin.

══════════════════════════════════════════════════
MAVJUD IKONKA NOMLARI (faqat shu ro'yxatdan tanlang):
agriculture, ai, airplane, algorithm, architecture, art, atom, award, basketball, behavior,
biology, brain, building, business, calendar, car, certificate, chart, chemistry, cinema,
city, climate, code, communication, computer, construction, contract, cooking, country,
court, crime, culture, database, democracy, design, diploma, dna, doctor, economics,
education, electricity, emotion, energy, environment, family, finance, fire, fitness, flag,
food, football, forest, geography, globe, government, graduation, health, history, hospital,
house, idea, industry, innovation, internet, investment, justice, language, law, leadership,
literature, logistics, management, map, marketing, math, medicine, mental, microscope,
military, money, moon, mountain, museum, music, nature, network, nuclear, nutrition, ocean,
peace, pharmacy, philosophy, photography, physics, planet, politics, pollution, poverty,
privacy, project, psychology, rain, recycling, research, rights, robot, running, satellite,
school, science, security, ship, social, solar, space, sport, star, startup, statistics,
strategy, success, surgery, swimming, target, team, technology, tennis, theater, time,
trade, train, transport, university, vaccine, volleyball, war, water, welfare, wind,
writing, yoga
Mavzuga eng yaqinini tanlang. Ro'yxatda aynan mos nom bo'lmasa — ma'no jihatdan
eng yaqinini oling (masalan "fotosintez" → "biology", "bank" → "finance").

══════════════════════════════════════════════════
MATN FORMATI — AI o'zi tanlaydi:

Qachon BULLET ro'yxat:
  • Alohida, teng darajali bandlar (3–6 ta)
  • Qadamlar, xususiyatlar, imkoniyatlar ro'yxati
  Format: "• Birinchi band\n• Ikkinchi band\n• Uchinchi band"

Qachon TO'LIQ PARAGRAF:
  • Tushuntirish, tahlil, kontekst, sabablar
  • Bir-biri bilan bog'liq fikrlar ketma-ketligi
  Format: "Bu hodisa shundan kelib chiqadiki, ... Natijada ... va shu tufayli ..."

Aralash (avval paragraf, keyin bullet):
  • Kirish jumlasi, so'ngra asosiy bandlar
  Format: "Asosiy omillar:\n• Birinchi\n• Ikkinchi"

TAQIQLANGAN: hamma slaydda hamisha bullet — formatsiz, bir xil tuzilma.

══════════════════════════════════════════════════
PROFESSIONAL LAYOUT TIZIMI:

[A] CHAP PANEL + O'NG KONTENT
  • Chap: to'q panel (x=0, w=4.0–4.5, h=7.5) — sarlavha, kichik izoh
  • O'ng: och fon, 3–5 faktblok yoki diagramma + matn

[B] YUQORI TASMA + PASTKI KONTENT
  • Yuqori: to'q tasma (y=0, h=1.6–2.0, w=13.333) — sarlavha
  • Pastda: 2–3 ustunli bloklar yoki batafsil matn + diagramma

[C] IKKI USTUN TAQQOSLASH
  • Chap ustun (w≈6.3): birinchi tomon — sarlavha, matn, metrika
  • Ajratuvchi (w=0.04, to'q rang)
  • O'ng ustun (w≈6.3): ikkinchi tomon — sarlavha, matn, metrika

[D] KARTA TIZIMI (3–4 ta)
  • Yuqori tasma + 3–4 teng karta
  • Har karta: sarlavha + katta raqam/belgi + 2–4 qator izoh

[E] KONTENT + DIAGRAMMA
  • Chap: sarlavha + 3–5 qator tushuntirish matni
  • O'ng: diagramma (chart element) — rasm bilan birga EMAS

[F] YARIM MATN + YARIM RASM (har 6 varoqda KAMIDA 1 ta MAJBURIY)
  • Chap yarmi (x=0.4, w=6.0): to'q panel yoki och fon + sarlavha + 4–6 qator matn
  • O'ng yarmi (x=7.0, w=6.0): image element — mavzuning vizual ifodasi
  Bu layout: tabiat, arxitektura, texnologiya, inson, san'at mavzulari uchun ideal.
  Rasm prompti 20–30 so'z, inglizcha, photorealistic.

══════════════════════════════════════════════════
MATN HAJMI — MAJBURIY:

Har slaydda KAMIDA 80 so'z matn bo'lsin (sarlavhalar bilan birga).
Har faktblok/karta ichida: sarlavha + 2–4 qator izoh.
Tana matni 13–16pt — o'qib bo'ladigan, mazmunli jumlalar.

YUQORI CHEGARA — bu o'lchangan, taxmin emas:
  • Instrumenti bor slaydda jami 90–130 so'z (matn yarim ustunga tushadi)
  • Instrumenti yo'q slaydda 160–240 so'z (matn butun enni egallaydi)
Bundan ortig'i 14pt da qutiga sig'maydi va quyidagi blok ustiga minib
qoladi. Ko'proq aytadigan gap bo'lsa — uni keyingi slaydga oling, matnni
siqib tiqmang.

══════════════════════════════════════════════════
RANG QOIDALARI:

• To'q fon → oq/juda och matn (FFFFFF yoki F0F0F0)
• Och fon → to'q matn (primary yoki 1A1A2A)
• TAQIQLANGAN: o'xshash rangdagi fon va shakl (masalan fon #1B3A6B + shakl #1F4080)
• Accent rang — faqat eng muhim elementlar uchun (sarlavha, raqam, aksent chiziq)

══════════════════════════════════════════════════
ROLLAR BO'YICHA:

hook       → Kuchli ochilish. Sarlavha 34–40pt. Katta focal raqam/fakt (52–60pt).
              3–4 qator izoh: nima haqida, nima uchun muhim.

context    → Mavzu fonini tushuntirish. 5–8 qator tuzilmali matn yoki 2 ta faktblok.
              Diagramma qo'shish mumkin (trend, tarix).

breakdown  → Tuzilmali tahlil. [B] yoki [D] layout.
              3–4 blok, har birida sarlavha + 3 qator izoh. Diagramma mumkin.

detail     → Chuqur tafsilot. Aniq raqam, sana, misol MAJBURIY.
              Paragraf formatida 6–10 qator matn. Diagramma juda mos keladi.

comparison → [C] layout MAJBURIY. Har ustunda sarlavha + 4–6 qator matn + metrika.
              Diagramma (bar/column) taqqoslashni kuchaytiradi.

application → Amaliy, qadamli. Bullet yoki raqamlangan qadamlar.
              Har qadam 2–3 qator tushuntirish. Diagramma (line/column) mumkin.

synthesis  → Final xulosa. 4–5 asosiy xulosa + har biri 1–2 qator izoh.
              Yakunlovchi chaqiriq yoki asosiy tavsiya.

Yuqorida "diagramma mumkin" deyilgan joylarda ham qoida bitta: slaydda
allaqachon rasm yoki infografika bo'lsa, diagramma QO'SHILMAYDI.

══════════════════════════════════════════════════
DIAGRAMMA UCHUN MA'LUMOTLAR:

Faqat REAL, MANTIQIY ma'lumotlar ishlatilsin.
Agar aniq raqam ma'lum bo'lmasa — taxminiy lekin realistik qiymatlar.
Kategoriyalar: 3–7 ta (ko'p bo'lsa o'qilmaydi).
Qiymatlar: bir seriyada 3–7 ta son.

══════════════════════════════════════════════════
QATTIQ TAQIQLAR:

✗ Slaydning yarmi bo'sh (40%+ bo'sh joy)
✗ Faqat sarlavha va raqam — izoh matni yo'q
✗ Dekorativ katta doiralar slayd chegarasidan tashqarida
✗ Mavzudan uzilgan global statistika (kerak bo'lmasa)
✗ Hamma slaydda bir xil bullet format
✗ Bitta slaydda ikkita instrument (rasm + diagramma, diagramma + kartochka)
✗ Chekka: matn bloklari slayd chegarasidan ≥ 0.3" masofada

══════════════════════════════════════════════════
JAVOB: faqat sof JSON (markdown, ``` yoki boshqa matn YO'Q):

{
  "topic": "mavzu",
  "theme": {"primary":"1B2A4A","accent":"E8A020","light":"F4F6F9","heading_font":"Calibri","body_font":"Calibri"},
  "slides": [
    {
      "index": 1, "role": "hook",
      "title": "Sarlavha (QA uchun)",
      "key_text": "Kamida 3 ta to'liq jumla — slayd asosiy g'oyasi",
      "canvas": {
        "background": "F4F6F9",
        "elements": [...]
      }
    }
  ]
}"""

# ─────────────────────────────────────────── REGENERATE PROMPT

ICON_NAMES = (
    "agriculture, ai, airplane, algorithm, architecture, art, atom, award, basketball, behavior, biology, brain, building, business, calendar, car, certificate, chart, chemistry, cinema, city, climate, code, communication, computer, construction, contract, cooking, country, court, crime, culture, database, democracy, design, diploma, dna, doctor, economics, education, electricity, emotion, energy, environment, family, finance, fire, fitness, flag, food, football, forest, geography, globe, government, graduation, health, history, hospital, house, idea, industry, innovation, internet, investment, justice, language, law, leadership, literature, logistics, management, map, marketing, math, medicine, mental, microscope, military, money, moon, mountain, museum, music, nature, network, nuclear, nutrition, ocean, peace, pharmacy, philosophy, photography, physics, planet, politics, pollution, poverty, privacy, project, psychology, rain, recycling, research, rights, robot, running, satellite, school, science, security, ship, social, solar, space, sport, star, startup, statistics, strategy, success, surgery, swimming, target, team, technology, tennis, theater, time, trade, train, transport, university, vaccine, volleyball, war, water, welfare, wind, writing, yoga"
)

SYSTEM_PROMPT_REGEN = """Sen professional biznes taqdimot slaydini qayta loyihalaysan.

Slayd o'lchami: 13.333" × 7.5". Element turlari: rect, text, circle, image, chart, kpi, icon, infographic.
Kpi formati: {"type":"kpi","x":1.0,"y":4.2,"w":3.4,"h":1.8,"value":"78%","label":"izoh","fill":"F4F6F9","color":"1B2A4A"}

Icon formati: {"type":"icon","x":1.2,"y":2.4,"w":0.7,"h":0.7,"icon":"<ro'yxatdagi nom>","fill":"2A78D6","color":"FFFFFF","shape":"circle"}
Scheme formati: {"type":"scheme","x":0.8,"y":1.7,"w":11.7,"h":4.8,"scheme_kind":"hierarchy|components|process|cycle|levels","scheme_root":"markaz","items":[{"title":"Tarmoq","text":"tarkibi, vergul bilan"}]}
  → tizim/tuzilma/jarayon uchun; shaklni kod tanlaydi, sen faqat mazmun berasan
Infographic formati: {"type":"infographic","x":0.6,"y":1.9,"w":12.1,"h":4.4,"preset":"cards|steps|timeline|cycle|pyramid","items":[{"title":"...","text":"...","icon":"<nom>","value":"{LAST_YEAR}"}]}
  → items 3-5 ta, har birida icon nomi; koordinatani kod hisoblaydi, sen faqat mazmun ber
Ikonka nomlari: {ICONS}

Chart formati: {"type":"chart","x":1.0,"y":2.0,"w":8.0,"h":4.0,"chart_type":"column|bar|line|area|pie|donut|radar|scatter","chart_title":"...","categories":[...],"series":[{"name":"...","values":[...]}]}

Muammoni to'liq bartaraf etgan YANGI professional layout bilan qaytар.

Qoidalar:
- role, index o'zgartirma
- Matn hajmi: kamida 80 so'z; instrumentli slaydda 130 so'zdan, instrumentsizda
  240 so'zdan OSHMASIN — ortig'i qutiga sig'maydi va ustma-ust tushadi
- Professional layout: chap panel, yuqori tasma, ustun tizimi
- To'q fon → oq matn; och fon → to'q matn
- Har taqdimotda kamida 2 ta chart, 2 ta image va 2 ta infographic bo'lsin; birinchi slaydda image MAJBURIY
- BITTA SLAYDDA BITTA INSTRUMENT: image, chart, infographic va kpi dan faqat bittasi.
  Qolgan joyni matn bilan to'ldir va o'sha instrumentni to'liq izohla
- Ro'yxatli slaydni bullet emas, infographic qilib bering
- Muhim raqamlarni kpi kartochkasi qilib ko'rsat (yonma-yon 2-4 ta)
- Chart uchun raqamni har mavzuda topish mumkin: sanalar, ulushlar, bosqichlar, taqqoslash
- Agar muammoda "keraksiz" yoki "o'chir" deyilsa — o'sha elementni OLIB TASHLА, o'rnini matn bilan to'ldir
- Faqat sof JSON qaytar

Format:
{
  "index": <n>, "role": "<role>",
  "title": "<sarlavha>", "key_text": "<kamida 3 jumla>",
  "canvas": {"background": "<hex>", "elements": [...]}
}""".replace("{ICONS}", ICON_NAMES)


# ─────────────────────────────────────────── YORDAMCHI FUNKSIYALAR

def _clean_json(raw: str) -> str:
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end + 1]
    return cleaned


def _salvage_partial_json(text: str) -> dict | None:
    try:
        slides_start = text.find('"slides"')
        if slides_start == -1:
            return None
        arr_start = text.find("[", slides_start)
        if arr_start == -1:
            return None

        depth = 0
        i = arr_start
        last_good_end = arr_start + 1
        while i < len(text):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    last_good_end = i + 1
            elif ch == "]" and depth == 0:
                break
            i += 1

        slides_str = text[arr_start:last_good_end] + "]"
        slides = json.loads(slides_str)
        if not slides:
            return None

        try:
            prefix = text[:arr_start]
            topic_match = re.search(r'"topic"\s*:\s*"([^"]+)"', prefix)
            topic = topic_match.group(1) if topic_match else "Mavzu"
            theme_start = prefix.find('"theme"')
            theme = {"primary": "1B2A4A", "accent": "E8A020", "light": "F4F6F9",
                     "heading_font": "Calibri", "body_font": "Calibri"}
            if theme_start != -1:
                t_open = prefix.find("{", theme_start)
                t_close = prefix.find("}", t_open)
                if t_open != -1 and t_close != -1:
                    theme = json.loads(prefix[t_open:t_close + 1])
        except Exception:
            topic = "Mavzu"
            theme = {"primary": "1B2A4A", "accent": "E8A020", "light": "F4F6F9",
                     "heading_font": "Calibri", "body_font": "Calibri"}

        return {"topic": topic, "theme": theme, "slides": slides}
    except Exception as ex:
        log.warning("Partial salvage muvaffaqiyatsiz: %s", ex)
        return None


# Ishlab turgan model jarayon davomida eslab qolinadi: ro'yxatning boshidagi
# model hisobda bo'lmasa, uni har so'rovda qayta sinash keraksiz kechikish
# beradi. Bot qayta ishga tushganda tekshiruv yangidan boshlanadi.
_WORKING = {}


# Admin panelda premium taqdimot uchun alohida tanlangan model. Bu yerda
# turadi, chunki generatsiya sinxron oqimda (`run_in_executor`) ishlaydi va
# u yerdan bazaga murojaat qilib bo'lmaydi; tanlovni Telegram tomoni
# generatsiya boshlanishidan oldin shu yerga yozib qo'yadi.
_preferred = {}


def set_text_model(model_id: str) -> None:
    """Premium taqdimot uchun tanlangan matn modelini o'rnatadi."""
    model_id = (model_id or "").strip()
    if not model_id or _preferred.get("text") == model_id:
        return
    _preferred["text"] = model_id
    # Avval boshqa model ishlayotgan bo'lsa, u eslab qolingan — yangi
    # tanlov birinchi bo'lib sinalishi uchun tozalanadi.
    _WORKING.pop("text", None)
    log.info("Premium taqdimot matn modeli: %s", model_id)


def _models(kind: str) -> list:
    """Sinaladigan modellar — avval tanlangani, keyin ishlagani ma'lum bo'lgani."""
    chain = (config.OPENROUTER_TEXT_MODELS if kind == "text"
             else config.OPENROUTER_VISION_MODELS)
    chain = list(chain)
    for model in (_WORKING.get(kind), _preferred.get(kind)):
        if not model:
            continue
        chain = [model] + [item for item in chain if item != model]
    return chain


# Bitta taqdimotga qancha token ketganini yozib boradi. Narxni taxmin
# qilish o'rniga logdan aniq ko'rinsin: modellar va hajm o'zgarganda
# taxmin eskiradi, hisob esa eskirmaydi.
USAGE = {"calls": 0, "input": 0, "output": 0}


def reset_usage() -> None:
    USAGE.update(calls=0, input=0, output=0)


def usage_report() -> str:
    """Logga yoziladigan qisqa hisobot."""
    return (f"{USAGE['calls']} so'rov, "
            f"{USAGE['input']:,} kirish + {USAGE['output']:,} chiqish tokeni")


def _count(data: dict) -> None:
    usage = (data.get("usage") if isinstance(data, dict) else None) or {}
    USAGE["calls"] += 1
    USAGE["input"] += int(usage.get("prompt_tokens") or 0)
    USAGE["output"] += int(usage.get("completion_tokens") or 0)


# Provayder javobni to'xtatganini bildiradigan sabablar. Gemini hujjat
# yoki nutq matniga o'xshash javobni "RECITATION" deb kesadi — farmon va
# davlat choralari haqidagi mavzularda bu tez-tez bo'ladi. HTTP 200
# keladi, lekin matn bo'sh yoki chala.
_BLOCKED = {"content_filter", "safety", "recitation", "prohibited_content",
            "blocklist", "spii", "image_safety", "error"}


def _content(data: dict) -> str:
    choices = (data or {}).get("choices") or [{}]
    message = (choices[0] or {}).get("message") or {}
    return str(message.get("content") or "")


def _unusable(data: dict) -> str:
    """Javob ishlatib bo'lmaydigan bo'lsa — sababi, aks holda ""."""
    if not isinstance(data, dict):
        return "javob JSON obyekt emas"
    if data.get("error"):
        return f"provayder xatosi: {str(data['error'])[:200]}"
    choices = data.get("choices") or []
    if not choices:
        return "javobda choices yo'q"
    choice = choices[0] or {}
    finish = str(choice.get("finish_reason") or "").lower()
    native = str(choice.get("native_finish_reason") or "").lower()
    if finish in _BLOCKED or native in _BLOCKED:
        return f"javob to'xtatildi ({native or finish})"
    if not _content(data).strip():
        return f"bo'sh javob (finish_reason={native or finish or '?'})"
    return ""


def _request(kind: str, payload: dict, timeout: int = 180,
             accept: Optional[Callable[[str], bool]] = None) -> dict:
    """So'rovni ro'yxatdagi modellar bilan navbatma-navbat bajaradi.

    Model yaroqsiz bo'lsa (hisobda yo'q, nomi o'zgargan) yoki provayder
    javob bermasa keyingisiga o'tiladi. Shu sababli model nomini
    almashtirish xizmatni to'xtatib qo'yolmaydi.

    HTTP 200 ham yetarli emas: javob bo'sh, filtr bilan to'xtatilgan
    yoki `accept` uni rad etsa ham keyingi model sinaladi. Ilgari bunday
    javob "muvaffaqiyatli" hisoblanib, slayd jimgina tashlab ketilardi.
    """
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError(
            "OpenRouter kaliti topilmadi — muhitda AI_INTEGRATIONS_OPENROUTER_API_KEY "
            "yoki OPENROUTER_API_KEY bo'lishi kerak"
        )

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    chain = _models(kind)
    last_error = None
    # Hech bir model to'liq javob bermasa, bo'sh bo'lmagan eng birinchi
    # javob qaytariladi — undan qisman foydalanish mumkin.
    partial = None
    rejected = False
    for index, model in enumerate(chain):
        try:
            resp = requests.post(config.OPENROUTER_URL, headers=headers,
                                 json={**payload, "model": model}, timeout=timeout)
            afford = _affordable(resp, payload)
            if afford:
                # Hisobdagi mablag' so'ralgan javob uzunligini qoplamaydi.
                # Boshqa modelga o'tish foyda bermaydi (hisob bitta) —
                # o'sha model kichikroq chegara bilan qayta so'raladi.
                log.warning("OpenRouter mablag'i %s tokenga yetadi (%s so'ralgan) "
                            "— chegara kamaytirildi", afford,
                            payload.get("max_tokens"))
                resp = requests.post(
                    config.OPENROUTER_URL, headers=headers,
                    json={**payload, "model": model, "max_tokens": afford},
                    timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            status = getattr(getattr(e, "response", None), "status_code", "?")
            body = getattr(getattr(e, "response", None), "text", "")[:200]
            last_error = e
            if index + 1 < len(chain):
                log.warning("Model ishlamadi (%s, HTTP %s): %s — %s ga o'tildi",
                            model, status, body, chain[index + 1])
                continue
            if partial is not None:
                break
            log.error("Ro'yxatdagi hamma model ishlamadi (oxirgisi %s, HTTP %s): %s",
                      model, status, body)
            raise
        except ValueError as e:
            # 200 keldi, lekin tanasi JSON emas (provayder sahifasi).
            last_error = e
            log.warning("Model javobi JSON emas (%s): %s", model, e)
            continue
        _count(data)
        reason = _unusable(data)
        if not reason and accept is not None and not accept(_content(data)):
            reason = "javobda kerakli qism yo'q"
        choice = ((data.get("choices") or [{}])[0] or {}) if isinstance(data, dict) else {}
        if choice.get("finish_reason") == "length":
            log.warning("%s javobi token chegarasida kesildi (max_tokens=%s)",
                        model, payload.get("max_tokens"))
        if reason:
            rejected = True
            last_error = RuntimeError(f"{model}: {reason}")
            if partial is None and _content(data).strip():
                partial = data
            log.warning("Model javobi yaroqsiz (%s): %s%s", model, reason,
                        f" — {chain[index + 1]} ga o'tildi"
                        if index + 1 < len(chain) else "")
            continue
        # Oldingi model mazmun sababli yiqilgan bo'lsa, zaxira model
        # eslab qolinmaydi: keyingi so'rovlar yana tanlangan modeldan
        # boshlanadi (zaxira odatda qimmatroq).
        if not rejected and _WORKING.get(kind) != model:
            log.info("%s modeli: %s", "Matn" if kind == "text" else "Vision", model)
            _WORKING[kind] = model
        return data
    if partial is not None:
        log.warning("Hech bir model to'liq javob bermadi — qisman javob olindi")
        return partial
    raise last_error if last_error else RuntimeError("Model ro'yxati bo'sh")


_AFFORD = re.compile(r"can only afford (\d+)", re.IGNORECASE)
# Bundan qisqa javobga bitta slayd ham sig'maydi.
_MIN_TOKENS = 1500


def _affordable(resp, payload: dict) -> int:
    """402 "can only afford N" bo'lsa — qayta so'rash uchun N (aks holda 0)."""
    if getattr(resp, "status_code", 0) != 402:
        return 0
    match = _AFFORD.search(getattr(resp, "text", "") or "")
    if not match:
        return 0
    afford = int(match.group(1)) - 50
    if afford < _MIN_TOKENS or afford >= int(payload.get("max_tokens") or 0):
        return 0
    return afford


def _with_today(system_prompt: str) -> str:
    """System promptga bugungi sanani qo'yadi.

    Promptdagi yil misollari ({LAST_YEAR}, {YEAR_SPAN}) va yil qoidasi har
    chaqiruvda qaytadan hisoblanadi — shuning uchun bot yangi yilga
    o'tganda ham qayta ishga tushirish shart emas.
    """
    history = timeframe.history_years()
    prompt = system_prompt.replace("{LAST_YEAR}", str(timeframe.last_full_year()))
    prompt = prompt.replace("{YEAR_SPAN}", f"{history[0]}–{history[-1]}")
    return prompt + "\n\n" + timeframe.year_rule("uz")


def _call_openrouter(system_prompt: str, user_prompt: str, temperature: float = 0.7,
                     max_tokens: int = 16000) -> dict:
    payload = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _with_today(system_prompt)},
            {"role": "user", "content": user_prompt},
        ],
    }
    raw = _request("text", payload)["choices"][0]["message"]["content"]
    cleaned = _clean_json(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        log.error("JSON parse xato. Xom javob (2000 belgi): %s", raw[:2000])
        salvaged = _salvage_partial_json(cleaned)
        if salvaged:
            log.warning("Partial JSON salvage: %d slayd", len(salvaged.get("slides", [])))
            return salvaged
        raise


def _call_openrouter_text(system_prompt: str, user_prompt: str,
                          temperature: float = 0.3,
                          max_tokens: int = 1800,
                          accept: Optional[Callable[[str], bool]] = None) -> str:
    """Oddiy matn so'raydi — JSON rejimisiz.

    Manbani siqishda javob JSON emas, nasr bo'lishi kerak; `_call_openrouter`
    esa har doim `json_object` rejimida so'raydi. `accept` javobni rad
    etsa, keyingi model sinaladi.
    """
    payload = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": _with_today(system_prompt)},
            {"role": "user", "content": user_prompt},
        ],
    }
    data = _request("text", payload, accept=accept)
    return _content(data).strip()


# ─────────────────────────────────────────── DARAJA INSTRUCTIONLARI

LEVEL_INSTRUCTIONS = {
    1: (
        "DARAJA: MAKTAB DARSLIGI (bolalar uchun)\n"
        "• Tilni JUDA oddiy yoz — 10-14 yoshli o'quvchi tushunadigan so'zlar\n"
        "• Har murakkab g'oyani kundalik hayotdan olingan sodda misol bilan tushuntir\n"
        "• Ilmiy atamalar ishlatma; agar kerak bo'lsa, darhol oddiy tilda izohlat\n"
        "• Har slaydda BITTA asosiy g'oya — ko'p ma'lumot yuklamaslik\n"
        "• 'Bu shuni anglatadi...', 'Tasavvur qiling...', 'Masalan...' kabi iboralar ko'p ishlatilsin\n"
        "• Qisqa jumlalar (10-12 so'zdan oshmasin), do'stona ton\n"
        "• Rasmlar va vizual element ko'proq, text kamroq — bolalar uchun vizual muhim\n"
        "• Mavzuni chuqur tushuntir — sodda til bilan, lekin to'liq"
    ),
    2: (
        "DARAJA: STUDENT (oliy ta'lim)\n"
        "• Tartibli, mantiqiy tuzilma: kirish → nazariya → misollar → xulosa\n"
        "• Aniq ma'lumotlar va raqamlar, iloji bo'lsa manba bilan\n"
        "• Atamalar ishlatilsin, lekin birinchi marta qo'llanilganda qisqacha tushuntirma berilsin\n"
        "• Har slayd mavzuning bir jihatini chuqur yoritsin — umumiy gap emas\n"
        "• Professional, lekin haddan tashqari akademik emas — o'quvchiga qulay\n"
        "• Grafik/jadval kerak joyda ishlatilsin — ma'lumotni ko'rsatish uchun\n"
        "• Mavzuni to'liq tushuntir: 'nima', 'nima uchun', 'qanday' savollariga javob ber"
    ),
    3: (
        "DARAJA: AKADEMIK (ilmiy/professional)\n"
        "• Ilmiy uslub — aniq faktlar, statistika, terminologiya\n"
        "• Har g'oya dalil va manba bilan asoslansin (agar umumiy bilim bo'lsa — aniq izohlat)\n"
        "• Metodologiya, tahlil, xulosa aniq ajratilsin va ketma-ketlikda kelsin\n"
        "• Terminologiya to'g'ri, to'liq va izchil ishlatilsin\n"
        "• Har slaydda kamida bitta aniq ilmiy fakt, raqam yoki tadqiqot natijasi\n"
        "• Formal akademik til — his-tuyg'u emas, dalil asosidagi bayonot\n"
        "• Mavzuni eng chuqur darajada yoritsin: sabab, mexanizm, ta'sir, xulosa"
    ),
}


PRESENTATION_LANGUAGE_INSTRUCTIONS = {
    "uz": "Barcha slayd matnlari, sarlavhalari va izohlari faqat o‘zbek tilida bo‘lsin.",
    "ru": "Весь текст слайдов, заголовки и подписи должны быть только на русском языке.",
    "en": "All slide text, headings, and captions must be written only in English.",
}


def _language_instruction(language: str) -> str:
    return PRESENTATION_LANGUAGE_INSTRUCTIONS.get(
        language, PRESENTATION_LANGUAGE_INSTRUCTIONS["uz"]
    )


# ─────────────────────────────────────────── ASOSIY FUNKSIYALAR

def _base_rules(topic: str, slide_count: int, level: int = 2) -> str:
    """Barcha brief va chunk promptlari uchun umumiy qoidalar."""
    level_instr = LEVEL_INSTRUCTIONS.get(level, LEVEL_INSTRUCTIONS[2])
    return (
        f"• Slaydlar soni: AYNAN {slide_count} ta\n"
        "• Matn hajmini slayd maqsadiga mos tanla: vizual slaydda qisqa, tahliliy slaydda batafsil\n"
        "• ASOSIY MAQSAD: mavzuni chuqur va tabiiy tushuntirish — har slayd bitta jihatni ochsin\n"
        "• Hozirgi kun bilan keraksiz taqqoslash QILMA — mavzuning o'zini yorit\n"
        "• Mavzuga mos ma'lumotlar — global statistika faqat kerak bo'lganda\n"
        "• Matn formati (bullet/paragraf) mazmunga qarab tanlangsin\n"
        "• Rang kontrasti qat'iy: to'q fon → oq matn, och fon → to'q matn\n"
        "• key_text mazmunli bo'lsin, lekin sun'iy ravishda cho'zilmasin\n"
        "• Birinchi slaydda image MAJBURIY; har taqdimotda kamida 2 ta image va 2 ta chart\n"
        "• BITTA slaydda BITTA instrument (image | chart | infographic | "
        "scheme | kpi) — ikkitasi bir varaqqa sig'maydi va bir-birini yopadi\n"
        "• Ketma-ket slaydlarda tuzilma takrorlanmasin; dastlabki 5 slayd "
        "bir-biridan butunlay boshqacha bo'lsin\n"
        "• Tizim, tuzilma yoki jarayon haqidagi slaydda `scheme` elementidan "
        "foydalan — u kartochka to'ridan butunlay boshqacha ko'rinadi\n"
        "• O'sha yagona instrument slaydning kamida yarmini egallasin va matnda "
        "to'liq izohlansin — nima ko'rsatilgani va qanday xulosa chiqishi\n"
        "• Matn hajmi: instrumentli slaydda 90-130 so'z, instrumentsizda 160-240 so'z "
        "(o'lchangan chegara — ortig'i qutiga sig'maydi)\n"
        "• Rasm promptida matn so'ramang — harflar buzilib chiqadi\n"
        "  Diagramma qo'shsang — 'caption' maydoni MAJBURIY to'ldirsin\n"
        f"\n{level_instr}"
    )


def plan_presentation(topic: str, preferences: str = "", slide_count: int | None = None) -> dict:
    """AI foydalanuvchidan so'ramasdan taqdimot parametrlarini tanlaydi."""
    prompt = f"""Mavzu: {topic}
Foydalanuvchi istaklari: {preferences or "Ko'rsatma berilmagan; eng yaxshi professional variantni tanla."}

Taqdimot darajasini tanla:
1=maktab, 2=student/umumiy professional, 3=akademik/ekspert.
Mavzu murakkabligi, auditoriya va foydalanuvchi istaklariga qarab qaror qil.
Slaydlar soni foydalanuvchi tomonidan tanlangan va o'zgartirilmaydi: {slide_count or "belgilanmagan"}.
Faqat JSON qaytar: {{"level": 2, "reason": "qisqa sabab"}}"""
    result = _call_openrouter(
        "Sen taqdimot strategiyasi bo'yicha aqlli rejalashtiruvchisan. Faqat JSON qaytar.",
        prompt,
        temperature=0.35,
    )
    return result if isinstance(result, dict) else {"level": 2}


def _source_block(source: str) -> str:
    """Mijoz bergan materialni promptga qo'yadigan bo'lak.

    Material bo'lmasa bo'sh satr qaytadi va prompt avvalgidek qoladi.
    """
    text = (source or "").strip()
    if not text:
        return ""
    return (
        "\n\nMIJOZ BERGAN MATERIAL — taqdimot ANA SHUNGA tayanishi shart:\n"
        f"{text}\n"
        "• Slaydlardagi faktlar, raqamlar, nomlar va atamalar shu materialdan "
        "olinsin; materialda yo'q raqamni o'ylab topmang.\n"
        "• Materialga zid narsa yozilmasin.\n"
        "• Material mavzuning bir qismini qamrasa, qolganini o'z bilimingiz "
        "bilan to'ldiring, lekin materialdagi qismini o'zgartirmang.\n"
    )


def condense_source(text: str, topic: str) -> str:
    """Uzun materialni taqdimot uchun ishchi xulosaga aylantiradi."""
    prompt = (
        f"Quyidagi materialni \"{topic}\" mavzusidagi taqdimot uchun ishchi "
        "xulosaga aylantir.\n\n"
        "Yozuvchiga kerak bo'ladigan har bir narsani saqla: raqamlar, sanalar, "
        "nomlar, atamalar, tuzilma, xulosalar. Navigatsiya matni, reklama va "
        "takrorni tashla. 500-700 so'z, oddiy nasr, materialning o'z tilida.\n\n"
        f"MATERIAL:\n{text[:40_000]}"
    )
    return _call_openrouter_text(
        "Siz materialni hech narsa o'ylab topmasdan qisqartirasiz.",
        prompt, temperature=0.2, max_tokens=1800)


def generate_brief(topic: str, slide_count: int = 8, level: int = 2,
                   preferences: str = "", language: str = "uz",
                   source: str = "") -> dict:
    angle_name, angle_desc = random.choice(_NARRATIVE_ANGLES)

    user_prompt = (
        f"Mavzu: {topic}\n"
        f"Foydalanuvchi istaklari: {preferences or 'Erkin ijodiy qarorlarni o‘zing tanla.'}\n"
        f"{_source_block(source)}\n"
        f"TIL TALABI: {_language_instruction(language)}\n\n"
        f"NARRATIV YONDASHUV: «{angle_name}»\n"
        f"{angle_desc}\n\n"
        "Qoidalar:\n"
        + _base_rules(topic, slide_count, level)
    )
    return _call_openrouter(SYSTEM_PROMPT_BRIEF, user_prompt, temperature=0.72)


def generate_brief_chunk(
    topic: str,
    chunk_size: int,
    chunk_num: int,
    total_chunks: int,
    is_first: bool,
    is_last: bool,
    prev_summary: str | None,
    level: int = 2,
    preferences: str = "",
    language: str = "uz",
    source: str = "",
) -> dict:
    """Taqdimotning bir bo'lagini (chunk_size ta slayd) generatsiya qiladi."""
    if is_first:
        role_hint = (
            "Bu BIRINChI bo'lak.\n"
            "Birinchi slayd: role='hook' (MAJBURIY).\n"
            "Keyin: context, breakdown va detail slaydlari."
        )
    elif is_last:
        role_hint = (
            f"Bu OXIRGI bo'lak ({chunk_num+1}/{total_chunks}).\n"
            "Oxirgi slayd: role='synthesis' (MAJBURIY).\n"
            "Application slaydlaridan keyin synthesis bilan yoping."
        )
    else:
        role_hint = (
            f"Bu {chunk_num+1}/{total_chunks}-bo'lak (o'rtadagi).\n"
            "breakdown, detail, comparison, application rollaridan foydalaning (tartibda).\n"
            "Birinchi yoki oxirgi bo'lak emas — hook va synthesis QILMANG."
        )

    prev_ctx = (
        f"\nOLDINGI BO'LAK XULOSASI (takrorlanmaslik uchun):\n{prev_summary}\n"
        if prev_summary else ""
    )

    user_prompt = (
        f"Mavzu: {topic}\n"
        f"Foydalanuvchi istaklari: {preferences or 'Erkin ijodiy qarorlarni o‘zing tanla.'}\n"
        f"{_source_block(source)}"
        f"TIL TALABI: {_language_instruction(language)}\n"
        f"Bo'lak: {chunk_num+1}/{total_chunks} | {chunk_size} ta slayd\n"
        f"{prev_ctx}\n"
        f"{role_hint}\n\n"
        "Qoidalar:\n"
        + _base_rules(topic, chunk_size, level) +
        "\n• Avvalgi bo'lak bilan takrorlanmaslik — yangi g'oyalar, yangi faktlar\n"
        "• Mantiqiy bog'lanish: avvalgi slaydlar mavzusini davom ettir"
    )
    return _call_openrouter(SYSTEM_PROMPT_BRIEF, user_prompt, temperature=0.72)


def get_chunk_summary(slides_raw: list) -> str:
    """Keyingi bo'lak uchun avvalgi bo'lak qisqacha xulosasini tuzadi."""
    parts = []
    for s in slides_raw:
        title = s.get("title", "")
        key = (s.get("key_text", "") or "")[:120]
        role = s.get("role", "")
        parts.append(f"[{role}] {title}: {key}")
    return "\n".join(parts)


# ─────────────────────────────────────── Kichik tuzatish so'rovlari
#
# Slaydda nuqson topilganda uni BUTUNICHA qayta yozdirish eng qimmat yo'l:
# butun kanvas JSON ketadi va butun kanvas JSON qaytadi — bitta slayd uchun
# ming-ming token. Quyidagi so'rovlar esa faqat bitta qarorni yoki bitta
# elementni so'raydi, qolganini kod bajaradi. Shuning uchun javob bir necha
# o'nlab token bo'ladi va slaydning yaxshi qismlari o'zgarmay qoladi.

SYSTEM_PROMPT_PATCH = (
    "Sen taqdimot slaydini tuzatishga yordam berasan. Faqat so'ralgan narsani "
    "ber — slaydni qayta yozma, ortiqcha izoh berma. Javob sof JSON bo'lsin."
)


def choose_instrument(topic: str, title: str, key_text: str, options: list,
                      language: str = "uz") -> dict:
    """Bir necha instrumentdan qaysi biri qolishini so'raydi.

    Slayd JSON'i yuborilmaydi: modelga qaror uchun sarlavha, mazmun va
    variantlar ro'yxati yetarli.
    """
    listed = "\n".join(f"- {item['kind']}: {item['what']}" for item in options)
    user_prompt = (
        f"Mavzu: {topic}\n"
        f"Slayd sarlavhasi: {title}\n"
        f"Slayd mazmuni: {key_text}\n\n"
        f"Bu slaydda bir nechta instrument bor:\n{listed}\n\n"
        "Bir varaqda faqat BITTASI qolishi kerak — ular bir-birini yopadi. "
        "Qaysi biri slayd g'oyasini yaxshiroq ochadi?\n"
        f"TIL TALABI: {_language_instruction(language)}\n"
        'Faqat JSON: {"keep": "chart", "note": "qoladigan instrumentni '
        'izohlovchi bitta jumla — nima ko\'rsatilgan va qanday xulosa chiqadi"}'
    )
    return _call_openrouter(SYSTEM_PROMPT_PATCH, user_prompt,
                            temperature=0.2, max_tokens=300)


def make_chart(topic: str, title: str, key_text: str, language: str = "uz") -> dict:
    """Slaydga qo'yiladigan bitta diagramma elementini so'raydi.

    Koordinata so'ralmaydi — uni kod hisoblaydi.
    """
    user_prompt = (
        f"Mavzu: {topic}\n"
        f"Slayd sarlavhasi: {title}\n"
        f"Slayd mazmuni: {key_text}\n\n"
        "Shu slayd mazmuniga mos BITTA diagramma ma'lumotini ber. Raqamlar "
        "mavzuga tegishli va mantiqiy bo'lsin, o'ylab topilgan bo'lmasin. "
        "Kategoriya 3-7 ta.\n"
        f"{timeframe.year_rule(language)}\n"
        f"TIL TALABI: {_language_instruction(language)}\n"
        'Faqat JSON: {"chart_type": "column|bar|line|area|pie|donut|radar", '
        '"chart_title": "...", "caption": "diagramma nimani ko\'rsatadi — '
        '1-2 jumla", "categories": ["..."], '
        '"series": [{"name": "...", "values": [1, 2, 3]}]}'
    )
    return _call_openrouter(SYSTEM_PROMPT_PATCH, user_prompt,
                            temperature=0.4, max_tokens=900)


def make_infographic(topic: str, title: str, key_text: str, icons: str,
                     language: str = "uz") -> dict:
    """Infografika bandlarini so'raydi — joylashuvni kod hisoblaydi."""
    user_prompt = (
        f"Mavzu: {topic}\n"
        f"Slayd sarlavhasi: {title}\n"
        f"Slayd mazmuni: {key_text}\n\n"
        "Shu slayd mazmunini 3-5 bandli infografikaga aylantir. Har bandda "
        "qisqa sarlavha (2-4 so'z), 1-2 jumla izoh (90 belgigacha) va "
        "ro'yxatdan ikonka nomi bo'lsin.\n"
        f"Ikonka nomlari: {icons}\n"
        f"TIL TALABI: {_language_instruction(language)}\n"
        'Faqat JSON: {"preset": "cards|steps|timeline|cycle|pyramid", '
        '"items": [{"title": "...", "text": "...", "icon": "...", '
        f'"value": "{timeframe.last_full_year()}"}}]}}'
    )
    return _call_openrouter(SYSTEM_PROMPT_PATCH, user_prompt,
                            temperature=0.4, max_tokens=900)


def regenerate_slide(
    topic: str, slide_json: dict, feedback: str, language: str = "uz"
) -> dict:
    user_prompt = (
        f"Mavzu: {topic}\n"
        f"Muammo: {feedback}\n"
        f"TIL TALABI: {_language_instruction(language)}\n"
        f"Eski slayd JSON:\n{json.dumps(slide_json, ensure_ascii=False)}\n\n"
        "Muammoni bartaraf etgan professional yangi slayd JSON qaytar. "
        "Agar ma'lumotlar taqqoslansa — diagramma qo'sh. "
        "Matn hajmini KAMAYTIRMA."
    )
    return _call_openrouter(SYSTEM_PROMPT_REGEN, user_prompt, temperature=0.6)
