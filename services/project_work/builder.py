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

from config import DOCUMENTS_DIR

from .content import ProjectContent, SectionContent

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
        try:
            return await asyncio.to_thread(self._build_sync, content, images)
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

    def _build_sync(self, content: ProjectContent, images: dict) -> str:
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

        self._body(doc, content, images)
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

    def _body(self, doc, content: ProjectContent, images: dict) -> None:
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
