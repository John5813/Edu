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
from .specs import (
    ARTIFACT_BUDGET,
    ARTIFACT_FORECAST,
    ARTIFACT_DATA,
    ARTIFACT_RESULTS,
    ARTIFACT_RISKS,
    ARTIFACT_SCHEME,
    ARTIFACT_TIMELINE,
    CHART_ARTIFACTS,
    CARD_ARTIFACTS,
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

# Har artefakt turi qanday jadval ekani. Ustunlar hujjatga chop etiladi,
# shuning uchun uch tilda; `ask` faqat AI ga boradi.
_TABLE_KINDS = {
    ARTIFACT_TIMELINE: {
        "columns": {
            "uz": ["Bosqich", "Muddat", "Mas'ul", "Kutilayotgan natija"],
            "ru": ["Этап", "Срок", "Ответственный", "Ожидаемый результат"],
            "en": ["Stage", "Duration", "Responsible", "Expected result"],
        },
        "ask": "the sequential stages of carrying out the project, with realistic durations",
        "rows": 6,
    },
    ARTIFACT_BUDGET: {
        "columns": {
            "uz": ["Xarajat moddasi", "Miqdori", "Birlik narxi (so'm)", "Jami (so'm)"],
            "ru": ["Статья расходов", "Количество", "Цена за единицу (сум)", "Итого (сум)"],
            "en": ["Cost item", "Quantity", "Unit price (so'm)", "Total (so'm)"],
        },
        "ask": (
            "the project's cost items with realistic Uzbekistan market prices in so'm. "
            "The last row must be a total row and the totals must add up correctly"
        ),
        "rows": 7,
    },
    ARTIFACT_RISKS: {
        "columns": {
            "uz": ["Xavf", "Ehtimolligi", "Ta'siri", "Oldini olish chorasi"],
            "ru": ["Риск", "Вероятность", "Влияние", "Меры предотвращения"],
            "en": ["Risk", "Likelihood", "Impact", "Mitigation"],
        },
        "ask": (
            "the risks specific to this project, not generic ones. "
            "Likelihood and impact must be one of: yuqori / o'rta / past (in the target language)"
        ),
        "rows": 5,
    },
    ARTIFACT_RESULTS: {
        "columns": {
            "uz": ["Ko'rsatkich", "Hozirgi holat", "Maqsadli qiymat", "O'lchash usuli"],
            "ru": ["Показатель", "Текущее состояние", "Целевое значение", "Способ измерения"],
            "en": ["Indicator", "Current state", "Target value", "Measurement method"],
        },
        "ask": "measurable indicators of the project's success, with concrete numbers",
        "rows": 5,
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
        'the project cost items with realistic Uzbekistan market prices. '
        '"amount" must be a plain number of so\'m with no spaces or words. '
        'Give 5-7 items, largest first, and no total row — the chart sums them.',
        '{"items": [{"name": "Uskunalar va jihozlar", "amount": 48000000}]}',
    ),
    ARTIFACT_TIMELINE: (
        'the sequential stages of the project. "start" is the month the stage '
        'begins counted from zero, "duration" is its length in months; both are '
        'plain numbers. Stages follow one another without gaps. Give 5-7 stages.',
        '{"stages": [{"name": "Tayyorgarlik va loyihalash", "start": 0, "duration": 2, "owner": "Loyiha rahbari"}]}',
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
}


@dataclass
class SectionContent:
    spec: SectionSpec
    text: str
    table: Optional[Dict] = None       # {"headers": [...], "rows": [[...]]}
    chart: Optional[Dict] = None       # diagramma yoki kartochka uchun raqamli ma'lumot
    image_prompt: str = ""
    formula: Optional[Dict] = None


@dataclass
class ProjectContent:
    topic: str
    field_key: str
    language: str
    author_name: str = ""
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
        with_scheme: bool,
        depth: float = 1.0,
        source: Optional["SourceMaterial"] = None,
        progress_cb=None,
    ) -> ProjectContent:
        brief = await self._source_brief(source, topic)
        specs = [
            self._scaled(spec, depth)
            for spec in await self._resolve_sections(topic, field_key, language, brief)
        ]

        semaphore = asyncio.Semaphore(_CONCURRENCY)
        done = 0

        async def one(spec: SectionSpec) -> SectionContent:
            nonlocal done
            async with semaphore:
                section = await self._section(topic, spec, language, with_scheme, brief)
            done += 1
            if progress_cb:
                progress_cb(done, len(specs))
            return section

        sections = await asyncio.gather(*(one(spec) for spec in specs))
        references = await self._references(topic, language)
        return ProjectContent(
            topic=topic,
            field_key=field_key,
            language=language,
            sections=list(sections),
            references=references,
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
        self, topic: str, field_key: str, language: str, brief: str = ""
    ) -> List[SectionSpec]:
        if field_key != GENERIC_FIELD_KEY:
            return sections_for(field_key)
        return generic_sections(await self.propose_middle_sections(topic, language, brief))

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
        self, topic: str, spec: SectionSpec, language: str, with_scheme: bool, brief: str = ""
    ) -> SectionContent:
        text = await self._section_text(topic, spec, language, brief)

        table = None
        chart = None
        formula = None
        image_prompt = ""
        if spec.artifact in TABLE_ARTIFACTS:
            try:
                table = await self._table(topic, spec, language, brief)
            except Exception as e:
                logger.error("Loyiha jadvali olinmadi (%s): %s", spec.key, e)
        elif spec.artifact in CHART_ARTIFACTS or spec.artifact in CARD_ARTIFACTS:
            try:
                chart = await self._chart(topic, spec, language, brief)
            except Exception as e:
                logger.error("Loyiha diagrammasi olinmadi (%s): %s", spec.key, e)
            if spec.artifact == ARTIFACT_FORECAST:
                formula = await self._formula(topic, spec, language)
        elif spec.artifact == ARTIFACT_SCHEME and with_scheme:
            image_prompt = (
                f"clean professional diagram illustrating {spec.heading('en')} "
                f"for a project about {topic}, flat vector style, labelled boxes "
                f"and arrows, white background, no text captions"
            )

        return SectionContent(spec=spec, text=text, table=table, chart=chart,
                              image_prompt=image_prompt, formula=formula)

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
no thousand separators, no currency words inside the number.{self._source_block(brief)}

Respond with JSON only, in exactly this shape:
{example}"""

        raw = await self._json_request(prompt, max_tokens=1600, temperature=0.4)
        for key in ("items", "stages", "risks", "indicators", "points"):
            if raw.get(key):
                return raw
        raise ValueError("diagramma ma'lumoti bo'sh qaytdi")

    async def _formula(self, topic: str, spec: SectionSpec, language: str) -> Optional[Dict]:
        """Samaradorlik hisobi — formula, qiymatlar va natija."""
        target = _LANGUAGE_NAMES.get(language, "Uzbek")
        prompt = f"""Give the one calculation that proves this project's effectiveness.

Project topic: "{topic}"

Choose the measure that fits the field — payback period, return on investment,
yield per hectare, throughput, cost per unit — and show it worked through.
"latex" is the formula in LaTeX without dollar signs. "name", "meaning" and
"conclusion" are in {target}.

Respond with JSON only:
{{"name": "Investitsiya rentabelligi (ROI)",
  "latex": "ROI = \\\\frac{{P}}{{I}} \\\\times 100\\\\%",
  "given": ["P — sof foyda, 148 mln so'm", "I — investitsiya, 420 mln so'm"],
  "result": "ROI = 35,2%",
  "meaning": "Bir yillik sof foyda investitsiyaning 35 foizini qoplaydi.",
  "conclusion": "Loyiha taxminan 2,8 yilda o'zini oqlaydi."}}"""
        try:
            raw = await self._json_request(prompt, max_tokens=900, temperature=0.3)
            return raw if raw.get("latex") else None
        except Exception as e:
            logger.error("Samaradorlik formulasi olinmadi: %s", e)
            return None

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
