import os
import logging
from datetime import datetime
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from pptx import Presentation
from pptx.util import Inches as PptxInches, Pt as PptxPt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from typing import Dict, Optional, List
import asyncio
import aiohttp
from config import DOCUMENTS_DIR, TEMP_DIR, PEXELS_API_KEY
from bot.services.pexels import PexelsService

logger = logging.getLogger(__name__)

class DocumentService:
    def __init__(self):
        self.documents_dir = DOCUMENTS_DIR
        self.temp_dir = TEMP_DIR
        self.pexels = PexelsService(PEXELS_API_KEY) if PEXELS_API_KEY else None

    async def create_presentation_with_smart_images(self, topic: str, content: Dict, author_name: str) -> str:
        """Create PowerPoint presentation with AI-generated smart images from Pexels"""
        try:
            # First, get smart images for the presentation
            images = await self._get_smart_images_for_presentation(topic, content)
            
            # Then create presentation with images
            return await self.create_presentation(topic, content, images, author_name)
        
        except Exception as e:
            logger.error(f"Error creating presentation with smart images: {e}")
            # Fallback to creating presentation without images
            return await self.create_presentation(topic, content, {}, author_name)
    
    async def create_presentation(self, topic: str, content: Dict, images: Dict, author_name: str) -> str:
        """Create PowerPoint presentation"""
        try:
            prs = Presentation()

            # Set slide size (16:9)
            prs.slide_width = PptxInches(13.33)
            prs.slide_height = PptxInches(7.5)

            slides_data = content.get('slides', [])

            for idx, slide_data in enumerate(slides_data):
                slide_num = idx + 1

                if slide_num == 1:
                    # Title slide
                    slide_layout = prs.slide_layouts[0]  # Title slide layout
                    slide = prs.slides.add_slide(slide_layout)

                    title = slide.shapes.title
                    subtitle = slide.placeholders[1]

                    title.text = "Taqdimot"
                    title.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
                    # Reduce title font size
                    title.text_frame.paragraphs[0].font.size = PptxPt(36)


                    subtitle.text = f"{topic}\n\n\n{author_name or '__________________'}"
                    subtitle.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
                    # Reduce subtitle font size
                    subtitle.text_frame.paragraphs[0].font.size = PptxPt(20)


                elif slide_num in images:
                    # Slide with image (left side) and text (right side)
                    slide_layout = prs.slide_layouts[6]  # Blank layout
                    slide = prs.slides.add_slide(slide_layout)

                    # Add title
                    title_box = slide.shapes.add_textbox(
                        PptxInches(0.5), PptxInches(0.5),
                        PptxInches(12), PptxInches(1)
                    )
                    title_frame = title_box.text_frame
                    title_para = title_frame.paragraphs[0]
                    title_para.text = slide_data['title']
                    title_para.font.size = PptxPt(24)
                    title_para.font.bold = True
                    title_para.alignment = PP_ALIGN.CENTER

                    # Download and add image (left side)
                    image_url = images[slide_num]
                    if image_url:
                        image_path = await self._download_image(image_url, f"slide_{slide_num}.jpg")
                        if image_path:
                            try:
                                slide.shapes.add_picture(
                                    image_path,
                                    PptxInches(0.5), PptxInches(2),
                                    PptxInches(5.5), PptxInches(4)
                                )
                            except Exception as e:
                                logger.error(f"Error adding image to slide: {e}")

                    # Add text content (right side)
                    text_box = slide.shapes.add_textbox(
                        PptxInches(6.5), PptxInches(2),
                        PptxInches(6), PptxInches(4.5)
                    )
                    text_frame = text_box.text_frame
                    text_frame.word_wrap = True
                    text_para = text_frame.paragraphs[0]
                    text_para.text = slide_data['content']
                    text_para.font.size = PptxPt(14)
                    text_para.alignment = PP_ALIGN.LEFT

                else:
                    # Regular text slide
                    slide_layout = prs.slide_layouts[1]  # Title and content layout
                    slide = prs.slides.add_slide(slide_layout)

                    title = slide.shapes.title
                    content_placeholder = slide.placeholders[1]

                    title.text = slide_data['title']
                    # Make slide titles slightly smaller than the default
                    title.text_frame.paragraphs[0].font.size = PptxPt(20)
                    title.text_frame.paragraphs[0].font.bold = True
                    title.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

                    content_placeholder.text = slide_data['content']

                    # Format content
                    content_frame = content_placeholder.text_frame
                    content_frame.paragraphs[0].font.size = PptxPt(16)
                    content_frame.paragraphs[0].alignment = PP_ALIGN.LEFT

            # Save presentation
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"presentation_{timestamp}.pptx"
            file_path = os.path.join(self.documents_dir, filename)

            prs.save(file_path)
            logger.info(f"Presentation saved: {file_path}")

            return file_path

        except Exception as e:
            logger.error(f"Error creating presentation: {e}")
            raise

    async def create_independent_work(self, topic: str, content: Dict) -> str:
        """Create independent work document"""
        try:
            doc = Document()

            # Set document style
            style = doc.styles['Normal']
            font = style.font
            font.name = 'Times New Roman'
            font.size = Pt(12)

            # Title page
            title_para = doc.add_paragraph()
            title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title_run = title_para.add_run("MUSTAQIL ISH")
            title_run.font.size = Pt(16)
            title_run.font.bold = True

            doc.add_paragraph()  # Empty line

            topic_para = doc.add_paragraph()
            topic_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            topic_run = topic_para.add_run(topic)
            topic_run.font.size = Pt(14)
            topic_run.font.bold = True

            # Add page break
            doc.add_page_break()

            # Table of contents
            toc_para = doc.add_paragraph()
            toc_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            toc_run = toc_para.add_run("REJA")
            toc_run.font.size = Pt(14)
            toc_run.font.bold = True

            doc.add_paragraph()  # Empty line

            # Add sections to TOC
            sections = content.get('sections', [])
            for idx, section in enumerate(sections, 1):
                toc_item = doc.add_paragraph()
                toc_item.paragraph_format.first_line_indent = Inches(0.5)
                toc_item.add_run(f"{idx}. {section['title']}")

            # Add page break
            doc.add_page_break()

            # Add sections content
            for idx, section in enumerate(sections, 1):
                # Section title
                section_title = doc.add_paragraph()
                section_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
                section_title_run = section_title.add_run(f"{idx}. {section['title']}")
                section_title_run.font.bold = True
                section_title_run.font.size = Pt(14)

                doc.add_paragraph()  # Empty line

                # Section content
                content_para = doc.add_paragraph(section['content'])
                content_para.paragraph_format.first_line_indent = Inches(0.5)
                content_para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY  # Justify alignment

                doc.add_paragraph()  # Empty line

            # References
            if content.get('references'):
                doc.add_page_break()

                ref_title = doc.add_paragraph()
                ref_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
                ref_title_run = ref_title.add_run("FOYDALANILGAN ADABIYOTLAR")
                ref_title_run.font.bold = True
                ref_title_run.font.size = Pt(14)

                doc.add_paragraph()  # Empty line

                for idx, ref in enumerate(content['references'], 1):
                    ref_para = doc.add_paragraph()
                    ref_para.paragraph_format.first_line_indent = Inches(0.5)
                    ref_para.add_run(f"{idx}. {ref}")

            # Save document
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

            # Set document style
            style = doc.styles['Normal']
            font = style.font
            font.name = 'Times New Roman'
            font.size = Pt(12)

            # Title page
            title_para = doc.add_paragraph()
            title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title_run = title_para.add_run("REFERAT")
            title_run.font.size = Pt(16)
            title_run.font.bold = True

            doc.add_paragraph()  # Empty line

            topic_para = doc.add_paragraph()
            topic_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            topic_run = topic_para.add_run(topic)
            topic_run.font.size = Pt(14)
            topic_run.font.bold = True

            # Add page break
            doc.add_page_break()

            # Table of contents
            toc_para = doc.add_paragraph()
            toc_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            toc_run = toc_para.add_run("REJA")
            toc_run.font.size = Pt(14)
            toc_run.font.bold = True

            doc.add_paragraph()  # Empty line

            # Add sections to TOC
            sections = content.get('sections', [])
            for idx, section in enumerate(sections, 1):
                toc_item = doc.add_paragraph()
                toc_item.paragraph_format.first_line_indent = Inches(0.5)
                toc_item.add_run(f"{idx}. {section['title']}")

            # Add page break
            doc.add_page_break()

            # Add sections content
            for idx, section in enumerate(sections, 1):
                # Section title
                section_title = doc.add_paragraph()
                section_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
                section_title_run = section_title.add_run(f"{idx}. {section['title']}")
                section_title_run.font.bold = True
                section_title_run.font.size = Pt(14)

                doc.add_paragraph()  # Empty line

                # Section content
                content_para = doc.add_paragraph(section['content'])
                content_para.paragraph_format.first_line_indent = Inches(0.5)
                content_para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY  # Justify alignment

                doc.add_paragraph()  # Empty line

            # References
            if content.get('references'):
                doc.add_page_break()

                ref_title = doc.add_paragraph()
                ref_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
                ref_title_run = ref_title.add_run("FOYDALANILGAN ADABIYOTLAR")
                ref_title_run.font.bold = True
                ref_title_run.font.size = Pt(14)

                doc.add_paragraph()  # Empty line

                for idx, ref in enumerate(content['references'], 1):
                    ref_para = doc.add_paragraph()
                    ref_para.paragraph_format.first_line_indent = Inches(0.5)
                    ref_para.add_run(f"{idx}. {ref}")

            # Save document
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"referat_{timestamp}.docx"
            file_path = os.path.join(self.documents_dir, filename)

            doc.save(file_path)
            logger.info(f"Referat saved: {file_path}")

            return file_path

        except Exception as e:
            logger.error(f"Error creating referat: {e}")
            raise

    async def _download_image(self, image_url: str, filename: str) -> Optional[str]:
        """Download image from URL for presentation"""
        try:
            file_path = os.path.join(self.temp_dir, filename)

            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        with open(file_path, 'wb') as f:
                            f.write(await response.read())
                        return file_path
                    else:
                        logger.error(f"Failed to download image: HTTP {response.status}")
                        return None

        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None