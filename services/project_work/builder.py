"""Spetsifikatsiya bo'yicha loyiha ishi DOCX faylini yig'ish.

Bitta quruvchi hamma sohaga xizmat qiladi: u bo'limlar ro'yxatini bosib
chiqadi, artefakt talab qilgan joyga jadval yoki sxema qo'yadi. Yangi soha
qo'shilganda bu fayl o'zgarmaydi.
"""

import asyncio
import logging
import os
from datetime import datetime
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from config import DOCUMENTS_DIR, TEMP_DIR

from . import charts, variety
from .content import ProjectContent, SectionContent
from .specs import (
    ARTIFACT_RESULTS,
    ARTIFACT_RISKS,
    ARTIFACT_TIMELINE,
)

logger = logging.getLogger(__name__)

_DOC_LABEL = {"uz": "LOYIHA ISHI", "ru": "ПРОЕКТНАЯ РАБОТА", "en": "PROJECT WORK"}
_FIELD_WORD = {"uz": "Yo'nalish", "ru": "Направление", "en": "Field"}
_TABLE_WORD = {"uz": "jadval", "ru": "Таблица", "en": "Table"}
_FIGURE_WORD = {"uz": "rasm", "ru": "Рисунок", "en": "Figure"}


def _table_caption(index: int, title: str, language: str) -> str:
    if language == "uz":
        return f"{index}-{_TABLE_WORD['uz']}. {title}"
    return f"{_TABLE_WORD.get(language, _TABLE_WORD['en'])} {index}. {title}"


def _figure_caption(index: int, title: str, language: str) -> str:
    if language == "uz":
        return f"{index}-{_FIGURE_WORD['uz']}. {title}"
    return f"{_FIGURE_WORD.get(language, _FIGURE_WORD['en'])} {index}. {title}"


class ProjectWorkBuilder:
    def __init__(self, document_service, together_service=None):
        self.documents = document_service
        self.together = together_service

    async def build(self, content: ProjectContent) -> str:
        images = await self._render_images(content)
        # Sxema hujjat boshida bir marta tanlanadi va butun hujjat bo'ylab
        # amal qiladi. Quruvchi umumiy obyekt bo'lgani uchun u `self` da
        # emas, chaqiruv zanjiri orqali uzatiladi.
        chosen = variety.choose(
            (content.language, content.topic, content.field_key),
            user_id=content.user_id,
        )
        try:
            return await asyncio.to_thread(self._build_sync, content, images, chosen)
        finally:
            for path in images.values():
                try:
                    os.remove(path)
                except OSError:
                    pass

    async def _render_images(self, content: ProjectContent) -> dict:
        wanted = [s for s in content.sections if s.image_prompt]
        if not wanted or not self.together:
            return {}
        results = await asyncio.gather(
            *(self.together.generate_image(s.image_prompt, aspect_ratio="4:3") for s in wanted),
            return_exceptions=True,
        )
        images = {}
        for section, result in zip(wanted, results):
            if isinstance(result, str) and result and os.path.exists(result):
                images[section.spec.key] = result
            else:
                logger.warning("Loyiha sxemasi chizilmadi (%s): %s", section.spec.key, result)
        return images

    # ------------------------------------------------------------------ docx

    def _build_sync(self, content: ProjectContent, images: dict, chosen) -> str:
        language = content.language
        doc = Document()

        style = doc.styles["Normal"]
        style.font.name = "Times New Roman"
        style.font.size = Pt(14)
        style.paragraph_format.line_spacing = 1.5

        for index, section in enumerate(doc.sections):
            section.top_margin = Inches(0.79)
            section.bottom_margin = Inches(0.79)
            section.left_margin = Inches(1.18)
            section.right_margin = Inches(0.39)
            section.footer.is_linked_to_previous = False
            if index == 0:
                section.different_first_page_header_footer = True

        self._title_page(doc, content, _DOC_LABEL.get(language, _DOC_LABEL["uz"]))

        doc.add_page_break()
        self._contents(doc, content)
        doc.add_page_break()

        for section in doc.sections:
            self.documents._add_page_number(section)

        self._body(doc, content, images, chosen)
        self._references(doc, content)

        os.makedirs(DOCUMENTS_DIR, exist_ok=True)
        filename = f"loyiha_ishi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        path = os.path.join(DOCUMENTS_DIR, filename)
        doc.save(path)
        logger.info("Loyiha ishi saqlandi: %s", path)
        return path

    def _title_page(self, doc, content: ProjectContent, label: str) -> None:
        """Title page for a project work — like the referat one, plus the field."""
        texts = self.documents._get_referat_template_texts(content.language)

        def centered(text: str, size: int = 14, bold: bool = False):
            para = doc.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = para.add_run(text)
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.name = "Times New Roman"
            return para

        centered("_" * 50)
        centered("_" * 20 + f" {texts['from_subject']}")
        for _ in range(4):
            doc.add_paragraph()

        centered(f"{label}:", size=36, bold=True)
        for _ in range(3):
            doc.add_paragraph()

        centered(f"{texts['topic']}: {content.topic}")
        from .specs import field_label

        centered(f"{_FIELD_WORD.get(content.language, _FIELD_WORD['uz'])}: "
                 f"{field_label(content.field_key, content.language)}")
        doc.add_paragraph()

        signatures = doc.add_paragraph()
        signatures.alignment = WD_ALIGN_PARAGRAPH.CENTER
        prepared = signatures.add_run(f"{texts['prepared_by']}: ")
        prepared.font.size = Pt(14)
        prepared.font.name = "Times New Roman"
        if content.author_name:
            author = signatures.add_run(content.author_name)
            author.font.bold = True
        else:
            author = signatures.add_run(f"_____ {texts['course']}")
        author.font.size = Pt(14)
        author.font.name = "Times New Roman"
        signatures.add_run("               ")
        accepted = signatures.add_run(f"{texts['accepted_by']}: " + "_" * 15)
        accepted.font.size = Pt(14)
        accepted.font.name = "Times New Roman"

        for _ in range(3):
            doc.add_paragraph()
        centered(texts["city"])

    def _contents(self, doc, content: ProjectContent) -> None:
        toc = self.documents._get_toc_texts(content.language)
        heading = doc.add_paragraph()
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = heading.add_run(toc.get("reja", "REJA").upper())
        run.font.size = Pt(14)
        run.font.bold = True

        numbered = 0
        for section in content.sections:
            item = doc.add_paragraph()
            if self._is_numbered(section):
                numbered += 1
                item.add_run(f"{numbered}. {section.spec.heading(content.language)}")
            else:
                item.add_run(section.spec.heading(content.language))

        if content.references:
            doc.add_paragraph().add_run(toc["adabiyotlar"])

    @staticmethod
    def _is_numbered(section: SectionContent) -> bool:
        """Kirish va xulosa raqamlanmaydi — akademik qoida shunday."""
        return section.spec.key not in {"kirish", "xulosa"}

    def _body(self, doc, content: ProjectContent, images: dict, chosen) -> None:
        language = content.language
        citable = [r for r in content.references if not r.startswith("__CATEGORY__")]
        table_no = 0
        figure_no = 0
        footnote_no = 1
        numbered = 0

        for section in content.sections:
            heading = doc.add_paragraph()
            heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if self._is_numbered(section):
                numbered += 1
                run = heading.add_run(f"{numbered}. {section.spec.heading(language)}")
            else:
                run = heading.add_run(section.spec.heading(language).upper())
            run.font.bold = True
            run.font.size = Pt(14)

            body = self._paragraphs(doc, section.text)

            if body and citable and self._is_numbered(section):
                reference = citable[(footnote_no - 1) % len(citable)]
                self.documents._add_footnote(body[-1], reference, footnote_no)
                footnote_no += 1

            if section.table:
                table_no += 1
                self._add_table(doc, section, table_no, language)

            if section.chart:
                figure_no, table_no = self._add_instrument(
                    doc, section, figure_no, table_no, language, chosen
                )

            if section.formula:
                self._add_formula(doc, section.formula, language)

            image_path = images.get(section.spec.key)
            if image_path:
                figure_no += 1
                self._add_figure(doc, section, image_path, figure_no, language)

    def _paragraphs(self, doc, text: str) -> list:
        from services.document_service import _split_into_paragraphs

        written = []
        for chunk in _split_into_paragraphs(text, target_count=2):
            para = doc.add_paragraph(chunk)
            para.paragraph_format.first_line_indent = Inches(0.5)
            para.paragraph_format.line_spacing = 1.5
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            written.append(para)
        return written

    def _add_instrument(self, doc, section: SectionContent, figure_no: int,
                        table_no: int, language: str, chosen) -> tuple:
        """Bo'limning raqamli ma'lumotini o'ziga mos shaklda chizadi."""
        artifact = section.spec.artifact
        data = section.chart or {}
        title = section.spec.heading(language)

        if artifact == ARTIFACT_RESULTS:
            self._add_indicator_cards(doc, data.get("indicators") or [], language)
            return figure_no, table_no

        if artifact not in variety.FORMS:
            return figure_no, table_no

        # Shakl va rang sxemasi hujjat boshida tanlangan: shu sababli bitta
        # ishda ikkita bir xil chizma bo'lmaydi, ketma-ket ishlar esa
        # bir-biriga o'xshamaydi.
        form = chosen.form(artifact)
        try:
            image_path = charts.draw(artifact, form, data, title, TEMP_DIR,
                                     palette=chosen.palette,
                                     unit=str(data.get("unit") or ""))
        except Exception as e:
            logger.warning("Diagramma chizilmadi (%s/%s): %s", section.spec.key, form, e)
            return figure_no, table_no

        figure_no += 1
        try:
            picture = doc.add_paragraph()
            picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
            picture.add_run().add_picture(image_path, width=Inches(5.9))
            self._caption(doc, _figure_caption(figure_no, title, language))
        finally:
            try:
                os.remove(image_path)
            except OSError:
                pass

        # Diagramma raqamni ko'rsatadi, tafsilotni esa yonidagi ro'yxat beradi.
        if artifact == ARTIFACT_RISKS:
            self._add_risk_key(doc, data.get("risks") or [], language)
        elif artifact == ARTIFACT_TIMELINE:
            self._add_stage_owners(doc, data.get("stages") or [], language)
        return figure_no, table_no

    def _caption(self, doc, text: str, align=WD_ALIGN_PARAGRAPH.CENTER) -> None:
        caption = doc.add_paragraph()
        caption.alignment = align
        run = caption.add_run(text)
        run.font.italic = True
        run.font.size = Pt(12)
        run.font.name = "Times New Roman"

    def _add_indicator_cards(self, doc, indicators: list, language: str) -> None:
        """Ko'rsatkichlar — jadval emas, "hozirgi → maqsad" kartochkalari."""
        rows = [i for i in indicators if i.get("name")][:5]
        if not rows:
            return

        table = doc.add_table(rows=len(rows), cols=2)
        table.style = "Table Grid"
        for index, indicator in enumerate(rows):
            name_cell, value_cell = table.rows[index].cells

            name_cell.text = str(indicator.get("name", ""))
            for paragraph in name_cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(12)
                    run.font.name = "Times New Roman"

            current = str(indicator.get("current", "")).strip()
            target = str(indicator.get("target", "")).strip()
            unit = str(indicator.get("unit", "")).strip()
            value_cell.text = ""
            paragraph = value_cell.paragraphs[0]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            big = paragraph.add_run(f"{current} → {target}")
            big.font.size = Pt(16)
            big.font.bold = True
            big.font.name = "Times New Roman"
            if unit:
                tail = paragraph.add_run(f"  {unit}")
                tail.font.size = Pt(11)
                tail.font.name = "Times New Roman"
        doc.add_paragraph()

    def _add_risk_key(self, doc, risks: list, language: str) -> None:
        """Matritsadagi raqamlar nimani anglatishini ochib beradi."""
        for number, risk in enumerate(risks[:9], start=1):
            para = doc.add_paragraph()
            para.paragraph_format.line_spacing = 1.15
            para.paragraph_format.left_indent = Inches(0.3)
            label = para.add_run(f"{number}. {risk.get('name', '')} — ")
            label.font.size = Pt(12)
            label.font.name = "Times New Roman"
            label.font.bold = True
            fix = para.add_run(str(risk.get("mitigation", "")))
            fix.font.size = Pt(12)
            fix.font.name = "Times New Roman"
        doc.add_paragraph()

    def _add_stage_owners(self, doc, stages: list, language: str) -> None:
        owners = [s for s in stages if s.get("owner")]
        if not owners:
            return
        for stage in owners[:8]:
            para = doc.add_paragraph()
            para.paragraph_format.line_spacing = 1.15
            para.paragraph_format.left_indent = Inches(0.3)
            run = para.add_run(f"{stage.get('name', '')} — {stage.get('owner', '')}")
            run.font.size = Pt(12)
            run.font.name = "Times New Roman"
        doc.add_paragraph()

    def _add_formula(self, doc, formula: dict, language: str) -> None:
        """Samaradorlik hisobi: formula, berilganlar, natija va izoh."""
        name = str(formula.get("name", "")).strip()
        if name:
            heading = doc.add_paragraph()
            run = heading.add_run(name)
            run.font.bold = True
            run.font.size = Pt(13)
            run.font.name = "Times New Roman"

        latex = str(formula.get("latex", "")).strip()
        if latex:
            try:
                image_path = charts.render_formula(latex, TEMP_DIR)
                para = doc.add_paragraph()
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                para.add_run().add_picture(image_path, width=Inches(3.6))
                os.remove(image_path)
            except Exception as e:
                logger.warning("Formula chizilmadi: %s", e)

        for given in (formula.get("given") or [])[:6]:
            para = doc.add_paragraph()
            para.paragraph_format.left_indent = Inches(0.3)
            para.paragraph_format.line_spacing = 1.15
            run = para.add_run(str(given))
            run.font.size = Pt(12)
            run.font.name = "Times New Roman"

        for key, bold in (("result", True), ("meaning", False), ("conclusion", False)):
            text = str(formula.get(key, "")).strip()
            if not text:
                continue
            para = doc.add_paragraph()
            para.paragraph_format.first_line_indent = Inches(0.5)
            para.paragraph_format.line_spacing = 1.5
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run = para.add_run(text)
            run.font.size = Pt(14)
            run.font.bold = bold
            run.font.name = "Times New Roman"
        doc.add_paragraph()

    def _add_table(self, doc, section: SectionContent, number: int, language: str) -> None:
        caption = doc.add_paragraph()
        caption.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        caption_run = caption.add_run(
            _table_caption(number, section.spec.heading(language), language)
        )
        caption_run.font.italic = True
        caption_run.font.size = Pt(12)
        caption_run.font.name = "Times New Roman"

        headers = section.table["headers"]
        rows = section.table["rows"]
        table = doc.add_table(rows=1 + len(rows), cols=len(headers))
        table.style = "Table Grid"

        for column, title in enumerate(headers):
            cell = table.rows[0].cells[column]
            cell.text = str(title)
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.font.bold = True
                    run.font.size = Pt(12)
                    run.font.name = "Times New Roman"

        for row_index, row in enumerate(rows, start=1):
            cells = table.rows[row_index].cells
            for column in range(len(headers)):
                value = str(row[column]) if column < len(row) else ""
                cells[column].text = value
                for paragraph in cells[column].paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(12)
                        run.font.name = "Times New Roman"

        doc.add_paragraph()

    def _add_figure(self, doc, section: SectionContent, image_path: str, number: int, language: str) -> None:
        picture = doc.add_paragraph()
        picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
        picture.add_run().add_picture(image_path, width=Inches(5.0))

        caption = doc.add_paragraph()
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption_run = caption.add_run(
            _figure_caption(number, section.spec.heading(language), language)
        )
        caption_run.font.italic = True
        caption_run.font.size = Pt(12)
        caption_run.font.name = "Times New Roman"
        doc.add_paragraph()

    def _references(self, doc, content: ProjectContent) -> None:
        if not content.references:
            return
        toc = self.documents._get_toc_texts(content.language)
        doc.add_page_break()
        heading = doc.add_paragraph()
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = heading.add_run(toc["adabiyotlar"].upper())
        run.font.bold = True
        run.font.size = Pt(14)

        for index, reference in enumerate(content.references, start=1):
            if reference.startswith("__CATEGORY__"):
                continue
            para = doc.add_paragraph()
            para.paragraph_format.first_line_indent = Inches(0.5)
            para.paragraph_format.line_spacing = 1.5
            para.add_run(f"{index}. {reference}")
