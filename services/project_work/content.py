"""Loyiha ishi mazmunini spetsifikatsiya bo'yicha AI dan olish.

Har bo'lim uchun matn, artefakt talab qilgan bo'limlar uchun jadval yoki
sxema, va oxirida adabiyotlar ro'yxati olinadi.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field as dataclass_field, replace
from typing import Dict, List, Optional

from utils.ai_text import token_budget, trim_to_last_sentence
from utils.heading_guard import heading_rule, strip_echoed_heading

from .source import SourceMaterial
from . import tables
from .specs import (
    ARTIFACT_BREAKEVEN,
    ARTIFACT_BUDGET,
    ARTIFACT_CALC,
    ARTIFACT_CASHFLOW,
    ARTIFACT_COSTS,
    ARTIFACT_FORECAST,
    ARTIFACT_DATA,
    ARTIFACT_MARKETING,
    ARTIFACT_RESULTS,
    ARTIFACT_RISKS,
    ARTIFACT_SCHEME,
    ARTIFACT_TIMELINE,
    BLOCK_AUTO,
    BLOCK_ORDER,
    CHART_ARTIFACTS,
    DEFAULT_BLOCKS,
    DERIVED_TABLE_ARTIFACTS,
    CARD_ARTIFACTS,
    FORMULA_COUNTS,
    TABLE_ARTIFACTS,
    GENERIC_FIELD_KEY,
    SectionSpec,
    generic_sections,
    sections_for,
)

logger = logging.getLogger(__name__)

# Bir vaqtda nechta bo'lim yozilsin — ketma-ket juda sekin, cheksiz parallel
# esa provayder limitiga uriladi.
_CONCURRENCY = 3

# Bundan qisqa manba promptga o'z holicha ketadi; uzuni bir marta siqiladi.
_SOURCE_INLINE_LIMIT = 4_000
_SOURCE_CONDENSE_LIMIT = 40_000

_LANGUAGE_NAMES = {"uz": "Uzbek", "ru": "Russian", "en": "English"}

# Modelning o'zi yozadigan jadvallar. Bularning mazmuni matn: ustunlar ham
# mavzuga qarab o'zgaradi, shuning uchun ularni kod bilan qurib bo'lmaydi.
#
# Byudjet, bosqichlar, risklar, marketing, chiqim va pul oqimi jadvallari bu
# yerda YO'Q: ular diagramma ma'lumotidan `tables.py` da quriladi, ya'ni
# jadvaldagi raqam bilan diagrammadagi raqam bir xil bo'ladi.
_TABLE_KINDS = {
    ARTIFACT_CALC: {
        "columns": {
            "uz": ["Ko'rsatkich", "Hisoblash usuli", "Natija", "O'lchov birligi"],
            "ru": ["Показатель", "Способ расчёта", "Результат", "Единица измерения"],
            "en": ["Indicator", "Calculation", "Result", "Unit"],
        },
        "ask": (
            "the step-by-step numeric calculation this project rests on. Each row is "
            "one computed quantity: what it is, how it is obtained from the previous "
            "figures, the resulting number, and its unit. The rows must follow on from "
            "one another and the arithmetic must be correct"
        ),
        "rows": 6,
    },
    ARTIFACT_DATA: {
        "columns": None,  # ustunlarni AI mavzuga qarab o'zi tanlaydi
        "ask": "the most useful analytical table for this particular section",
        "rows": 6,
    },
}

# Diagramma quriladigan artefaktlar. Jadvaldan farqi: bu yerda AI dan matn
# emas, SON so'raladi — chizish uchun raqam kerak.
_CHART_SHAPES = {
    ARTIFACT_BUDGET: (
        'the one-off investment items the project needs to start, with realistic '
        'Uzbekistan market prices. For each item give "quantity" (how many), '
        '"unit" (what is counted: dona, komplekt, m2, xizmat) and "unit_price" '
        'in so\'m. Quantity and unit price are plain numbers; the line total and '
        'the grand total are computed from them, so do NOT give a total row. '
        'Give 5-7 items, largest first.',
        '{"items": [{"name": "Ishlab chiqarish uskunasi", "quantity": 3, '
        '"unit": "dona", "unit_price": 16000000}]}',
    ),
    ARTIFACT_TIMELINE: (
        'the sequential stages of the project. "start" is the month the stage '
        'begins counted from zero, "duration" is its length in months; both are '
        'plain numbers. "owner" is who is responsible and "result" is the '
        'concrete deliverable that stage ends with. Stages follow one another '
        'without gaps. Give 5-7 stages.',
        '{"stages": [{"name": "Tayyorgarlik va loyihalash", "start": 0, '
        '"duration": 2, "owner": "Loyiha rahbari", "result": "Tasdiqlangan '
        'texnik topshiriq"}]}',
    ),
    ARTIFACT_RISKS: (
        'the risks specific to this project, not generic ones. "likelihood" and '
        '"impact" must each be exactly one of: past, o\'rta, yuqori. Give 5-6 risks.',
        '{"risks": [{"name": "Uskuna yetkazib berish kechikishi", "likelihood": "o\'rta", "impact": "yuqori", "mitigation": "Ikkinchi yetkazib beruvchi bilan shartnoma"}]}',
    ),
    ARTIFACT_RESULTS: (
        'the measurable indicators of the project\'s success. "current" and '
        '"target" are plain numbers, "unit" is their unit of measure. Give 4-5 '
        'indicators whose target is clearly better than the current value.',
        '{"indicators": [{"name": "Ishlab chiqarish hajmi", "current": 1200, "target": 3400, "unit": "tonna/yil"}]}',
    ),
    ARTIFACT_FORECAST: (
        'a forecast of the project\'s key quantity over four periods, starting '
        'from the current year. "value" is the expected figure, "low" and "high" '
        'the confidence range; all plain numbers in the same unit. The first '
        'period is today\'s actual figure, so its low and high equal its value.',
        '{"unit": "mln so\'m", "points": [{"period": "2025", "value": 1200, "low": 1200, "high": 1200}]}',
    ),
    ARTIFACT_MARKETING: (
        'the sales forecast and the promotion channels behind it. "periods" are '
        '4-6 consecutive selling periods (quarters or years) with "units" — how '
        'much is sold — and "revenue" — what it brings in, expressed in '
        '"money_unit". "channels" are 4-5 real promotion channels with the '
        '"budget" spent on each in so\'m, the "reach" in people, the '
        '"conversion" share as text, and the resulting number of "customers". '
        'The cost per customer is computed from budget and customers, so do not '
        'give it. Every figure is a plain number and the channel figures must be '
        'consistent with the sales forecast.',
        '{"unit": "dona", "money_unit": "mln so\'m", '
        '"periods": [{"period": "2026 I chorak", "units": 1200, "revenue": 96}], '
        '"channels": [{"name": "Instagram maqsadli reklama", "budget": 12000000, '
        '"reach": 150000, "conversion": "1,2%", "customers": 1800}]}',
    ),
    ARTIFACT_COSTS: (
        'the recurring cost of running the project for one year — not the '
        'one-off investment. Each item has "kind", which is exactly one of '
        'doimiy (a cost that does not change with output) or o\'zgaruvchi (one '
        'that does), and "amount", the annual figure in so\'m as a plain '
        'number. The share of each item is computed, so do not give it. '
        '"output" is what the project produces in that same year, with its own '
        'unit, so that the cost of one unit can be worked out. Give 5-7 items, '
        'largest first.',
        '{"output": {"name": "Yillik ishlab chiqarish", "value": 12000, '
        '"unit": "tonna"}, "items": [{"name": "Xom ashyo va materiallar", '
        '"kind": "o\'zgaruvchi", "amount": 240000000}]}',
    ),
    ARTIFACT_BREAKEVEN: (
        'the figures the break-even point is worked out from. "fixed" is the '
        'annual fixed cost, "price" the selling price of one unit and "variable" '
        'the variable cost of one unit — all three in the same "money_unit". '
        '"planned" is the volume the project plans to sell, in "unit". The price '
        'must be greater than the variable cost, otherwise the project can never '
        'break even. All four are plain numbers.',
        '{"unit": "dona", "money_unit": "mln so\'m", "fixed": 420, '
        '"price": 0.085, "variable": 0.052, "planned": 9000}',
    ),
    ARTIFACT_CASHFLOW: (
        'the project\'s cash flow over 4-6 consecutive periods (years or '
        'quarters), all figures in the same "money_unit" as plain numbers. '
        '"income" is what comes in that period and "expense" what goes out; the '
        'first period includes the initial investment, so its expense is much '
        'larger and the flow starts negative. "investment" is that initial '
        'outlay. The net and the accumulated flow are computed, so do not give '
        'them, but the figures must be such that the accumulated flow turns '
        'positive somewhere in the middle of the range.',
        '{"money_unit": "mln so\'m", "investment": 420, '
        '"periods": [{"period": "2026", "income": 180, "expense": 560}]}',
    ),
}


# Qaysi bo'limda qanday hisob kutiladi. Aniq nomlar berilgan, chunki
# "samaradorlikni hisobla" degan ko'rsatma har bo'limda bir xil ROI ni
# qaytarardi — mijoz esa bir hujjatda uchta bir xil formulani ko'rardi.
_FORMULA_ASKS = {
    ARTIFACT_CALC: (
        "the numeric core of the project, step by step. Each calculation feeds "
        "the next one: a quantity, then what is derived from it, then the "
        "result that the project's decision rests on. These are the field's own "
        "engineering or economic formulas, not general financial ratios."
    ),
    ARTIFACT_COSTS: (
        "first the cost of one unit of output (total annual cost divided by "
        "annual output), then the share of variable costs in the total and what "
        "that share says about how the cost behaves when output changes."
    ),
    ARTIFACT_MARKETING: (
        "first the cost of acquiring one customer (marketing budget divided by "
        "the customers it brings), then the return on the marketing spend "
        "(revenue it generates against the budget spent)."
    ),
    ARTIFACT_BREAKEVEN: (
        "first the break-even volume in units — fixed costs divided by the "
        "margin one unit contributes — then the break-even revenue, then the "
        "safety margin: how far the planned volume sits above the break-even "
        "volume, as a percentage."
    ),
    ARTIFACT_CASHFLOW: (
        "first the payback period of the initial investment from the "
        "accumulated cash flow, then the profitability of the investment over "
        "the whole period."
    ),
    ARTIFACT_FORECAST: (
        "first the growth rate the forecast implies between the first and the "
        "last period, then the measure of effectiveness that fits this field."
    ),
    ARTIFACT_BUDGET: (
        "the investment per unit of the capacity the money buys — what one unit "
        "of output capacity costs to create."
    ),
    "default": (
        "the measure of effectiveness that fits this field, worked through."
    ),
}


@dataclass
class SectionContent:
    spec: SectionSpec
    text: str
    table: Optional[Dict] = None       # {"headers": [...], "rows": [[...]]}
    chart: Optional[Dict] = None       # diagramma yoki kartochka uchun raqamli ma'lumot
    image_prompt: str = ""
    # Bir bo'limda bir nechta hisob bo'lishi mumkin: tannarx ham, rentabellik
    # ham, qoplanish muddati ham. Ilgari bittasi chiqardi.
    formulas: List[Dict] = dataclass_field(default_factory=list)
    # Diagramma ostidagi izoh. Ustoz "bu nimani ko'rsatadi" deb so'raganda
    # javob hujjatning o'zida turishi kerak.
    note: str = ""


# Hujjatga qo'yiladigan haqiqiy suratlar soni. Sxemalar va diagrammalar
# ma'lumotni ko'rsatadi, surat esa ishga jonli tus beradi — ikkitasi
# hujjatni bosib ketmaydi.
PHOTOGRAPHS_PER_WORK = 2


def _place_photographs(sections: list, topic: str) -> list:
    """Ikkita bo'limga realistik surat prompti biriktiradi.

    Infografika yoki sxema emas, aynan surat: mijoz hujjatda jonli tasvir
    ko'rishni kutadi. Diagramma yoki jadvali bor bo'limlar chetlab
    o'tiladi — ular allaqachon vizual to'la.
    """
    free = [
        index for index, section in enumerate(sections)
        if not section.chart and not section.table
        and section.spec.key not in {"kirish", "xulosa"}
        and not section.image_prompt
    ]
    if not free:
        return sections

    # Hujjat bo'ylab tekis taqsimlaymiz: boshida va o'rtasida.
    chosen = []
    if free:
        chosen.append(free[0])
    if len(free) > 1:
        chosen.append(free[len(free) // 2] if free[len(free) // 2] != free[0] else free[-1])

    for index in chosen[:PHOTOGRAPHS_PER_WORK]:
        section = sections[index]
        section.image_prompt = (
            f"professional documentary photograph illustrating "
            f"{section.spec.heading('en').lower()} in the context of {topic}. "
            "Real people and real equipment in a real workplace, natural "
            "lighting, sharp focus, photorealistic, editorial quality. "
            "No text, no letters, no diagrams, no illustration style."
        )
    return sections


@dataclass
class ProjectContent:
    topic: str
    field_key: str
    language: str
    author_name: str = ""
    # Chizma shakli va rang sxemasi shu mijozning oldingi ishlariga qarab
    # tanlanadi, shuning uchun kim buyurtma bergani ma'lum bo'lishi kerak.
    user_id: Optional[int] = None
    sections: List[SectionContent] = dataclass_field(default_factory=list)
    references: List[str] = dataclass_field(default_factory=list)


class ProjectContentBuilder:
    def __init__(self, ai_service):
        self.ai = ai_service

    async def build(
        self,
        topic: str,
        field_key: str,
        language: str,
        depth: float = 1.0,
        source: Optional["SourceMaterial"] = None,
        progress_cb=None,
        blocks=None,
        user_id: Optional[int] = None,
    ) -> ProjectContent:
        brief = await self._source_brief(source, topic)
        blocks = await self.resolve_blocks(topic, field_key, blocks, brief)
        specs = [
            self._scaled(spec, depth)
            for spec in await self._resolve_sections(topic, field_key, language, brief, blocks)
        ]

        semaphore = asyncio.Semaphore(_CONCURRENCY)
        done = 0

        async def one(spec: SectionSpec) -> SectionContent:
            nonlocal done
            async with semaphore:
                section = await self._section(topic, spec, language, brief, field_key)
            done += 1
            if progress_cb:
                progress_cb(done, len(specs))
            return section

        sections = await asyncio.gather(*(one(spec) for spec in specs))
        sections = _place_photographs(list(sections), topic)
        references = await self._references(topic, language)
        return ProjectContent(
            topic=topic,
            field_key=field_key,
            language=language,
            sections=list(sections),
            references=references,
            user_id=user_id,
        )

    @staticmethod
    def _scaled(spec: SectionSpec, depth: float) -> SectionSpec:
        """Bo'lim hajmini mijoz tanlagan darajaga moslaydi."""
        if depth == 1.0:
            return spec
        try:
            low, high = (int(part) for part in spec.words.split("-"))
        except ValueError:
            return spec
        return replace(spec, words=f"{round(low * depth)}-{round(high * depth)}")

    # ---------------------------------------------------------------- manba

    async def _source_brief(self, source: Optional[SourceMaterial], topic: str) -> str:
        """Manbani bir marta siqib, har bo'lim promptiga qo'shiladigan holga keltiradi.

        Qo'llanma yoki sayt 60 000 belgi bo'lishi mumkin; uni o'nta bo'lim
        promptining har biriga qo'yish qimmat ham, foydasiz ham. Qisqa manba
        o'z holicha ketadi, uzuni bir marta xulosalanadi.
        """
        if source is None or not source.has_content:
            return ""

        text = source.text.strip()
        if len(text) <= _SOURCE_INLINE_LIMIT:
            return text

        prompt = f"""Condense this material into a working brief for writing a project
work on "{topic}".

Keep every fact that a writer would need: figures, names, dates, requirements,
methods, standards, structure. Drop navigation text, adverts and repetition.
Write 500-700 words of plain prose in the material's own language.

MATERIAL:
{text[:_SOURCE_CONDENSE_LIMIT]}"""

        try:
            condensed = await self.ai._make_request(
                messages=[
                    {"role": "system", "content": "You condense source material without inventing anything."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1800,
                temperature=0.2,
            )
            return condensed.strip()
        except Exception as e:
            logger.error("Manbani siqishda xato, boshi ishlatiladi: %s", e)
            return text[:_SOURCE_INLINE_LIMIT]

    @staticmethod
    def _source_block(brief: str) -> str:
        if not brief:
            return ""
        return (
            "\n\nSOURCE MATERIAL the client supplied — build the text on it, stay "
            "consistent with its facts and terminology, and do not contradict it:\n"
            f"{brief}"
        )

    # ------------------------------------------------------------- bo'limlar

    async def _resolve_sections(
        self, topic: str, field_key: str, language: str, brief: str = "", blocks=None
    ) -> List[SectionSpec]:
        if field_key != GENERIC_FIELD_KEY:
            return sections_for(field_key, blocks)
        middle = await self.propose_middle_sections(topic, language, brief)
        return generic_sections(middle, blocks)

    async def resolve_blocks(self, topic: str, field_key: str, blocks, brief: str = "") -> List[str]:
        """Mijoz tanlovini yakuniy blok ro'yxatiga aylantiradi.

        `auto` tanlansa mavzuga qarab AI hal qiladi: sof hisob-kitobli ishga
        Gantt lentasi ham, risklar diagrammasi ham keraksiz, va aksincha.
        Tuzilma sxemasi bu ro'yxatga kirmaydi — u har bir ishda bo'ladi.
        """
        chosen = [b for b in (blocks or []) if b in BLOCK_ORDER]
        if BLOCK_AUTO not in (blocks or []):
            return chosen

        try:
            proposed = await self._propose_blocks(topic, field_key, brief)
        except Exception as e:
            logger.error("Bloklarni AI tanlay olmadi: %s", e)
            proposed = []
        merged = [b for b in BLOCK_ORDER if b in proposed or b in chosen]
        return merged or list(DEFAULT_BLOCKS)

    async def suggest_field(self, topic: str) -> str:
        """Mavzudan yo'nalishni taxmin qiladi.

        Mijoz sakkizta tugmadan o'zi qidirgandan ko'ra, bot taklif qilib
        tasdiqlatgani tezroq va kamroq xato beradi.
        """
        from .specs import FIELDS

        catalogue = "\n".join(
            f"{key} — {spec.name('en')}" for key, spec in FIELDS.items()
        )
        prompt = f"""Which field of study does this project work topic belong to?

Topic: "{topic}"

Fields:
{catalogue}
other — none of the above fits

Respond with JSON only: {{"field": "business"}}"""
        try:
            raw = await self._json_request(prompt, max_tokens=60, temperature=0.0)
            key = str(raw.get("field") or "").strip().lower()
            if key in FIELDS:
                return key
        except Exception as e:
            logger.error("Yo'nalishni aniqlab bo'lmadi: %s", e)
        return GENERIC_FIELD_KEY

    async def _propose_blocks(self, topic: str, field_key: str, brief: str = "") -> List[str]:
        prompt = f"""A student is writing a project work ("loyiha ishi") on: "{topic}".
Field of study: {field_key}

Decide which of these content blocks this particular work genuinely needs.

calc      — the field's own step-by-step calculations and formulas
budget    — the one-off investment: what it buys, at what price
costs     — the recurring annual cost of running it, split into fixed and
            variable, and the cost of one unit of output
timeline  — implementation stages with durations and responsibilities
marketing — sales forecast by period plus the promotion channels, their
            budgets and the customers each brings
breakeven — the volume at which the project stops making a loss
forecast  — projection of a key quantity over several periods
cashflow  — money in and out period by period, and when the investment is
            recovered
risks     — risk analysis with mitigations
results   — measurable expected results

Rules for choosing:
- A project that sells something, produces something, or serves paying
  clients needs the money blocks: costs, marketing, breakeven and cashflow
  are what a supervisor asks about first. Include at least two of them.
- A project with no revenue side — a purely technical, medical, pedagogical
  or research project — still spends money, so budget and costs belong, but
  marketing and breakeven do not.
- A purely computational work needs no Gantt chart or risk matrix; a purely
  organisational one needs no formulas.

Choose between four and seven blocks.{self._source_block(brief)}

Respond with JSON only: {{"blocks": ["budget", "costs", "marketing", "breakeven"]}}"""
        raw = await self._json_request(prompt, max_tokens=260, temperature=0.2)
        proposed = [str(b).strip().lower() for b in (raw.get("blocks") or [])]
        return [b for b in proposed if b in BLOCK_ORDER]

    async def propose_middle_sections(
        self, topic: str, language: str, brief: str = ""
    ) -> List[SectionSpec]:
        """Ro'yxatda yo'q soha uchun o'rta bo'limlarni AI taklif qiladi."""
        target = _LANGUAGE_NAMES.get(language, "Uzbek")
        prompt = f"""A student is writing a project work ("loyiha ishi") on: "{topic}".

The document already has these sections and you must NOT repeat them:
introduction, relevance and goal, implementation plan, budget, risks,
expected results, conclusion.

Propose the 3-4 middle sections that belong between "relevance" and
"implementation plan" for this specific topic and its field of study.
Write the titles in {target}. Each needs a one-sentence instruction, in
English, saying what its text must contain.{self._source_block(brief)}

Respond with JSON only:
{{"sections": [{{"title": "...", "guidance": "..."}}]}}"""

        raw = await self._json_request(prompt, max_tokens=1200, temperature=0.5)
        proposed = []
        for item in (raw.get("sections") or [])[:4]:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            proposed.append(
                SectionSpec(
                    key=f"custom_{len(proposed) + 1}",
                    title={"uz": title, "ru": title, "en": title},
                    guidance=str(item.get("guidance") or "Cover this aspect of the project in depth."),
                    artifact=ARTIFACT_DATA if len(proposed) == 0 else None,
                )
            )
        if not proposed:
            raise RuntimeError("AI loyiha bo'limlarini taklif qila olmadi")
        return proposed

    async def _section(
        self, topic: str, spec: SectionSpec, language: str, brief: str = "",
        field_key: str = GENERIC_FIELD_KEY,
    ) -> SectionContent:
        text = await self._section_text(topic, spec, language, brief)

        table = None
        chart = None
        note = ""
        if spec.artifact == ARTIFACT_SCHEME:
            # Sxema endi kod bilan chiziladi. AI chizgan sxemada yozuvlar
            # buzilib chiqardi va uni o'qib bo'lmasdi.
            #
            # Bu tekshiruv eng oldinda turishi SHART: sxema ham `CHART_ARTIFACTS`
            # ro'yxatida, shuning uchun u umumiy diagramma shoxiga tushib
            # ketardi va `_CHART_SHAPES["scheme"]` bo'lmagani uchun har safar
            # KeyError bergan — ya'ni tuzilma sxemasi hech bir loyiha ishida
            # chiqmagan, xato esa log ichida qolib ketgan.
            try:
                chart = await self._scheme(topic, spec, language, brief)
            except Exception as e:
                logger.error("Loyiha sxemasi olinmadi (%s): %s", spec.key, e)
        elif spec.artifact in TABLE_ARTIFACTS:
            try:
                table = await self._table(topic, spec, language, brief)
            except Exception as e:
                logger.error("Loyiha jadvali olinmadi (%s): %s", spec.key, e)
        elif spec.artifact in CHART_ARTIFACTS or spec.artifact in CARD_ARTIFACTS:
            try:
                chart = await self._chart(topic, spec, language, brief)
            except Exception as e:
                logger.error("Loyiha diagrammasi olinmadi (%s): %s", spec.key, e)
            if chart:
                note = str(chart.get("note") or "").strip()
                # Jadval ham shu ma'lumotdan quriladi — ikkinchi so'rov yo'q,
                # ya'ni jadvaldagi summa diagrammadagiga teng bo'ladi.
                if spec.artifact in DERIVED_TABLE_ARTIFACTS:
                    table = tables.derive(spec.artifact, chart, language)

        # Formulalar bo'lim ma'lumoti tayyor bo'lgandan keyin so'raladi:
        # model jadvaldagi raqamlarni ko'rib, shu raqamlar bilan hisoblaydi.
        formulas = []
        count = FORMULA_COUNTS.get(spec.artifact or "")
        if count:
            formulas = await self._formulas(
                topic, spec, language, field_key, count, chart or {}, table
            )

        return SectionContent(spec=spec, text=text, table=table, chart=chart,
                              image_prompt="", formulas=formulas, note=note)

    async def _section_text(self, topic: str, spec: SectionSpec, language: str, brief: str = "") -> str:
        target = _LANGUAGE_NAMES.get(language, "Uzbek")
        prompt = f"""Write the body text of one section of a project work ("loyiha ishi").

Project topic: "{topic}"
Section: "{spec.heading(language)}"
What this section must contain: {spec.guidance}

Write {spec.words} words in {target}.

RULES:
{heading_rule(language)}
- Be concrete: real figures, named examples, Uzbekistan context where it fits
- Plain text only — no markdown, no bullet lists, no special characters
- Do not mention that a table or figure follows; it is added automatically{self._source_block(brief)}"""

        response = await self.ai._make_request(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write project documentation. The section heading is already "
                        "printed above your text; you produce only the body text under it. "
                        "Plain text only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=token_budget(spec.words, language),
            temperature=0.75,
        )

        from services.ai_service import clean_text

        text = strip_echoed_heading(response, [spec.heading(language), topic])
        return trim_to_last_sentence(clean_text(text))

    # ------------------------------------------------------------- artefakt

    async def _table(self, topic: str, spec: SectionSpec, language: str, brief: str = "") -> Dict:
        kind = _TABLE_KINDS[spec.artifact]
        target = _LANGUAGE_NAMES.get(language, "Uzbek")
        columns = kind["columns"]

        if columns:
            headers = columns.get(language, columns["uz"])
            header_rule = (
                f'Use exactly these column headers, in this order: {json.dumps(headers, ensure_ascii=False)}'
            )
        else:
            header_rule = (
                f"Choose 4 column headers yourself, in {target}, that suit the section"
            )

        prompt = f"""Build a table for a project work.

Project topic: "{topic}"
Section: "{spec.heading(language)}"
The table must show {kind['ask']}.

{header_rule}
Produce {kind['rows']} data rows. Every cell must carry a real, specific value
in {target} — never "...", never an empty cell, never a placeholder.

{self._source_block(brief)}

Respond with JSON only:
{{"headers": ["..."], "rows": [["..."]]}}"""

        raw = await self._json_request(prompt, max_tokens=2000, temperature=0.4)

        headers = [str(h) for h in (raw.get("headers") or [])]
        if columns:
            headers = columns.get(language, columns["uz"])
        rows = [
            [str(cell) for cell in row]
            for row in (raw.get("rows") or [])
            if isinstance(row, list) and row
        ]
        if not headers or not rows:
            raise ValueError("jadval bo'sh qaytdi")
        return {"headers": headers, "rows": rows}

    async def _chart(self, topic: str, spec: SectionSpec, language: str, brief: str = "") -> Dict:
        """Diagramma uchun raqamli ma'lumot — jadvaldan farqli o'laroq son so'raladi."""
        ask, example = _CHART_SHAPES[spec.artifact]
        target = _LANGUAGE_NAMES.get(language, "Uzbek")
        prompt = f"""Produce the data behind a figure in a project work.

Project topic: "{topic}"
Section: "{spec.heading(language)}"

The data must give {ask}
Write every name and label in {target}. Numbers are plain digits — no spaces,
no thousand separators, no currency words inside the number.

Add one more key, "note": a single sentence in {target} saying what the figure
shows and what conclusion the reader should draw from it. It is printed under
the figure, so it must stand on its own — never "as can be seen in the figure
above".{self._source_block(brief)}

Respond with JSON only, in exactly this shape (plus "note"):
{example}"""

        raw = await self._json_request(prompt, max_tokens=2200, temperature=0.4)
        if self._has_chart_data(spec.artifact, raw):
            return raw
        raise ValueError("diagramma ma'lumoti bo'sh qaytdi")

    @staticmethod
    def _has_chart_data(artifact: str, raw: Dict) -> bool:
        """Ma'lumot chizishga yetarlimi. Zararsizlik nuqtasida ro'yxat yo'q —
        u to'rtta sondan chiziladi, shuning uchun tekshiruv boshqacha."""
        if artifact == ARTIFACT_BREAKEVEN:
            price = tables.number(raw.get("price"))
            variable = tables.number(raw.get("variable"))
            # Narx o'zgaruvchi xarajatdan past bo'lsa nuqta umuman yo'q:
            # chizma cheksizlikka ketardi.
            return bool(tables.number(raw.get("fixed")) > 0 and price > variable)
        return any(raw.get(key) for key in
                   ("items", "stages", "risks", "indicators", "points",
                    "periods", "channels"))

    async def _scheme(self, topic: str, spec: SectionSpec, language: str,
                      brief: str = "") -> Dict:
        """Loyiha tuzilmasi sxemasi uchun bloklar ierarxiyasini so'raydi."""
        target = _LANGUAGE_NAMES.get(language, "Uzbek")
        prompt = f"""Describe the structure of this project as a hierarchy of blocks.

Project topic: "{topic}"
Section: "{spec.heading(language)}"

"root" is the project or system name. "branches" are its 3-4 main parts;
each has 2-3 concrete components under it. Keep every label short — two or
three words — because they are drawn inside boxes. Write them in {target}.
The parts must be specific to this project, not generic
headings.{self._source_block(brief)}

Respond with JSON only:
{{"root": "Loyiha nomi",
  "branches": [{{"name": "Laboratoriya", "items": ["Namuna olish", "Tahlil"]}}]}}"""
        raw = await self._json_request(prompt, max_tokens=700, temperature=0.4)
        if not raw.get("branches"):
            raise ValueError("sxema bloklari bo'sh")
        return raw

    async def _formulas(
        self, topic: str, spec: SectionSpec, language: str, field_key: str,
        count: int, data: Dict, table: Optional[Dict],
    ) -> List[Dict]:
        """Bo'limning hisob-kitoblari — bittasi emas, bir nechtasi.

        Formulalar bo'lim ma'lumoti olingandan keyin so'raladi va shu
        ma'lumot promptga kiritiladi: aks holda model jadvalda 240 mln
        turganda hisobda 300 mln ishlatib yuborardi.

        Qaysi formulalar kerakligi bo'lim turiga va sohaga bog'liq —
        qishloq xo'jaligi loyihasida gektardan hosildorlik, IT loyihasida
        esa bir foydalanuvchi narxi hisoblanadi.
        """
        target = _LANGUAGE_NAMES.get(language, "Uzbek")
        ask = _FORMULA_ASKS.get(spec.artifact or "", _FORMULA_ASKS["default"])
        known = self._known_figures(data, table)

        prompt = f"""Work out the calculations for one section of a project work.

Project topic: "{topic}"
Field of study: {field_key}
Section: "{spec.heading(language)}"

Give exactly {count} calculation{'s' if count > 1 else ''}: {ask}

Choose the measures that genuinely fit THIS topic and field — a farming
project is measured per hectare, a workshop per unit of output, a software
project per user, a social project per beneficiary. Do not repeat the same
measure twice and do not invent a measure that this field does not use.

Every calculation must be worked through with real numbers: the formula, the
value of each symbol, and the figure that comes out. The arithmetic must be
correct — a reader will check it.{known}

"latex" is the formula in LaTeX without dollar signs. "name", "given",
"result", "meaning" are in {target}. Give "conclusion" only on the last
calculation, as the overall verdict.

Respond with JSON only:
{{"formulas": [
  {{"name": "Investitsiya rentabelligi (ROI)",
    "latex": "ROI = \\\\frac{{P}}{{I}} \\\\times 100\\\\%",
    "given": ["P — sof foyda, 148 mln so'm", "I — investitsiya, 420 mln so'm"],
    "result": "ROI = 35,2%",
    "meaning": "Bir yillik sof foyda investitsiyaning 35 foizini qoplaydi.",
    "conclusion": "Loyiha taxminan 2,8 yilda o'zini oqlaydi."}}]}}"""
        try:
            raw = await self._json_request(
                prompt, max_tokens=500 + 550 * count, temperature=0.3
            )
        except Exception as e:
            logger.error("Hisob-kitob formulalari olinmadi (%s): %s", spec.key, e)
            return []

        out = []
        for item in (raw.get("formulas") or [])[:count]:
            if isinstance(item, dict) and str(item.get("latex") or "").strip():
                out.append(item)
        if not out:
            logger.warning("Formulalar bo'sh qaytdi (%s)", spec.key)
        return out

    @staticmethod
    def _known_figures(data: Dict, table: Optional[Dict]) -> str:
        """Bo'limda allaqachon bor raqamlarni promptga qo'shadi.

        Shu bo'lmasa formula jadval bilan qarama-qarshi chiqadi va ustoz
        buni birinchi ko'radi.
        """
        lines = []
        for key in ("total", "fixed_total", "variable_total", "budget_total",
                    "customers_total", "cost_per_customer", "investment",
                    "fixed", "price", "variable", "planned", "payback_period",
                    "unit", "money_unit"):
            value = data.get(key)
            if value not in (None, "", 0):
                lines.append(f"{key} = {value}")
        output = data.get("output")
        if isinstance(output, dict) and output.get("value"):
            lines.append(f"output = {output.get('value')} {output.get('unit', '')}".strip())
        if table and table.get("rows"):
            headers = " | ".join(str(h) for h in table.get("headers") or [])
            body = "\n".join(" | ".join(str(cell) for cell in row)
                              for row in table["rows"][:8])
            lines.append(f"The section's table:\n{headers}\n{body}")
        if not lines:
            return ""
        return ("\n\nFIGURES ALREADY PRINTED IN THIS SECTION — your calculation "
                "must use these exact numbers and must not contradict them:\n"
                + "\n".join(lines))

    async def _references(self, topic: str, language: str) -> List[str]:
        try:
            return await self.ai.generate_references(topic, language)
        except Exception as e:
            logger.error("Loyiha ishi uchun adabiyotlar olinmadi: %s", e)
            return []

    # ------------------------------------------------------------- yordamchi

    async def _json_request(self, prompt: str, max_tokens: int, temperature: float) -> Dict:
        response = await self.ai._make_request(
            messages=[
                {"role": "system", "content": "Respond with valid JSON only. No markdown, no commentary."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise
