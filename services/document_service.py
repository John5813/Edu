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

                    if title:
                        title.text = "Taqdimot"
                        title.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
                        # Reduce title font size
                        title.text_frame.paragraphs[0].font.size = PptxPt(36)

                    if subtitle:
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

                    if title:
                        title.text = slide_data['title']
                        # Make slide titles slightly smaller than the default
                        title.text_frame.paragraphs[0].font.size = PptxPt(20)
                        title.text_frame.paragraphs[0].font.bold = True
                        title.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

                    if content_placeholder:
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

    async def _get_smart_images_for_presentation(self, topic: str, content: Dict) -> Dict[int, str]:
        """Get smart images for presentation slides using Pexels API"""
        if not self.pexels:
            logger.warning("Pexels API not configured, skipping images")
            return {}
        
        try:
            slides_data = content.get('slides', [])
            slide_topics = []
            
            # Extract topics from slides for image search
            for idx, slide in enumerate(slides_data):
                if idx == 0:  # Skip title slide
                    continue
                    
                # Use slide title and extract key words for better search
                slide_title = slide.get('title', '')
                slide_content = slide.get('content', '')
                
                # Create search query from title and key content words
                search_query = self._extract_search_keywords(slide_title, slide_content, topic)
                slide_topics.append(search_query)
            
            # Get images for each slide topic
            images_dict = {}
            for idx, search_query in enumerate(slide_topics):
                slide_num = idx + 2  # Start from slide 2 (skip title slide)
                
                if search_query:
                    # Search for images
                    photos = await self.pexels.search_images(search_query, per_page=1)
                    
                    if photos:
                        photo = photos[0]
                        image_url = self.pexels.get_image_url(photo, "medium")
                        
                        # Download image
                        filename = f"slide_{slide_num}.jpg"
                        image_path = await self.pexels.download_image(image_url, filename)
                        
                        if image_path:
                            images_dict[slide_num] = image_path
                            logger.info(f"Added smart image for slide {slide_num}: {search_query}")
                    
                    # Small delay to respect rate limits
                    await asyncio.sleep(0.2)
            
            return images_dict
            
        except Exception as e:
            logger.error(f"Error getting smart images: {e}")
            return {}

    def _extract_search_keywords(self, title: str, content: str, main_topic: str) -> str:
        """Extract search keywords from slide content for better image matching"""
        # Combine title and main topic for search
        search_terms = []
        
        if title:
            # Remove common words and extract meaningful terms
            title_words = title.lower().split()
            meaningful_words = [word for word in title_words 
                              if len(word) > 3 and word not in ['uchun', 'haqida', 'asosida', 'davom']]
            search_terms.extend(meaningful_words[:2])  # Take first 2 meaningful words
        
        # Add main topic
        if main_topic:
            topic_words = main_topic.lower().split()[:2]  # First 2 words of main topic
            search_terms.extend(topic_words)
        
        # Create search query (prefer English terms for better Pexels results)
        search_query = ' '.join(search_terms[:3])  # Max 3 terms for focused search
        
        # Translate common Uzbek/Russian terms to English for better results
        translations = {
            'ta\'lim': 'education',
            'texnologiya': 'technology', 
            'kompyuter': 'computer',
            'internet': 'internet',
            'dasturlash': 'programming',
            'ishbilarmonlik': 'business',
            'sport': 'sports',
            'tibbiyot': 'medicine',
            'iqtisod': 'economics',
            'san\'at': 'art',
            'tarix': 'history',
            'geografiya': 'geography',
            'kimyo': 'chemistry',
            'fizika': 'physics',
            'matematika': 'mathematics'
        }
        
        for uz_term, eng_term in translations.items():
            if uz_term in search_query.lower():
                search_query = search_query.lower().replace(uz_term, eng_term)
        
        return search_query or main_topic  # Fallback to main topic