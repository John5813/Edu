import os
import logging
from datetime import datetime
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pptx import Presentation
from pptx.util import Inches as PptxInches, Pt as PptxPt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from typing import Dict, Optional, List
import asyncio
from config import DOCUMENTS_DIR, TEMP_DIR
from services.together_service import TogetherImageService

logger = logging.getLogger(__name__)

class DocumentService:
    def __init__(self):
        self.documents_dir = DOCUMENTS_DIR
        self.temp_dir = TEMP_DIR
        try:
            self.together = TogetherImageService()
        except Exception as e:
            logger.warning(f"Together AI not available: {e}")
            self.together = None

    async def create_presentation_with_smart_images(self, topic: str, content: Dict, author_name: str, language: str = "uz", template_service=None, template_id: str = None) -> str:
        """Create PowerPoint presentation with new layout system and Together AI images
        
        NEW STRUCTURE:
        1. Muqova - O'ng: Mavzu + Ism, Chap: 50% rasm
        2. Reja - 4 asosiy punkt
        3. Kirish - ~50 so'z
        4-N. Asosiy slaidlar (6 ta shablon aylanib)
        N+1. Xulosa - ~50 so'z
        N+2. Adabiyotlar
        N+3. Rahmat
        """
        try:
            prs = Presentation()
            prs.slide_width = PptxInches(13.333)
            prs.slide_height = PptxInches(7.5)
            
            slides_data = content.get('slides', [])
            
            for i, slide_data in enumerate(slides_data):
                layout = slide_data.get('layout', 'text_only')
                await self._create_slide_by_layout(prs, slide_data, i, author_name, topic, language, template_service, template_id)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"presentation_{timestamp}.pptx"
            file_path = os.path.join(self.documents_dir, filename)
            prs.save(file_path)
            logger.info(f"Presentation saved: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error creating presentation: {e}")
            raise

    async def _create_slide_by_layout(self, prs, slide_data: Dict, slide_idx: int, author_name: str, topic: str, language: str, template_service=None, template_id: str = None):
        """Create slide based on layout type"""
        layout = slide_data.get('layout', 'text_only')
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        
        if template_service and template_id:
            template_service.apply_template_to_slide(slide, template_id)
        
        if layout == 'cover':
            await self._create_cover_slide(slide, slide_data, author_name, topic, language)
        elif layout == 'plan':
            self._create_plan_slide(slide, slide_data)
        elif layout == 'intro':
            self._create_intro_slide(slide, slide_data)
        elif layout == 'two_column':
            self._create_two_column_slide(slide, slide_data, language)
        elif layout == 'right_image':
            await self._create_right_image_slide(slide, slide_data, topic, language)
        elif layout == 'left_image':
            await self._create_left_image_slide(slide, slide_data, topic, language)
        elif layout == 'three_column':
            self._create_three_column_slide(slide, slide_data, language)
        elif layout == 'horizontal_image':
            await self._create_horizontal_image_slide(slide, slide_data, topic, language)
        elif layout == 'text_with_numbers':
            self._create_text_with_numbers_slide(slide, slide_data)
        elif layout == 'conclusion':
            self._create_conclusion_slide(slide, slide_data)
        elif layout == 'references':
            self._create_references_slide(slide, slide_data)
        elif layout == 'thanks':
            self._create_thanks_slide(slide, language)
        else:
            self._create_default_slide(slide, slide_data)

    async def _create_cover_slide(self, slide, slide_data: Dict, author_name: str, topic: str, language: str):
        """1-varoq: Chap 50% rasm, O'ng mavzu + ism"""
        if self.together:
            try:
                image_path = await self.together.generate_cover_image(topic, language)
                if image_path and os.path.exists(image_path):
                    slide.shapes.add_picture(
                        image_path,
                        PptxInches(0), PptxInches(0),
                        PptxInches(6.666), PptxInches(7.5)
                    )
            except Exception as e:
                logger.error(f"Error generating cover image: {e}")
        
        title_box = slide.shapes.add_textbox(
            PptxInches(7), PptxInches(2.5),
            PptxInches(5.8), PptxInches(3)
        )
        tf = title_box.text_frame
        tf.word_wrap = True
        
        p1 = tf.paragraphs[0]
        p1.text = topic
        p1.font.size = PptxPt(42)
        p1.font.bold = True
        p1.font.color.rgb = RGBColor(0, 0, 0)
        p1.alignment = PP_ALIGN.CENTER
        
        p2 = tf.add_paragraph()
        p2.text = author_name if author_name else "________________"
        p2.font.size = PptxPt(26)
        p2.font.bold = True
        p2.alignment = PP_ALIGN.CENTER

    def _create_plan_slide(self, slide, slide_data: Dict):
        """2-varoq: Reja - 4 asosiy punkt"""
        self._add_slide_title(slide, slide_data.get('title', 'Reja'))
        
        plan_items = slide_data.get('plan_items', [])
        content_box = slide.shapes.add_textbox(
            PptxInches(1), PptxInches(2),
            PptxInches(11), PptxInches(5)
        )
        tf = content_box.text_frame
        tf.word_wrap = True
        
        for i, item in enumerate(plan_items[:4]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = item if item.startswith(str(i+1)) else f"{i+1}. {item}"
            p.font.size = PptxPt(26)
            p.font.bold = True
            p.alignment = PP_ALIGN.JUSTIFY
            p.space_after = PptxPt(24)

    def _create_intro_slide(self, slide, slide_data: Dict):
        """3-varoq: Kirish - ~50 so'z"""
        self._add_slide_title(slide, slide_data.get('title', 'Kirish'))
        self._add_justified_content(slide, slide_data.get('content', ''), 
                                    PptxInches(1), PptxInches(2), 
                                    PptxInches(11), PptxInches(5))

    def _create_two_column_slide(self, slide, slide_data: Dict, language: str = 'uz'):
        """Shablon 1: 2 ustunli - har ustun 30 so'z"""
        self._add_slide_title(slide, slide_data.get('title', ''))
        
        columns = slide_data.get('columns', [])
        content = slide_data.get('content', '')
        
        if isinstance(content, list):
            content = ' '.join(str(item) for item in content)
        
        if not columns and content:
            words = content.split()
            mid = len(words) // 2
            columns = [
                {'text': ' '.join(words[:mid])},
                {'text': ' '.join(words[mid:])}
            ]
        
        font_size = 23 if language in ['ru', 'en'] else 24
        
        for i, col in enumerate(columns[:2]):
            x_pos = PptxInches(0.5) if i == 0 else PptxInches(6.9)
            box = slide.shapes.add_textbox(x_pos, PptxInches(2), PptxInches(5.9), PptxInches(5))
            tf = box.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            if isinstance(col, dict):
                col_text = col.get('column_content', col.get('text', col.get('content', '')))
            else:
                col_text = str(col)
            p.text = col_text
            p.font.size = PptxPt(font_size)
            p.alignment = PP_ALIGN.LEFT

    async def _create_right_image_slide(self, slide, slide_data: Dict, topic: str, language: str):
        """Shablon 2: O'ng 50% rasm, chap matn"""
        self._add_slide_title(slide, slide_data.get('title', ''))
        
        self._add_justified_content(slide, slide_data.get('content', ''),
                                    PptxInches(0.5), PptxInches(2),
                                    PptxInches(6), PptxInches(5))
        
        if self.together:
            try:
                image_path = await self.together.generate_slide_image(
                    topic, slide_data.get('title', ''), language
                )
                if image_path and os.path.exists(image_path):
                    slide.shapes.add_picture(
                        image_path,
                        PptxInches(6.8), PptxInches(1.5),
                        PptxInches(6.2), PptxInches(5.5)
                    )
            except Exception as e:
                logger.error(f"Error generating right image: {e}")

    async def _create_left_image_slide(self, slide, slide_data: Dict, topic: str, language: str):
        """Shablon 3: Chap 50% rasm, o'ng matn"""
        self._add_slide_title(slide, slide_data.get('title', ''))
        
        if self.together:
            try:
                image_path = await self.together.generate_slide_image(
                    topic, slide_data.get('title', ''), language
                )
                if image_path and os.path.exists(image_path):
                    slide.shapes.add_picture(
                        image_path,
                        PptxInches(0.3), PptxInches(1.5),
                        PptxInches(6.2), PptxInches(5.5)
                    )
            except Exception as e:
                logger.error(f"Error generating left image: {e}")
        
        self._add_justified_content(slide, slide_data.get('content', ''),
                                    PptxInches(6.8), PptxInches(2),
                                    PptxInches(6), PptxInches(5))

    def _create_three_column_slide(self, slide, slide_data: Dict, language: str = 'uz'):
        """Shablon 4: 3 ustunli - har ustun 20 so'z"""
        self._add_slide_title(slide, slide_data.get('title', ''))
        
        columns = slide_data.get('columns', [])
        content = slide_data.get('content', '')
        
        if isinstance(content, list):
            content = ' '.join(str(item) for item in content)
        
        if not columns and content:
            words = content.split()
            third = len(words) // 3
            columns = [
                {'text': ' '.join(words[:third])},
                {'text': ' '.join(words[third:2*third])},
                {'text': ' '.join(words[2*third:])}
            ]
        
        font_size = 23 if language in ['ru', 'en'] else 24
        
        for i, col in enumerate(columns[:3]):
            x_pos = PptxInches(0.4 + i * 4.3)
            box = slide.shapes.add_textbox(x_pos, PptxInches(2), PptxInches(4), PptxInches(5))
            tf = box.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            if isinstance(col, dict):
                col_text = col.get('column_content', col.get('text', col.get('content', '')))
            else:
                col_text = str(col)
            p.text = col_text
            p.font.size = PptxPt(font_size)
            p.alignment = PP_ALIGN.LEFT

    async def _create_horizontal_image_slide(self, slide, slide_data: Dict, topic: str, language: str):
        """Shablon 5: Pastda 21:9 gorizontal rasm, ustida matn"""
        self._add_slide_title(slide, slide_data.get('title', ''))
        
        self._add_justified_content(slide, slide_data.get('content', ''),
                                    PptxInches(0.5), PptxInches(1.5),
                                    PptxInches(12), PptxInches(2))
        
        if self.together:
            try:
                image_path = await self.together.generate_panoramic_image(
                    topic, slide_data.get('title', ''), language
                )
                if image_path and os.path.exists(image_path):
                    slide.shapes.add_picture(
                        image_path,
                        PptxInches(0.3), PptxInches(4),
                        PptxInches(12.7), PptxInches(3.3)
                    )
            except Exception as e:
                logger.error(f"Error generating horizontal image: {e}")

    def _create_text_with_numbers_slide(self, slide, slide_data: Dict):
        """Shablon 6: Raqamlangan ro'yxat ko'rinishida - 5 ta punkt"""
        self._add_slide_title(slide, slide_data.get('title', ''))
        
        content = slide_data.get('content', '')
        
        numbered_items = slide_data.get('numbered_items', [])
        if not numbered_items and content:
            sentences = [s.strip() for s in content.replace('\n', '. ').split('.') if s.strip()]
            numbered_items = sentences[:5]
        
        content_box = slide.shapes.add_textbox(
            PptxInches(1), PptxInches(2),
            PptxInches(11), PptxInches(5)
        )
        tf = content_box.text_frame
        tf.word_wrap = True
        
        for i, item in enumerate(numbered_items[:5]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            item_text = item.strip()
            if item_text.startswith(f"{i+1}.") or item_text.startswith(f"{i+1})"):
                p.text = item_text
            else:
                p.text = f"{i+1}. {item_text}"
            p.font.size = PptxPt(26)
            p.alignment = PP_ALIGN.LEFT
            p.space_after = PptxPt(18)

    def _create_conclusion_slide(self, slide, slide_data: Dict):
        """Xulosa slayd - ~50 so'z"""
        self._add_slide_title(slide, slide_data.get('title', 'Xulosa'))
        self._add_justified_content(slide, slide_data.get('content', ''),
                                    PptxInches(1), PptxInches(2),
                                    PptxInches(11), PptxInches(5))

    def _create_references_slide(self, slide, slide_data: Dict):
        """Adabiyotlar ro'yxati slayd"""
        self._add_slide_title(slide, slide_data.get('title', 'Foydalangan adabiyotlar'))
        
        references = slide_data.get('references', [])
        if isinstance(references, str):
            references = [references]
        
        content_box = slide.shapes.add_textbox(
            PptxInches(0.5), PptxInches(2),
            PptxInches(12), PptxInches(5)
        )
        tf = content_box.text_frame
        tf.word_wrap = True
        
        for i, ref in enumerate(references[:6]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = f"{i+1}. {ref}" if not ref.startswith(str(i+1)) else ref
            p.font.size = PptxPt(24)
            p.alignment = PP_ALIGN.JUSTIFY
            p.space_after = PptxPt(12)

    def _create_thanks_slide(self, slide, language: str):
        """Rahmat slayd - E'tiboringiz uchun rahmat!"""
        thanks_texts = {
            'uz': "E'tiboringiz uchun rahmat!",
            'ru': "Спасибо за внимание!",
            'en': "Thank you for your attention!"
        }
        
        text = thanks_texts.get(language, thanks_texts['uz'])
        
        thanks_box = slide.shapes.add_textbox(
            PptxInches(1), PptxInches(3),
            PptxInches(11), PptxInches(2)
        )
        tf = thanks_box.text_frame
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = PptxPt(48)
        p.font.bold = True
        p.font.color.rgb = RGBColor(0, 0, 0)
        p.alignment = PP_ALIGN.CENTER

    def _create_default_slide(self, slide, slide_data: Dict):
        """Default text slide"""
        self._add_slide_title(slide, slide_data.get('title', ''))
        self._add_justified_content(slide, slide_data.get('content', ''),
                                    PptxInches(1), PptxInches(2),
                                    PptxInches(11), PptxInches(5))

    def _add_slide_title(self, slide, title: str):
        """Add title to slide - qalin qora 42pt"""
        title_box = slide.shapes.add_textbox(
            PptxInches(0.3), PptxInches(0.3),
            PptxInches(12.7), PptxInches(1)
        )
        tf = title_box.text_frame
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = PptxPt(42)
        p.font.bold = True
        p.font.color.rgb = RGBColor(0, 0, 0)
        p.alignment = PP_ALIGN.CENTER

    def _add_justified_content(self, slide, content, left: float, top: float, width: float, height: float):
        """Add justified content text - 24pt"""
        if isinstance(content, list):
            content = ' '.join(str(item) for item in content)
        elif not isinstance(content, str):
            content = str(content) if content else ''
            
        content_box = slide.shapes.add_textbox(left, top, width, height)
        tf = content_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = content
        p.font.size = PptxPt(24)
        p.alignment = PP_ALIGN.JUSTIFY

    async def create_presentation(self, topic: str, content: Dict, images: Dict, author_name: str) -> str:
        """Legacy method - redirects to new method"""
        return await self.create_presentation_with_smart_images(topic, content, author_name)

    async def create_presentation_with_layouts(self, topic: str, content: Dict, author_name: str) -> str:
        """Legacy method - redirects to new method"""
        return await self.create_presentation_with_smart_images(topic, content, author_name)

    async def create_presentation_from_template(self, topic: str, content: Dict, author_name: str, template_path: str) -> str:
        """Create presentation from template - falls back to standard creation"""
        return await self.create_presentation_with_smart_images(topic, content, author_name)

    async def create_independent_work(self, topic: str, content: Dict) -> str:
        """Create independent work document"""
        try:
            doc = Document()
            style = doc.styles['Normal']
            font = style.font
            font.name = 'Times New Roman'
            font.size = Pt(14)
            
            paragraph_format = style.paragraph_format
            paragraph_format.line_spacing = 1.5
            
            for section in doc.sections:
                section.top_margin = Inches(0.79)
                section.bottom_margin = Inches(0.79)
                section.left_margin = Inches(1.18)
                section.right_margin = Inches(0.39)

            user_lang = content.get('language', 'uz')
            author_name = content.get('author_name', '')
            await self._create_independent_work_title_page(doc, topic, user_lang, author_name)

            doc.add_page_break()

            toc_texts = self._get_toc_texts(user_lang)
            
            toc_para = doc.add_paragraph()
            toc_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            toc_run = toc_para.add_run(toc_texts.get('reja', 'REJA').upper())
            toc_run.font.size = Pt(14)
            toc_run.font.bold = True
            all_sections = content.get('sections', [])

            toc_item = doc.add_paragraph()
            toc_item.add_run(toc_texts['kirish'])

            numbered_count = 0
            for idx, section in enumerate(all_sections):
                if idx == 0 or idx == len(all_sections) - 1:
                    continue
                numbered_count += 1
                toc_item = doc.add_paragraph()
                toc_item.add_run(f"{numbered_count}. {section['title']}")

            toc_item = doc.add_paragraph()
            toc_item.add_run(toc_texts['xulosa'])

            if content.get('references'):
                toc_item = doc.add_paragraph()
                toc_item.add_run(toc_texts['adabiyotlar'])

            doc.add_page_break()

            for section in doc.sections:
                self._add_page_number(section)

            numbered_section_count = 0
            for idx, section in enumerate(all_sections):
                title = section['title']
                
                if idx == len(all_sections) - 1:
                    doc.add_page_break()
                
                section_title = doc.add_paragraph()
                section_title.alignment = WD_ALIGN_PARAGRAPH.CENTER

                if idx == 0:
                    section_title_run = section_title.add_run(toc_texts['kirish'].upper())
                elif idx == len(all_sections) - 1:
                    section_title_run = section_title.add_run(toc_texts['xulosa'].upper())
                else:
                    numbered_section_count += 1
                    section_title_run = section_title.add_run(f"{numbered_section_count}. {title}")

                section_title_run.font.bold = True
                section_title_run.font.size = Pt(14)

                content_para = doc.add_paragraph(section['content'])
                content_para.paragraph_format.first_line_indent = Inches(0.5)
                content_para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                content_para.paragraph_format.line_spacing = 1.5

            if content.get('references'):
                doc.add_page_break()
                ref_title = doc.add_paragraph()
                ref_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
                ref_title_run = ref_title.add_run(toc_texts['adabiyotlar'].upper())
                ref_title_run.font.bold = True
                ref_title_run.font.size = Pt(14)

                references = content['references'][:5]
                for idx, ref in enumerate(references, 1):
                    ref_para = doc.add_paragraph()
                    ref_para.paragraph_format.first_line_indent = Inches(0.5)
                    ref_para.paragraph_format.line_spacing = 1.5
                    ref_para.add_run(f"{idx}. {ref}")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"independent_work_{timestamp}.docx"
            file_path = os.path.join(self.documents_dir, filename)
            doc.save(file_path)
            logger.info(f"Independent work saved: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Error creating independent work: {e}")
            raise

    async def create_referat(self, topic: str, content: Dict) -> str:
        """Create referat document"""
        try:
            doc = Document()
            style = doc.styles['Normal']
            font = style.font
            font.name = 'Times New Roman'
            font.size = Pt(14)

            paragraph_format = style.paragraph_format
            paragraph_format.line_spacing = 1.5

            for idx, section in enumerate(doc.sections):
                section.top_margin = Inches(0.79)
                section.bottom_margin = Inches(0.79)
                section.left_margin = Inches(1.18)
                section.right_margin = Inches(0.39)
                section.footer.is_linked_to_previous = False
                if idx == 0:
                    section.different_first_page_header_footer = True

            user_lang = content.get('language', 'uz')
            author_name = content.get('author_name', '')
            await self._create_referat_title_page(doc, topic, user_lang, author_name)

            doc.add_page_break()

            toc_texts = self._get_toc_texts(user_lang)
            
            toc_para = doc.add_paragraph()
            toc_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            toc_run = toc_para.add_run(toc_texts.get('reja', 'REJA').upper())
            toc_run.font.size = Pt(14)
            toc_run.font.bold = True
            all_sections = content.get('sections', [])

            toc_item = doc.add_paragraph()
            toc_item.add_run(toc_texts['kirish'])

            numbered_count = 0
            for idx, section in enumerate(all_sections):
                if idx == 0 or idx == len(all_sections) - 1:
                    continue
                numbered_count += 1
                toc_item = doc.add_paragraph()
                toc_item.add_run(f"{numbered_count}. {section['title']}")

            toc_item = doc.add_paragraph()
            toc_item.add_run(toc_texts['xulosa'])

            if content.get('references'):
                toc_item = doc.add_paragraph()
                toc_item.add_run(toc_texts['adabiyotlar'])

            doc.add_page_break()

            for section in doc.sections:
                self._add_page_number(section)

            numbered_section_count = 0
            for idx, section in enumerate(all_sections):
                title = section['title']
                
                if idx == len(all_sections) - 1:
                    doc.add_page_break()
                
                section_title = doc.add_paragraph()
                section_title.alignment = WD_ALIGN_PARAGRAPH.CENTER

                if idx == 0:
                    section_title_run = section_title.add_run(toc_texts['kirish'].upper())
                elif idx == len(all_sections) - 1:
                    section_title_run = section_title.add_run(toc_texts['xulosa'].upper())
                else:
                    numbered_section_count += 1
                    section_title_run = section_title.add_run(f"{numbered_section_count}. {title}")

                section_title_run.font.bold = True
                section_title_run.font.size = Pt(14)

                content_para = doc.add_paragraph(section['content'])
                content_para.paragraph_format.first_line_indent = Inches(0.5)
                content_para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                content_para.paragraph_format.line_spacing = 1.5

            if content.get('references'):
                doc.add_page_break()
                ref_title = doc.add_paragraph()
                ref_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
                ref_title_run = ref_title.add_run(toc_texts['adabiyotlar'].upper())
                ref_title_run.font.bold = True
                ref_title_run.font.size = Pt(14)

                references = content['references'][:5]
                references_reversed = list(reversed(references))
                for idx, ref in enumerate(references_reversed, 1):
                    ref_para = doc.add_paragraph()
                    ref_para.paragraph_format.first_line_indent = Inches(0.5)
                    ref_para.paragraph_format.line_spacing = 1.5
                    ref_para.add_run(f"{idx}. {ref}")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"referat_{timestamp}.docx"
            file_path = os.path.join(self.documents_dir, filename)
            doc.save(file_path)
            logger.info(f"Referat saved: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Error creating referat: {e}")
            raise

    async def _create_referat_title_page(self, doc, topic: str, language: str = 'uz', author_name: str = ''):
        """Create referat title page"""
        try:
            texts = self._get_referat_template_texts(language)

            para1 = doc.add_paragraph()
            para1.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run1 = para1.add_run("_" * 50)
            run1.font.size = Pt(14)
            run1.font.name = 'Times New Roman'

            para2 = doc.add_paragraph()
            para2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run2 = para2.add_run("_" * 20 + f" {texts['from_subject']}")
            run2.font.size = Pt(14)
            run2.font.name = 'Times New Roman'

            for _ in range(4):
                doc.add_paragraph()

            title_para = doc.add_paragraph()
            title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title_run = title_para.add_run(f"{texts['referat']}:")
            title_run.font.size = Pt(36)
            title_run.font.bold = True
            title_run.font.name = 'Times New Roman'

            for _ in range(3):
                doc.add_paragraph()

            topic_para = doc.add_paragraph()
            topic_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            topic_run = topic_para.add_run(f"{texts['topic']}: {topic}")
            topic_run.font.size = Pt(14)
            topic_run.font.name = 'Times New Roman'

            for _ in range(2):
                doc.add_paragraph()

            signatures_para = doc.add_paragraph()
            signatures_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

            bajardi_run = signatures_para.add_run(f"{texts['prepared_by']}: ")
            bajardi_run.font.size = Pt(14)
            bajardi_run.font.name = 'Times New Roman'

            if author_name:
                author_run = signatures_para.add_run(f"{author_name}")
                author_run.font.size = Pt(14)
                author_run.font.name = 'Times New Roman'
                author_run.font.bold = True
            else:
                kurs_run = signatures_para.add_run(f"_____ {texts['course']}")
                kurs_run.font.size = Pt(14)
                kurs_run.font.name = 'Times New Roman'

            signatures_para.add_run("               ")

            qabul_run = signatures_para.add_run(f"{texts['accepted_by']}: ")
            qabul_run.font.size = Pt(14)
            qabul_run.font.name = 'Times New Roman'

            qabul_line_run = signatures_para.add_run("_" * 15)
            qabul_line_run.font.size = Pt(14)
            qabul_line_run.font.name = 'Times New Roman'

            for _ in range(3):
                doc.add_paragraph()

            city_para = doc.add_paragraph()
            city_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            city_run = city_para.add_run(texts['city'])
            city_run.font.size = Pt(14)
            city_run.font.name = 'Times New Roman'

        except Exception as e:
            logger.error(f"Error creating referat title page: {e}")

    def _get_referat_template_texts(self, language: str) -> Dict[str, str]:
        """Get language-specific texts for referat template"""
        if language == 'ru':
            return {
                'from_subject': 'по предмету',
                'referat': 'РЕФЕРАТ',
                'topic': 'Тема',
                'prepared_by': 'Выполнил',
                'course': 'курс',
                'accepted_by': 'Принял',
                'city': 'Ташкент'
            }
        elif language == 'en':
            return {
                'from_subject': 'on the subject',
                'referat': 'REPORT',
                'topic': 'Topic',
                'prepared_by': 'Prepared by',
                'course': 'course',
                'accepted_by': 'Accepted by',
                'city': 'Tashkent'
            }
        else:
            return {
                'from_subject': 'fanidan',
                'referat': 'REFERAT',
                'topic': 'Mavzu',
                'prepared_by': 'Bajardi',
                'course': 'kurs',
                'accepted_by': 'Qabul qildi',
                'city': 'Toshkent'
            }

    async def _create_independent_work_title_page(self, doc, topic: str, language: str = 'uz', author_name: str = ''):
        """Create independent work title page"""
        try:
            texts = self._get_independent_work_template_texts(language)

            faculty_para = doc.add_paragraph()
            faculty_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            faculty_run = faculty_para.add_run("_" * 30 + f" {texts['faculty']}")
            faculty_run.font.size = Pt(14)
            faculty_run.font.name = 'Times New Roman'

            subject_para = doc.add_paragraph()
            subject_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            subject_run = subject_para.add_run("_" * 30 + f" {texts['from_subject']}")
            subject_run.font.size = Pt(14)
            subject_run.font.name = 'Times New Roman'

            for _ in range(3):
                doc.add_paragraph()

            title_para = doc.add_paragraph()
            title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title_run = title_para.add_run(texts['independent_work'])
            title_run.font.size = Pt(32)
            title_run.font.bold = True
            title_run.font.name = 'Times New Roman'

            for _ in range(2):
                doc.add_paragraph()

            topic_para = doc.add_paragraph()
            topic_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            topic_run = topic_para.add_run(f"{texts['topic']}: {topic}")
            topic_run.font.size = Pt(14)
            topic_run.font.name = 'Times New Roman'

            for _ in range(4):
                doc.add_paragraph()

            signatures_para = doc.add_paragraph()
            signatures_para.alignment = WD_ALIGN_PARAGRAPH.LEFT

            bajardi_run = signatures_para.add_run(f"{texts['prepared_by']}: ")
            bajardi_run.font.size = Pt(14)
            bajardi_run.font.name = 'Times New Roman'

            if author_name:
                author_run = signatures_para.add_run(f"{author_name}")
                author_run.font.size = Pt(14)
                author_run.font.name = 'Times New Roman'
                author_run.font.bold = True
            else:
                bajardi_line_run = signatures_para.add_run("_" * 18)
                bajardi_line_run.font.size = Pt(14)
                bajardi_line_run.font.name = 'Times New Roman'

            signatures_para.add_run("         ")

            qabul_run = signatures_para.add_run(f"{texts['accepted_by']}: ")
            qabul_run.font.size = Pt(14)
            qabul_run.font.name = 'Times New Roman'

            qabul_line_run = signatures_para.add_run("_" * 15)
            qabul_line_run.font.size = Pt(14)
            qabul_line_run.font.name = 'Times New Roman'

        except Exception as e:
            logger.error(f"Error creating independent work title page: {e}")

    def _get_independent_work_template_texts(self, language: str) -> Dict[str, str]:
        """Get language-specific texts for independent work template"""
        if language == 'ru':
            return {
                'faculty': 'факультета',
                'from_subject': 'по предмету',
                'independent_work': 'Самостоятельная работа',
                'topic': 'Тема',
                'prepared_by': 'Выполнил',
                'accepted_by': 'Принял'
            }
        elif language == 'en':
            return {
                'faculty': 'faculty',
                'from_subject': 'on the subject',
                'independent_work': 'Independent work',
                'topic': 'Topic',
                'prepared_by': 'Prepared by',
                'accepted_by': 'Accepted by'
            }
        else:
            return {
                'faculty': 'fakulteti',
                'from_subject': 'fanidan',
                'independent_work': 'Mustaqil ish',
                'topic': 'Mavzu',
                'prepared_by': 'Bajardi',
                'accepted_by': 'Qabul qildi'
            }

    def _get_toc_texts(self, language: str) -> dict:
        """Get language-specific texts for table of contents"""
        if language == 'ru':
            return {
                'reja': 'План',
                'kirish': 'Введение',
                'xulosa': 'Заключение',
                'adabiyotlar': 'Использованная литература'
            }
        elif language == 'en':
            return {
                'reja': 'Contents',
                'kirish': 'Introduction',
                'xulosa': 'Conclusion',
                'adabiyotlar': 'References'
            }
        else:
            return {
                'reja': 'Reja',
                'kirish': 'Kirish',
                'xulosa': 'Xulosa',
                'adabiyotlar': 'Foydalangan adabiyotlar'
            }

    def _add_page_number(self, section):
        """Add page number to footer"""
        try:
            footer = section.footer
            paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

            run = paragraph.add_run()

            fldChar1 = OxmlElement('w:fldChar')
            fldChar1.set(qn('w:fldCharType'), 'begin')
            run._r.append(fldChar1)

            instrText = OxmlElement('w:instrText')
            instrText.set(qn('xml:space'), 'preserve')
            instrText.text = "PAGE"
            run._r.append(instrText)

            fldChar2 = OxmlElement('w:fldChar')
            fldChar2.set(qn('w:fldCharType'), 'separate')
            run._r.append(fldChar2)

            fldChar3 = OxmlElement('w:fldChar')
            fldChar3.set(qn('w:fldCharType'), 'end')
            run._r.append(fldChar3)

            run.font.size = Pt(14)
            run.font.name = 'Times New Roman'
        except Exception as e:
            logger.error(f"Error adding page number: {e}")

    async def create_presentation_with_template_background(
        self, 
        topic: str, 
        content: Dict, 
        author_name: str, 
        template_id: str, 
        template_service, 
        language: str, 
        references: List = None, 
        plan_items: List = None
    ) -> str:
        """Create presentation with template background and custom content"""
        try:
            slides_data = content.get('slides', [])
            
            if references:
                for slide in slides_data:
                    if slide.get('layout') == 'references':
                        slide['references'] = references
                        break
                else:
                    slides_data.append({
                        'title': 'Adabiyotlar' if language == 'uz' else ('Литература' if language == 'ru' else 'References'),
                        'content': '',
                        'layout': 'references',
                        'references': references
                    })
            
            if plan_items:
                for slide in slides_data:
                    if slide.get('layout') == 'plan':
                        slide['plan_items'] = plan_items
                        break
            
            new_content = {'slides': slides_data}
            return await self.create_presentation_with_smart_images(topic, new_content, author_name, language, template_service, template_id)
            
        except Exception as e:
            logger.error(f"Error creating presentation with template background: {e}")
            raise

    async def create_new_presentation_system(
        self, 
        topic: str, 
        content: Dict, 
        author_name: str, 
        language: str
    ) -> str:
        """Create presentation using new layout system"""
        return await self.create_presentation_with_smart_images(topic, content, author_name, language)
