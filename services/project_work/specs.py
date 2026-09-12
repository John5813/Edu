"""Qaysi soha loyiha ishi qanday bo'limlardan iboratligini aytadigan model.

Loyiha ishi sohadan sohaga o'zgaradi, lekin butunlay emas: deyarli hammasida
kirish, dolzarblik, ish jadvali, byudjet, risklar, kutilayotgan natijalar va
xulosa bor. Shu umumiy qism bu yerda bir marta yozilgan; har soha faqat
o'ziga xos o'rta bo'limlarini beradi.

Shuning uchun yangi soha qo'shish — bitta `FieldSpec`, yangi quruvchi kod emas.

`title` hujjatga chop etiladi, shuning uchun uch tilda. `guidance` esa faqat
AI ga beriladigan ko'rsatma — u hech qachon ko'rinmaydi, shuning uchun bitta
tilda yetarli; AI matnni mijoz tanlagan tilda yozadi.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Bo'lim ostiga qo'yiladigan artefakt turlari.
ARTIFACT_DATA = "data"          # mavzuga oid tahliliy jadval
ARTIFACT_TIMELINE = "timeline"  # bosqich | muddat | mas'ul | natija
ARTIFACT_BUDGET = "budget"      # modda | miqdor | narx | summa
ARTIFACT_RISKS = "risks"        # xavf | ehtimollik | ta'sir | chora
ARTIFACT_RESULTS = "results"    # ko'rsatkich | hozirgi | maqsad | o'lchov
ARTIFACT_SCHEME = "scheme"      # tuzilma sxemasi (kod bilan chiziladi)
ARTIFACT_FORECAST = "forecast"  # prognoz chizig'i + hisob formulasi
ARTIFACT_CALC = "calc"          # hisob-kitob jadvali + formulalar, chizmasiz
ARTIFACT_MARKETING = "marketing"  # sotuv prognozi + kanallar bo'yicha hisob
ARTIFACT_COSTS = "costs"        # chiqimlar tarkibi + tannarx hisobi
ARTIFACT_BREAKEVEN = "breakeven"  # zararsizlik nuqtasi
ARTIFACT_CASHFLOW = "cashflow"  # kirim-chiqim oqimi va to'planishi

# Bir xil ko'rinishdagi beshta jadval o'rniga har ma'lumot o'z shaklini
# oladi: xarajat — ustunli diagramma, bosqichlar — Gantt lentasi, risklar —
# pufakchali yoki radar diagramma, natijalar — ko'rsatkich kartochkalari,
# prognoz — chiziq, tuzilma — bloklar sxemasi.
CHART_ARTIFACTS = {
    ARTIFACT_BUDGET,
    ARTIFACT_TIMELINE,
    ARTIFACT_RISKS,
    ARTIFACT_FORECAST,
    ARTIFACT_MARKETING,
    ARTIFACT_COSTS,
    ARTIFACT_BREAKEVEN,
    ARTIFACT_CASHFLOW,
    # Sxema ham chizma: ilgari u AI rasmi edi va undagi yozuvlar buzilardi.
    ARTIFACT_SCHEME,
}
CARD_ARTIFACTS = {ARTIFACT_RESULTS}
# AI dan matn ko'rinishida jadval so'raladigan artefaktlar.
TABLE_ARTIFACTS = {ARTIFACT_DATA, ARTIFACT_CALC}

# Jadvali raqamli ma'lumotdan KOD bilan chiqariladigan artefaktlar.
#
# Ilgari byudjet uchun ikkita alohida so'rov bor edi: biri jadval uchun,
# biri diagramma uchun. Ikkisi bir-biriga bog'lanmagani uchun jadvaldagi
# summa bilan diagrammadagi ustun boshqa-boshqa chiqardi — va jadval
# so'rovi hech qachon chaqirilmagani uchun bu ko'rinmay qolgan edi.
#
# Endi bitta so'rov raqamlarni beradi, jadval ham diagramma ham o'sha
# raqamdan quriladi. Yig'indi va ulush kodda hisoblanadi: AI qo'shishda
# xato qilardi, ustoz esa avvalo yig'indini tekshiradi.
DERIVED_TABLE_ARTIFACTS = {
    ARTIFACT_BUDGET,
    ARTIFACT_TIMELINE,
    ARTIFACT_RISKS,
    ARTIFACT_MARKETING,
    ARTIFACT_COSTS,
    ARTIFACT_CASHFLOW,
    ARTIFACT_BREAKEVEN,
    ARTIFACT_FORECAST,
}

# Nechta formula so'ralishi. Hisob-kitob bo'limining mag'zi formulalar
# bo'lgani uchun u eng ko'p oladi; rejadagi bo'limlarga formula kerak emas.
FORMULA_COUNTS = {
    ARTIFACT_CALC: 3,
    ARTIFACT_COSTS: 2,
    ARTIFACT_BREAKEVEN: 3,
    ARTIFACT_MARKETING: 2,
    ARTIFACT_CASHFLOW: 2,
    ARTIFACT_FORECAST: 2,
    ARTIFACT_BUDGET: 1,
}


# ─────────────────────────────────────────── Mijoz tanlaydigan mazmun bloklari
#
# Ilgari TIMELINE, BUDGET, FORECAST, RISKS va RESULTS har bir loyiha ishiga
# majburan tushardi. Ammo sof hisob-kitobli ishga Gantt lentasi ham, risk
# matritsasi ham keraksiz. Endi bo'limlar mijoz tanlagan bloklardan yig'iladi.

BLOCK_CALC = "calc"
BLOCK_BUDGET = "budget"
BLOCK_COSTS = "costs"
BLOCK_TIMELINE = "timeline"
BLOCK_MARKETING = "marketing"
BLOCK_BREAKEVEN = "breakeven"
BLOCK_FORECAST = "forecast"
BLOCK_CASHFLOW = "cashflow"
BLOCK_RISKS = "risks"
BLOCK_RESULTS = "results"
BLOCK_AUTO = "auto"

# Hujjatdagi tartib — mijoz tanlash tartibi emas. Iqtisodiy mantiq bo'yicha:
# hisob-kitob → investitsiya → doimiy chiqim → reja → sotuv → zararsizlik →
# prognoz → pul oqimi → risklar → natija.
BLOCK_ORDER = [
    BLOCK_CALC, BLOCK_BUDGET, BLOCK_COSTS, BLOCK_TIMELINE,
    BLOCK_MARKETING, BLOCK_BREAKEVEN, BLOCK_FORECAST, BLOCK_CASHFLOW,
    BLOCK_RISKS, BLOCK_RESULTS,
]

# Iqtisodiy hisob-kitob bloklari — `auto` rejimida mavzuda pul, ishlab
# chiqarish yoki xizmat bo'lsa AI shulardan tanlaydi.
ECONOMIC_BLOCKS = [BLOCK_COSTS, BLOCK_MARKETING, BLOCK_BREAKEVEN, BLOCK_CASHFLOW]

BLOCK_LABELS: Dict[str, Dict[str, str]] = {
    BLOCK_CALC: {"uz": "Hisob-kitob va formulalar", "ru": "Расчёты и формулы",
                 "en": "Calculations and formulas"},
    BLOCK_BUDGET: {"uz": "Smeta va resurslar", "ru": "Смета и ресурсы",
                   "en": "Budget and resources"},
    BLOCK_TIMELINE: {"uz": "Ish jadvali (bosqichlar)", "ru": "План работ (этапы)",
                     "en": "Work plan (stages)"},
    BLOCK_FORECAST: {"uz": "Prognoz va samaradorlik", "ru": "Прогноз и эффективность",
                     "en": "Forecast and effectiveness"},
    BLOCK_RISKS: {"uz": "Risklar tahlili", "ru": "Анализ рисков",
                  "en": "Risk analysis"},
    BLOCK_RESULTS: {"uz": "Kutilayotgan natijalar", "ru": "Ожидаемые результаты",
                    "en": "Expected results"},
    BLOCK_COSTS: {"uz": "Chiqimlar tarkibi va tannarx",
                  "ru": "Структура расходов и себестоимость",
                  "en": "Cost structure and unit cost"},
    BLOCK_MARKETING: {"uz": "Marketing prognozi va sotuv rejasi",
                      "ru": "Маркетинговый прогноз и план продаж",
                      "en": "Marketing forecast and sales plan"},
    BLOCK_BREAKEVEN: {"uz": "Zararsizlik nuqtasi tahlili",
                      "ru": "Анализ точки безубыточности",
                      "en": "Break-even analysis"},
    BLOCK_CASHFLOW: {"uz": "Pul oqimi va qoplanish muddati",
                     "ru": "Денежный поток и срок окупаемости",
                     "en": "Cash flow and payback period"},
    BLOCK_AUTO: {"uz": "AI mavzuga qarab o'zi tanlasin",
                 "ru": "ИИ выберет сам по теме",
                 "en": "Let the AI choose by topic"},
}


def block_label(block: str, language: str) -> str:
    labels = BLOCK_LABELS.get(block, {})
    return labels.get(language, labels.get("uz", block))


@dataclass(frozen=True)
class SectionSpec:
    key: str
    title: Dict[str, str]
    guidance: str
    artifact: Optional[str] = None
    words: str = "300-380"

    def heading(self, language: str) -> str:
        return self.title.get(language, self.title["uz"])


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: Dict[str, str]
    middle: List[SectionSpec] = field(default_factory=list)

    def name(self, language: str) -> str:
        return self.label.get(language, self.label["uz"])


# ─────────────────────────────────────────── Hamma sohada uchraydigan bo'limlar

INTRO = SectionSpec(
    key="kirish",
    title={"uz": "Kirish", "ru": "Введение", "en": "Introduction"},
    guidance=(
        "State what the project is, why it is needed now, who benefits from it, "
        "and what the work covers. Do not list the sections that follow."
    ),
    words="220-280",
)

RELEVANCE = SectionSpec(
    key="dolzarblik",
    title={
        "uz": "Muammoning dolzarbligi va loyiha maqsadi",
        "ru": "Актуальность проблемы и цель проекта",
        "en": "Relevance of the problem and project goal",
    },
    guidance=(
        "Describe the concrete problem the project solves, with figures where "
        "possible, then state the goal and three to five measurable objectives."
    ),
)

TIMELINE = SectionSpec(
    key="ish_jadvali",
    title={
        "uz": "Loyihani amalga oshirish rejasi",
        "ru": "План реализации проекта",
        "en": "Implementation plan",
    },
    guidance=(
        "Break the work into sequential stages and explain what happens in each, "
        "how long it takes and who is responsible."
    ),
    artifact=ARTIFACT_TIMELINE,
)

BUDGET = SectionSpec(
    key="byudjet",
    title={
        "uz": "Loyiha byudjeti va resurslar",
        "ru": "Бюджет проекта и ресурсы",
        "en": "Project budget and resources",
    },
    guidance=(
        "Explain the one-off investment the project needs to start: equipment, "
        "premises, installation, licences, working capital. Say where the "
        "funding comes from and which items dominate. Use realistic Uzbek "
        "market prices in so'm. Do not go into the recurring monthly running "
        "costs here — those belong to the cost-structure section."
    ),
    artifact=ARTIFACT_BUDGET,
)

RISKS = SectionSpec(
    key="risklar",
    title={
        "uz": "Risklar va ularni boshqarish",
        "ru": "Риски и управление ими",
        "en": "Risks and their management",
    },
    guidance=(
        "Identify the real risks of this specific project — not generic ones — "
        "and give a concrete mitigation for each."
    ),
    artifact=ARTIFACT_RISKS,
)

RESULTS = SectionSpec(
    key="natijalar",
    title={
        "uz": "Kutilayotgan natijalar va samaradorlik",
        "ru": "Ожидаемые результаты и эффективность",
        "en": "Expected results and effectiveness",
    },
    guidance=(
        "State what changes once the project is done, expressed as measurable "
        "indicators with target values, and how the effect will be verified."
    ),
    artifact=ARTIFACT_RESULTS,
)

FORECAST = SectionSpec(
    key="prognoz",
    title={
        "uz": "Prognoz va samaradorlik hisobi",
        "ru": "Прогноз и расчёт эффективности",
        "en": "Forecast and effectiveness calculation",
    },
    guidance=(
        "Project how the key quantity develops over the next three to four "
        "periods and explain what drives it. State the calculation behind the "
        "effectiveness figure — payback, yield, capacity or whichever measure "
        "fits this field — and interpret the result."
    ),
    artifact=ARTIFACT_FORECAST,
)

CALCULATION = SectionSpec(
    key="hisob",
    title={
        "uz": "Hisob-kitob va uni asoslash",
        "ru": "Расчёты и их обоснование",
        "en": "Calculations and their justification",
    },
    guidance=(
        "Work through the numeric core of the project step by step: state the "
        "input quantities with their units, the formula applied at each step, "
        "and the figure it produces. Explain what each result means in practice. "
        "This section is about arithmetic, not about planning or risks."
    ),
    artifact=ARTIFACT_CALC,
)

COSTS = SectionSpec(
    key="chiqimlar",
    title={
        "uz": "Chiqimlar tarkibi va tannarx hisobi",
        "ru": "Структура расходов и расчёт себестоимости",
        "en": "Cost structure and unit cost calculation",
    },
    guidance=(
        "Analyse what the project spends money on once it is running — not the "
        "one-off investment, but the recurring cost of operating it. Separate "
        "the fixed costs from the variable ones and say which items dominate. "
        "Work out the cost of one unit of output and compare it with the price "
        "the market pays. Use realistic Uzbek figures in so'm."
    ),
    artifact=ARTIFACT_COSTS,
    words="340-420",
)

MARKETING = SectionSpec(
    key="marketing_prognoz",
    title={
        "uz": "Marketing prognozi va sotuv rejasi",
        "ru": "Маркетинговый прогноз и план продаж",
        "en": "Marketing forecast and sales plan",
    },
    guidance=(
        "Forecast how much the project will sell and earn over the coming "
        "periods, and say what that forecast rests on: the size of the "
        "audience, the promotion channels, the price. Go through the channels "
        "one by one — what each costs, how many people it reaches, how many of "
        "them become customers. State what one customer costs to acquire and "
        "whether that is justified by what the customer brings in."
    ),
    artifact=ARTIFACT_MARKETING,
    words="340-420",
)

BREAKEVEN = SectionSpec(
    key="zararsizlik",
    title={
        "uz": "Zararsizlik nuqtasi va moliyaviy barqarorlik",
        "ru": "Точка безубыточности и финансовая устойчивость",
        "en": "Break-even point and financial stability",
    },
    guidance=(
        "Work out the volume at which the project stops making a loss: the "
        "fixed costs it must cover, the margin each unit contributes, and the "
        "number of units or the revenue that follows from those two. Say how "
        "far the planned volume sits above that point, and what happens to the "
        "figure if the price falls or costs rise."
    ),
    artifact=ARTIFACT_BREAKEVEN,
    words="320-400",
)

CASHFLOW = SectionSpec(
    key="pul_oqimi",
    title={
        "uz": "Pul oqimi va investitsiyaning qoplanishi",
        "ru": "Денежный поток и окупаемость инвестиций",
        "en": "Cash flow and return on investment",
    },
    guidance=(
        "Follow the money period by period: what comes in, what goes out, what "
        "is left, and how the accumulated balance moves from negative to "
        "positive. Say in which period the project turns cash-positive and when "
        "the initial investment is recovered. Name the periods concretely "
        "(years or quarters)."
    ),
    artifact=ARTIFACT_CASHFLOW,
    words="320-400",
)

CONCLUSION = SectionSpec(
    key="xulosa",
    title={"uz": "Xulosa", "ru": "Заключение", "en": "Conclusion"},
    guidance=(
        "Summarise what the project achieves, what was established in the work, "
        "and give practical recommendations for putting it into practice."
    ),
    words="240-300",
)

STRUCTURE = SectionSpec(
    key="tuzilma",
    title={
        "uz": "Loyihaning tuzilmasi",
        "ru": "Структура проекта",
        "en": "Project structure",
    },
    guidance=(
        "Describe how the project is put together: its main parts, what each "
        "part is responsible for, and how they connect into one working whole. "
        "Name the parts concretely — this is the structure of this project, not "
        "a general description of the field."
    ),
    artifact=ARTIFACT_SCHEME,
    words="260-320",
)

_OPENING = [INTRO, RELEVANCE]

# Blok → bo'lim. CONCLUSION har doim oxirida turadi, u blok emas.
_BLOCK_SECTIONS: Dict[str, SectionSpec] = {
    BLOCK_CALC: CALCULATION,
    BLOCK_BUDGET: BUDGET,
    BLOCK_COSTS: COSTS,
    BLOCK_TIMELINE: TIMELINE,
    BLOCK_MARKETING: MARKETING,
    BLOCK_BREAKEVEN: BREAKEVEN,
    BLOCK_FORECAST: FORECAST,
    BLOCK_CASHFLOW: CASHFLOW,
    BLOCK_RISKS: RISKS,
    BLOCK_RESULTS: RESULTS,
}

# `auto` tanlanib, AI javob bera olmasa ishlatiladigan zaxira ro'yxat.
# Ichida bitta haqiqiy hisob-kitob bo'lishi shart: loyiha ishida raqamsiz
# byudjet jadvali yetarli emas.
DEFAULT_BLOCKS = [BLOCK_BUDGET, BLOCK_COSTS, BLOCK_TIMELINE,
                  BLOCK_RISKS, BLOCK_RESULTS]


def _section(key, uz, ru, en, guidance, artifact=None, words="300-380") -> SectionSpec:
    return SectionSpec(
        key=key,
        title={"uz": uz, "ru": ru, "en": en},
        guidance=guidance,
        artifact=artifact,
        words=words,
    )


# ─────────────────────────────────────────── Sohalar

FIELDS: Dict[str, FieldSpec] = {
    "business": FieldSpec(
        key="business",
        label={"uz": "Iqtisodiyot va biznes", "ru": "Экономика и бизнес", "en": "Economics and business"},
        middle=[
            _section(
                "bozor", "Bozor tahlili va raqobat muhiti",
                "Анализ рынка и конкурентной среды", "Market and competitive analysis",
                "Analyse market size, demand, customer segments and the main "
                "competitors, with figures.",
                artifact=ARTIFACT_DATA,
            ),
            _section(
                "goya", "Loyiha g'oyasi va biznes modeli",
                "Идея проекта и бизнес-модель", "Project idea and business model",
                "Describe the product or service, how it earns money, and what "
                "makes it different from what already exists.",
            ),
            _section(
                "marketing", "Marketing strategiyasi va narx siyosati",
                "Маркетинговая стратегия и ценовая политика",
                "Marketing strategy and pricing policy",
                "Explain the positioning, the pricing policy and the reasoning "
                "behind it, the sales process and how customers are retained. "
                "Keep this qualitative — the channel figures and the sales "
                "forecast belong to the marketing forecast section.",
            ),
        ],
    ),
    "engineering": FieldSpec(
        key="engineering",
        label={"uz": "Texnika, muhandislik, qurilish", "ru": "Техника, инженерия, строительство", "en": "Engineering and construction"},
        middle=[
            _section(
                "topshiriq", "Texnik topshiriq va talablar",
                "Техническое задание и требования", "Technical assignment and requirements",
                "State the technical requirements, operating conditions, "
                "applicable standards and acceptance criteria.",
            ),
            _section(
                "tahlil", "Mavjud yechimlar tahlili",
                "Анализ существующих решений", "Analysis of existing solutions",
                "Compare the existing technical solutions and justify the one "
                "chosen for this project.",
                artifact=ARTIFACT_DATA,
            ),
            _section(
                "hisob", "Loyihalash va muhandislik hisob-kitoblari",
                "Проектирование и инженерные расчёты", "Design and engineering calculations",
                "Present the design decisions and the calculations behind them: "
                "loads, capacity, dimensions, materials. Show the reasoning.",
                artifact=ARTIFACT_CALC,
                words="380-450",
            ),
            _section(
                "xavfsizlik", "Xavfsizlik va ekologik talablar",
                "Требования безопасности и экологии", "Safety and environmental requirements",
                "Cover occupational safety, fire safety and environmental "
                "requirements specific to this project.",
                words="240-300",
            ),
        ],
    ),
    "it": FieldSpec(
        key="it",
        label={"uz": "IT va dasturiy ta'minot", "ru": "IT и программное обеспечение", "en": "IT and software"},
        middle=[
            _section(
                "talablar", "Muammo va talablar tahlili",
                "Анализ проблемы и требований", "Problem and requirements analysis",
                "Describe the users, their tasks, and the functional and "
                "non-functional requirements that follow.",
            ),
            _section(
                "arxitektura", "Tizim arxitekturasi",
                "Архитектура системы", "System architecture",
                "Describe the components, how they interact, the technology "
                "stack and why it was chosen.",
                artifact=ARTIFACT_SCHEME,
            ),
            _section(
                "malumotlar", "Ma'lumotlar bazasi va foydalanuvchi interfeysi",
                "База данных и пользовательский интерфейс", "Database and user interface",
                "Describe the main data entities and their relations, and the "
                "key screens of the interface.",
                artifact=ARTIFACT_DATA,
            ),
            _section(
                "testlash", "Testlash va sifat nazorati",
                "Тестирование и контроль качества", "Testing and quality control",
                "Explain how the system is tested, which cases matter most, and "
                "what counts as ready for release.",
                words="240-300",
            ),
        ],
    ),
    "education": FieldSpec(
        key="education",
        label={"uz": "Pedagogika va ta'lim", "ru": "Педагогика и образование", "en": "Pedagogy and education"},
        middle=[
            _section(
                "guruh", "Maqsadli guruh va ehtiyojlar tahlili",
                "Целевая группа и анализ потребностей", "Target group and needs analysis",
                "Describe who the project is for, how many people, and what "
                "their measured needs are.",
                artifact=ARTIFACT_DATA,
            ),
            _section(
                "metodika", "Pedagogik metodika va yondashuv",
                "Педагогическая методика и подход", "Teaching methodology and approach",
                "Explain the teaching methods used and why they suit this "
                "target group, referring to established pedagogy.",
            ),
            _section(
                "tadbirlar", "Tadbirlar mazmuni",
                "Содержание мероприятий", "Content of the activities",
                "Describe the concrete sessions, materials and activities that "
                "make up the project.",
            ),
        ],
    ),
    "social": FieldSpec(
        key="social",
        label={"uz": "Ijtimoiy va gumanitar soha", "ru": "Социальная и гуманитарная сфера", "en": "Social and humanitarian"},
        middle=[
            _section(
                "manfaatdorlar", "Manfaatdor tomonlar va maqsadli guruh",
                "Заинтересованные стороны и целевая группа", "Stakeholders and target group",
                "Identify who is affected, who decides, who funds, and what "
                "each party gains.",
                artifact=ARTIFACT_DATA,
            ),
            _section(
                "yechim", "Taklif etilayotgan yechim",
                "Предлагаемое решение", "Proposed solution",
                "Describe the intervention itself and the evidence that this "
                "kind of intervention works.",
            ),
            _section(
                "barqarorlik", "Loyihaning barqarorligi",
                "Устойчивость проекта", "Sustainability of the project",
                "Explain how the results are sustained after the funding period "
                "ends, and who continues the work.",
                words="240-300",
            ),
        ],
    ),
    "medicine": FieldSpec(
        key="medicine",
        label={"uz": "Tibbiyot va biologiya", "ru": "Медицина и биология", "en": "Medicine and biology"},
        middle=[
            _section(
                "muammo", "Muammoning tibbiy-biologik asoslari",
                "Медико-биологические основы проблемы", "Medical and biological background",
                "Present the clinical or biological background with prevalence "
                "figures and current practice.",
            ),
            _section(
                "metod", "Tadqiqot va amaliyot metodikasi",
                "Методика исследования и практики", "Research and practice methodology",
                "Describe the methods, sample, measurements and how data is "
                "collected and analysed.",
                artifact=ARTIFACT_DATA,
            ),
            _section(
                "profilaktika", "Profilaktika va tavsiyalar",
                "Профилактика и рекомендации", "Prevention and recommendations",
                "Give the preventive measures and practical recommendations "
                "that follow from the work.",
            ),
        ],
    ),
    "agriculture": FieldSpec(
        key="agriculture",
        label={"uz": "Qishloq xo'jaligi", "ru": "Сельское хозяйство", "en": "Agriculture"},
        middle=[
            _section(
                "sharoit", "Tabiiy-iqlim sharoiti va resurslar",
                "Природно-климатические условия и ресурсы", "Climate conditions and resources",
                "Describe the land, soil, water and climate conditions the "
                "project works with, using regional figures.",
                artifact=ARTIFACT_DATA,
            ),
            _section(
                "texnologiya", "Agrotexnologiya va ishlab chiqarish jarayoni",
                "Агротехнология и процесс производства", "Agrotechnology and production process",
                "Describe the growing or production technology step by step, "
                "including inputs, equipment and seasonal timing.",
                words="380-450",
            ),
            _section(
                "hosildorlik", "Hosildorlik va sifat ko'rsatkichlari",
                "Показатели урожайности и качества", "Yield and quality indicators",
                "Give expected yield and quality figures and compare them with "
                "regional averages, and work out the yield per hectare and the "
                "output the project's area produces.",
                artifact=ARTIFACT_CALC,
            ),
        ],
    ),
}

# Mijoz sohasini ro'yxatdan topa olmasa — bo'limlarni AI o'zi taklif qiladi.
GENERIC_FIELD_KEY = "generic"
GENERIC_LABEL = {
    "uz": "Boshqa soha (AI o'zi tuzadi)",
    "ru": "Другая сфера (AI составит сам)",
    "en": "Other field (AI will design it)",
}


def closing_for(blocks, middle: Optional[List[SectionSpec]] = None) -> List[SectionSpec]:
    """Mijoz tanlagan bloklardan yakuniy bo'limlarni yig'adi.

    Sohaning o'z bo'limlarida allaqachon hisob-kitob bo'lsa (muhandislikdagi
    loyihalash hisobi, qishloq xo'jaligidagi hosildorlik), umumiy hisob
    bloki qo'shilmaydi — aks holda hujjatda ikkita bir xil vazifadagi
    bo'lim va ikkita hisob jadvali paydo bo'lardi.
    """
    chosen = set(blocks or [])
    if any(section.artifact == ARTIFACT_CALC for section in (middle or [])):
        chosen.discard(BLOCK_CALC)
    ordered = [_BLOCK_SECTIONS[key] for key in BLOCK_ORDER if key in chosen]
    return [*ordered, CONCLUSION]


def _with_structure(middle: List[SectionSpec]) -> List[SectionSpec]:
    """Har bir ishga tuzilma sxemasini qo'shadi.

    Sxema o'rta bo'limlarning boshida turadi: o'quvchi avval loyihaning
    tuzilishini ko'radi, keyin tafsilotlarni o'qiydi. Soha bo'limlarida
    allaqachon sxema bo'lsa (masalan IT'dagi arxitektura), takrorlanmaydi.
    """
    if any(section.artifact == ARTIFACT_SCHEME for section in middle):
        return list(middle)
    return [STRUCTURE, *middle]


def sections_for(field_key: str, blocks=None) -> List[SectionSpec]:
    """Sohaning to'liq bo'limlar ketma-ketligi."""
    spec = FIELDS.get(field_key)
    if spec is None:
        raise KeyError(f"noma'lum soha: {field_key}")
    return [*_OPENING, *_with_structure(spec.middle),
            *closing_for(blocks, spec.middle)]


def generic_sections(middle: List[SectionSpec], blocks=None) -> List[SectionSpec]:
    """AI taklif qilgan o'rta bo'limlarni umumiy skeletga joylaydi."""
    return [*_OPENING, *_with_structure(middle), *closing_for(blocks, middle)]


def field_label(field_key: str, language: str) -> str:
    if field_key == GENERIC_FIELD_KEY:
        return GENERIC_LABEL.get(language, GENERIC_LABEL["uz"])
    return FIELDS[field_key].name(language)
