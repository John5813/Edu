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
        """Create PowerPoint presentation with 3 layout system and smart images"""
        try:
            # Validate content structure
            if not content or 'slides' not in content:
                logger.error(f"Invalid content structure: {content}")
                raise ValueError("Content must contain 'slides' key")
            
            # Create presentation with 3-template rotating system
            return await self.create_presentation_with_layouts(topic, content, author_name)

        except Exception as e:
            logger.error(f"Error creating presentation with smart images: {e}")
            # Final fallback
            return await self.create_presentation(topic, content, {}, author_name)

    async def create_presentation_from_template(self, topic: str, content: Dict, author_name: str, template_path: str) -> str:
        """Create presentation using existing template and replacing content"""
        try:
            # Load template
            prs = Presentation(template_path)
            slides_data = content.get('slides', [])

            # Get images for slides before processing
            slide_images = await self._get_template_images(topic, slides_data)

            # Process each slide
            for slide_idx, slide in enumerate(prs.slides):
                if slide_idx == 0:
                    # Title slide - update with topic and author
                    self._update_title_slide(slide, topic, author_name)
                elif slide_idx - 1 < len(slides_data):
                    # Content slides
                    slide_data = slides_data[slide_idx - 1]
                    await self._update_content_slide(slide, slide_data, slide_idx, slide_images)

            # Remove extra slides if template has more slides than needed
            while len(prs.slides) > len(slides_data) + 1:  # +1 for title slide
                rId = prs.slides._sldIdLst[-1].rId
                prs.part.drop_rel(rId)
                del prs.slides._sldIdLst[-1]

            # Add more slides if needed
            for i in range(len(prs.slides) - 1, len(slides_data)):
                slide_data = slides_data[i]
                new_slide = self._add_content_slide(prs, slide_data, i + 1, slide_images)

            # Save presentation
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"presentation_{timestamp}.pptx"
            file_path = os.path.join(self.documents_dir, filename)

            prs.save(file_path)
            logger.info(f"Template-based presentation saved: {file_path}")

            return file_path

        except Exception as e:
            logger.error(f"Error creating presentation from template: {e}")
            # Fallback to regular creation
            images = await self._get_smart_images_for_presentation(topic, content)
            return await self.create_presentation(topic, content, images, author_name)

    def _update_title_slide(self, slide, topic: str, author_name: str):
        """Update title slide with topic and author"""
        try:
            for shape in slide.shapes:
                if hasattr(shape, "text_frame") and shape.text_frame:
                    # Check if this might be title or subtitle
                    if shape.top < PptxInches(3):  # Likely title
                        shape.text_frame.clear()
                        p = shape.text_frame.paragraphs[0]
                        p.text = topic
                        p.alignment = PP_ALIGN.CENTER
                        if p.runs:
                            p.runs[0].font.bold = True
                            p.runs[0].font.size = PptxPt(36)
                    elif shape.top > PptxInches(3):  # Likely subtitle area
                        shape.text_frame.clear()
                        p = shape.text_frame.paragraphs[0]
                        default_author = "Noma'lum"
                        p.text = f"Muallif: {author_name or default_author}"
                        p.alignment = PP_ALIGN.CENTER
                        if p.runs:
                            p.runs[0].font.size = PptxPt(20)
        except Exception as e:
            logger.error(f"Error updating title slide: {e}")

    async def _update_content_slide(self, slide, slide_data: Dict, slide_num: int, slide_images: Dict):
        """Update content slide with new text and images"""
        try:
            # Update text content
            for shape in slide.shapes:
                if hasattr(shape, "text_frame") and shape.text_frame:
                    # Determine if this is title or content based on position
                    if shape.top < PptxInches(2):  # Likely title
                        shape.text_frame.clear()
                        p = shape.text_frame.paragraphs[0]
                        p.text = slide_data.get('title', f"Slayd {slide_num}")
                        p.alignment = PP_ALIGN.CENTER
                        if p.runs:
                            p.runs[0].font.bold = True
                            p.runs[0].font.size = PptxPt(24)
                    elif shape.top > PptxInches(2):  # Content area
                        shape.text_frame.clear()
                        p = shape.text_frame.paragraphs[0]
                        p.text = slide_data.get('content', '')
                        p.alignment = PP_ALIGN.LEFT
                        if p.runs:
                            p.runs[0].font.size = PptxPt(16)

            # Add or replace images
            if slide_num in slide_images:
                await self._add_image_to_slide(slide, slide_images[slide_num])

        except Exception as e:
            logger.error(f"Error updating content slide {slide_num}: {e}")

    def _add_content_slide(self, prs, slide_data: Dict, slide_num: int, slide_images: Dict):
        """Add new content slide to presentation"""
        try:
            # Use layout 1 (title and content)
            slide_layout = prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0]
            slide = prs.slides.add_slide(slide_layout)

            # Add title
            if slide.shapes.title:
                slide.shapes.title.text = slide_data.get('title', f"Slayd {slide_num}")
                slide.shapes.title.text_frame.paragraphs[0].font.size = PptxPt(24)
                slide.shapes.title.text_frame.paragraphs[0].font.bold = True
                slide.shapes.title.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

            # Add content
            if len(slide.placeholders) > 1:
                content_placeholder = slide.placeholders[1]
                content_placeholder.text = slide_data.get('content', '')
                content_placeholder.text_frame.paragraphs[0].font.size = PptxPt(16)

            # Add image if available
            if slide_num in slide_images:
                asyncio.create_task(self._add_image_to_slide(slide, slide_images[slide_num]))

            return slide

        except Exception as e:
            logger.error(f"Error adding content slide: {e}")
            return None

    async def _add_image_to_slide(self, slide, image_path: str):
        """Add image to slide, replacing existing image or adding new one"""
        try:
            if not image_path or not os.path.exists(image_path):
                return

            # Try to find existing image placeholder or shape
            image_added = False

            for shape in slide.shapes:
                # Check if this is an image placeholder or existing image
                if hasattr(shape, 'image') or (hasattr(shape, 'shape_type') and shape.shape_type == 13):  # MSO_SHAPE_TYPE.PICTURE
                    try:
                        # Remove existing image
                        sp = shape._element
                        sp.getparent().remove(sp)

                        # Add new image in same position
                        slide.shapes.add_picture(
                            image_path,
                            shape.left, shape.top,
                            shape.width, shape.height
                        )
                        image_added = True
                        break
                    except:
                        continue

            # If no existing image found, add new one
            if not image_added:
                # Add image to right side of slide
                slide.shapes.add_picture(
                    image_path,
                    PptxInches(6.5), PptxInches(2),
                    PptxInches(5.5), PptxInches(4)
                )

        except Exception as e:
            logger.error(f"Error adding image to slide: {e}")

    async def _get_template_images(self, topic: str, slides_data: List[Dict]) -> Dict[int, str]:
        """Get images for template slides"""
        if not self.pexels:
            logger.warning("Pexels API not configured, skipping images")
            return {}

        try:
            slide_images = {}

            for idx, slide_data in enumerate(slides_data):
                slide_num = idx + 1

                # Extract keywords for image search
                slide_title = slide_data.get('title', '')
                slide_content = slide_data.get('content', '')

                # Get search keywords
                search_query = self._extract_search_keywords(slide_title, slide_content, topic)

                if search_query:
                    # Search for images
                    photos = await self.pexels.search_images(search_query, per_page=1)

                    if photos:
                        photo = photos[0]
                        image_url = self.pexels.get_image_url(photo, "medium")

                        # Download image
                        filename = f"template_slide_{slide_num}.jpg"
                        image_path = await self.pexels.download_image(image_url, filename)

                        if image_path:
                            slide_images[slide_num] = image_path
                            logger.info(f"Downloaded template image for slide {slide_num}: {search_query}")

                    # Small delay to respect rate limits
                    await asyncio.sleep(0.3)

            return slide_images

        except Exception as e:
            logger.error(f"Error getting template images: {e}")
            return {}

    def _extract_search_keywords(self, title: str, content: str, main_topic: str) -> str:
        """Extract search keywords from slide content for better image matching"""
        # Combine title and main topic for search
        search_terms = []

        if title:
            # Remove common words and extract meaningful terms
            title_words = title.lower().split()
            meaningful_words = [word for word in title_words 
                              if len(word) > 3 and word not in ['uchun', 'haqida', 'asosida', 'davom', 'bilan', 'ning', 'dan']]
            search_terms.extend(meaningful_words[:2])  # Take first 2 meaningful words

        # Add main topic words
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
            'ekonomika': 'economics',
            'san\'at': 'art',
            'tarix': 'history',
            'geografiya': 'geography',
            'kimyo': 'chemistry',
            'fizika': 'physics',
            'matematika': 'mathematics',
            'fan': 'science',
            'ilm': 'science',
            'tadqiqot': 'research',
            'taraqqiyot': 'development',
            'innovatsiya': 'innovation',
            'zamonaviy': 'modern'
        }

        for uz_term, eng_term in translations.items():
            if uz_term in search_query.lower():
                search_query = search_query.lower().replace(uz_term, eng_term)

        return search_query or main_topic  # Fallback to main topic
    
    async def _create_title_slide(self, prs, topic: str, author_name: str):
        """Create title slide"""
        slide_layout = prs.slide_layouts[0]  # Title slide layout
        slide = prs.slides.add_slide(slide_layout)

        title = slide.shapes.title
        subtitle = slide.placeholders[1]

        if title:
            title.text = "Taqdimot"
            title.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
            title.text_frame.paragraphs[0].font.size = PptxPt(36)

        if subtitle:
            subtitle.text = f"{topic}\n\n\n{author_name or '__________________'}"
            subtitle.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
            subtitle.text_frame.paragraphs[0].font.size = PptxPt(20)

    async def _create_content_slide_by_layout(self, prs, slide_data: Dict, layout_type: str, slide_num: int, images: Dict):
        """Create content slide based on layout type"""
        logger.info(f"Creating slide {slide_num} with layout '{layout_type}', title: '{slide_data.get('title', 'NO TITLE')}', content: '{slide_data.get('content', 'NO CONTENT')[:50]}...'")
        
        if layout_type == "text_only":
            await self._create_text_only_slide(prs, slide_data)
        elif layout_type == "text_with_image":
            await self._create_text_with_image_slide(prs, slide_data, slide_num, images)
        elif layout_type == "three_column":
            await self._create_three_column_slide(prs, slide_data)
        else:
            logger.error(f"Unknown layout type: {layout_type}, using text_only fallback")
            await self._create_text_only_slide(prs, slide_data)

    async def _create_text_only_slide(self, prs, slide_data: Dict):
        """Create SHABLON 1: Text only slide"""
        slide_layout = prs.slide_layouts[1]  # Title and content layout
        slide = prs.slides.add_slide(slide_layout)

        title = slide.shapes.title
        content_placeholder = slide.placeholders[1]

        if title:
            title.text = slide_data.get('title', 'Mavzu')
            title.text_frame.paragraphs[0].font.size = PptxPt(24)
            title.text_frame.paragraphs[0].font.bold = True
            title.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

        if content_placeholder:
            content_placeholder.text = slide_data.get('content', 'Mazmun mavjud emas')
            content_frame = content_placeholder.text_frame
            content_frame.paragraphs[0].font.size = PptxPt(16)
            content_frame.paragraphs[0].alignment = PP_ALIGN.LEFT

    async def _create_text_with_image_slide(self, prs, slide_data: Dict, slide_num: int, images: Dict):
        """Create SHABLON 2: Text + Image slide"""
        slide_layout = prs.slide_layouts[6]  # Blank layout
        slide = prs.slides.add_slide(slide_layout)

        # Add title
        title_box = slide.shapes.add_textbox(
            PptxInches(0.5), PptxInches(0.5),
            PptxInches(12), PptxInches(1)
        )
        title_frame = title_box.text_frame
        title_para = title_frame.paragraphs[0]
        title_para.text = slide_data.get('title', 'Mavzu')
        title_para.font.size = PptxPt(24)
        title_para.font.bold = True
        title_para.alignment = PP_ALIGN.CENTER

        # Add image (left side) if available
        if slide_num in images:
            image_path = images[slide_num]
            logger.info(f"Trying to add image for slide {slide_num}: {image_path}")
            if image_path and os.path.exists(image_path):
                try:
                    slide.shapes.add_picture(
                        image_path,
                        PptxInches(0.5), PptxInches(2),
                        PptxInches(5.5), PptxInches(4)
                    )
                    logger.info(f"Successfully added image to slide {slide_num}")
                except Exception as e:
                    logger.error(f"Error adding image to slide {slide_num}: {e}")
            else:
                logger.warning(f"Image not found for slide {slide_num}: {image_path}")
        else:
            logger.info(f"No image available for slide {slide_num}")

        # Add text content (right side)
        text_box = slide.shapes.add_textbox(
            PptxInches(6.5), PptxInches(2),
            PptxInches(6), PptxInches(4.5)
        )
        text_frame = text_box.text_frame
        text_frame.word_wrap = True
        text_para = text_frame.paragraphs[0]
        text_para.text = slide_data.get('content', 'Mazmun mavjud emas')
        text_para.font.size = PptxPt(14)
        text_para.alignment = PP_ALIGN.LEFT

    async def _create_three_column_slide(self, prs, slide_data: Dict):
        """Create SHABLON 3: Three column slide"""
        logger.info(f"Creating three-column slide with data: {slide_data}")
        
        slide_layout = prs.slide_layouts[6]  # Blank layout
        slide = prs.slides.add_slide(slide_layout)

        # Add title
        title_box = slide.shapes.add_textbox(
            PptxInches(0.5), PptxInches(0.5),
            PptxInches(12), PptxInches(1)
        )
        title_frame = title_box.text_frame
        title_para = title_frame.paragraphs[0]
        title_para.text = slide_data.get('title', 'Uch Ustunli Slayd')
        title_para.font.size = PptxPt(24)
        title_para.font.bold = True
        title_para.alignment = PP_ALIGN.CENTER

        # Get content and split into 3 columns
        content_text = slide_data.get('content', '')
        logger.info(f"Content for 3-column: '{content_text[:100]}...'")
        
        if not content_text or content_text.strip() == 'Mazmun mavjud emas':
            # Create fallback content
            columns = [
                {'title': 'Birinchi Ustun', 'points': ['Asosiy ma\'lumot', 'Muhim nuqtalar']},
                {'title': 'Ikkinchi Ustun', 'points': ['Qo\'shimcha ma\'lumot', 'Tafsilotlar']},
                {'title': 'Uchinchi Ustun', 'points': ['Xulosa', 'Natijalar']}
            ]
        else:
            # Split content intelligently into 3 columns
            sentences = [s.strip() for s in content_text.replace('•', '').split('.') if s.strip()]
            
            if len(sentences) >= 3:
                # Distribute sentences across columns
                per_column = max(1, len(sentences) // 3)
                columns = []
                for i in range(3):
                    start_idx = i * per_column
                    end_idx = (i + 1) * per_column if i < 2 else len(sentences)
                    column_sentences = sentences[start_idx:end_idx]
                    
                    columns.append({
                        'title': f'Qism {i+1}',
                        'points': column_sentences[:3]  # Max 3 points per column
                    })
            else:
                # Split by lines or create word-based columns
                lines = [line.strip() for line in content_text.split('\n') if line.strip()]
                if len(lines) >= 3:
                    columns = [
                        {'title': f'Nuqta {i+1}', 'points': [lines[i]]} 
                        for i in range(min(3, len(lines)))
                    ]
                else:
                    # Word-based split for very short content
                    words = content_text.split()
                    if len(words) > 9:
                        third = len(words) // 3
                        columns = [
                            {'title': f'Bo\'lim {i+1}', 'points': [' '.join(words[i*third:(i+1)*third]) if i < 2 else ' '.join(words[i*third:])]}
                            for i in range(3)
                        ]
                    else:
                        # Very short content - just distribute words
                        columns = [
                            {'title': 'Boshi', 'points': [' '.join(words[:len(words)//3])]},
                            {'title': 'O\'rtasi', 'points': [' '.join(words[len(words)//3:2*len(words)//3])]},
                            {'title': 'Oxiri', 'points': [' '.join(words[2*len(words)//3:])]}
                        ]

        # Create 3 columns
        column_width = PptxInches(3.8)
        column_height = PptxInches(4.5)
        start_x = PptxInches(0.5)
        start_y = PptxInches(2)

        for i, column in enumerate(columns[:3]):
            # Calculate position
            x_pos = start_x + i * PptxInches(4.2)
            
            # Add column textbox
            col_box = slide.shapes.add_textbox(x_pos, start_y, column_width, column_height)
            col_frame = col_box.text_frame
            col_frame.word_wrap = True
            
            # Column title
            col_para = col_frame.paragraphs[0]
            col_para.text = column.get('title', f'Ustun {i+1}')
            col_para.font.size = PptxPt(18)
            col_para.font.bold = True
            col_para.alignment = PP_ALIGN.CENTER
            
            # Column points
            points = column.get('points', [])
            logger.info(f"Column {i+1} points: {points}")
            
            for point in points[:3]:  # Max 3 points per column
                if point and point.strip():
                    p = col_frame.add_paragraph()
                    p.text = f"• {point.strip()}"
                    p.font.size = PptxPt(12)
                    p.alignment = PP_ALIGN.LEFT

    async def _get_smart_images_for_layouts(self, topic: str, content: Dict) -> Dict[int, str]:
        """Get smart images only for 'text_with_image' layout slides"""
        if not self.pexels:
            logger.warning("Pexels API not configured, skipping images")
            return {}
        
        try:
            slides_data = content.get('slides', [])
            images_dict = {}
            
            for idx, slide_data in enumerate(slides_data):
                slide_num = idx + 2  # Start from slide 2 (skip title slide)
                
                # Only get images for 'text_with_image' layout (every 3rd slide starting from 2nd content slide)
                layout_type = self._get_layout_type(idx + 1)
                
                if layout_type == "text_with_image":
                    slide_title = slide_data.get('title', '')
                    slide_content = slide_data.get('content', '')
                    
                    # Create search query
                    search_query = self._extract_search_keywords(slide_title, slide_content, topic)
                    
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
            logger.error(f"Error getting smart images for layouts: {e}")
            return {}

    async def create_presentation_with_layouts(self, topic: str, content: Dict, author_name: str) -> str:
        """Create presentation with 3 rotating layout system"""
        try:
            # Validate content
            if not content or 'slides' not in content:
                logger.error(f"Invalid content for layouts: {content}")
                raise ValueError("Content must contain 'slides' key")
            
            prs = Presentation()
            
            # Set slide size (16:9)
            prs.slide_width = PptxInches(13.33)
            prs.slide_height = PptxInches(7.5)
            
            slides_data = content.get('slides', [])
            
            # Get smart images for layout 2 slides (text + image)
            images = await self._get_smart_images_for_layouts(topic, content)
            
            for idx, slide_data in enumerate(slides_data):
                slide_num = idx + 1
                
                if slide_num == 1:
                    # Title slide
                    await self._create_title_slide(prs, topic, author_name)
                else:
                    # Content slides with rotating layouts
                    layout_type = self._get_layout_type(slide_num - 1)  # -1 because we skip title slide
                    await self._create_content_slide_by_layout(prs, slide_data, layout_type, slide_num, images)
            
            # Save presentation
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"presentation_{timestamp}.pptx"
            file_path = os.path.join(self.documents_dir, filename)
            
            prs.save(file_path)
            logger.info(f"3-layout presentation saved: {file_path}")
            
            return file_path
            
        except Exception as e:
            logger.error(f"Error creating presentation with layouts: {e}")
            raise
    
    def _get_layout_type(self, content_slide_num: int) -> str:
        """Get layout type based on slide number (1->2->3->1->2->3...)"""
        layout_cycle = ["text_only", "text_with_image", "three_column"]
        return layout_cycle[(content_slide_num - 1) % 3]
    
    async def create_presentation(self, topic: str, content: Dict, images: Dict, author_name: str) -> str:
        """Create PowerPoint presentation (fallback method)"""
        try:
            # Validate content and create fallback if needed
            if not content or 'slides' not in content:
                logger.warning(f"Invalid content, creating fallback presentation: {content}")
                content = {
                    'slides': [
                        {
                            'title': topic,
                            'content': f"Bu taqdimot {topic} mavzusida tayyorlangan."
                        }
                    ]
                }
            
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
                        title.text = topic
                        title.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
                        title.text_frame.paragraphs[0].font.size = PptxPt(36)

                    if subtitle:
                        default_author = "Noma'lum"
                        subtitle.text = f"Muallif: {author_name or default_author}"
                        subtitle.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
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
                    title_para.text = slide_data.get('title', 'Mavzu')
                    title_para.font.size = PptxPt(24)
                    title_para.font.bold = True
                    title_para.alignment = PP_ALIGN.CENTER

                    # Add image (left side)
                    image_path = images[slide_num]
                    if image_path and os.path.exists(image_path):
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
                    text_para.text = slide_data.get('content', 'Mazmun mavjud emas')
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
                        title.text_frame.paragraphs[0].font.size = PptxPt(20)
                        title.text_frame.paragraphs[0].font.bold = True
                        title.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

                    if content_placeholder:
                        content_placeholder.text = slide_data['content']
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

            # Create custom title page with template design (language-specific)
            user_lang = content.get('language', 'uzbek')  # Default to uzbek
            await self._create_independent_work_title_page(doc, topic, user_lang)

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

            # Create custom title page with template design (language-specific)
            user_lang = content.get('language', 'uzbek')  # Default to uzbek
            await self._create_referat_title_page(doc, topic, user_lang)

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

    async def _create_referat_title_page(self, doc, topic: str, language: str = 'uzbek'):
        """Create referat title page with exact template design from user's image, language-specific"""
        try:
            # Language-specific texts
            texts = self._get_referat_template_texts(language)
            
            # Set paragraph formats for alignment and spacing
            
            # Top section with lines and "fanidan"
            # Long line
            para1 = doc.add_paragraph()
            para1.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run1 = para1.add_run("_" * 50)
            run1.font.size = Pt(12)
            run1.font.name = 'Times New Roman'
            
            # Short line with "fanidan"  
            para2 = doc.add_paragraph()  
            para2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run2 = para2.add_run("_" * 20 + f" {texts['from_subject']}")
            run2.font.size = Pt(12)
            run2.font.name = 'Times New Roman'
            
            # Add 6 empty lines for spacing
            for _ in range(6):
                doc.add_paragraph()
            
            # REFERAT title (large and bold)
            title_para = doc.add_paragraph()
            title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title_run = title_para.add_run(f"{texts['referat']}:")
            title_run.font.size = Pt(36)
            title_run.font.bold = True
            title_run.font.name = 'Times New Roman'
            
            # Add 5 empty lines for spacing
            for _ in range(5):
                doc.add_paragraph()
                
            # Topic title (underlined)
            topic_para = doc.add_paragraph()
            topic_para.alignment = WD_ALIGN_PARAGRAPH.CENTER  
            topic_run = topic_para.add_run(f"{texts['topic']}: ")
            topic_run.font.size = Pt(14)
            topic_run.font.name = 'Times New Roman'
            
            topic_line_run = topic_para.add_run("_" * 30)
            topic_line_run.font.size = Pt(14)
            topic_line_run.font.name = 'Times New Roman'
            
            # Add the actual topic below the line (on next paragraph)
            topic_name_para = doc.add_paragraph()
            topic_name_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            topic_name_run = topic_name_para.add_run(topic)
            topic_name_run.font.size = Pt(14)
            topic_name_run.font.name = 'Times New Roman'
            topic_name_run.font.italic = True
            
            # Add 2 empty lines
            for _ in range(2):
                doc.add_paragraph()
            
            # Bajardi section
            bajardi_para = doc.add_paragraph()
            bajardi_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            bajardi_run = bajardi_para.add_run(f"{texts['prepared_by']}: ")
            bajardi_run.font.size = Pt(12)
            bajardi_run.font.name = 'Times New Roman'
            
            kurs_run = bajardi_para.add_run(f"_____ {texts['course']}")
            kurs_run.font.size = Pt(12)
            kurs_run.font.name = 'Times New Roman'
            
            # Add new line within same paragraph
            bajardi_para.add_run("\n")
            
            guruh_run = bajardi_para.add_run(f"                                 {texts['group_student']}")
            guruh_run.font.size = Pt(12)
            guruh_run.font.name = 'Times New Roman'
            
            # Qabul qildi section with line
            qabul_para = doc.add_paragraph()
            qabul_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            qabul_run = qabul_para.add_run(f"{texts['accepted_by']}:")
            qabul_run.font.size = Pt(12)
            qabul_run.font.name = 'Times New Roman'
            
            qabul_line_run = qabul_para.add_run("_" * 20)
            qabul_line_run.font.size = Pt(12)
            qabul_line_run.font.name = 'Times New Roman'
            
            # Add 4 empty lines for spacing before Toshkent
            for _ in range(4):
                doc.add_paragraph()
            
            # City at bottom
            city_para = doc.add_paragraph()
            city_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            city_run = city_para.add_run(texts['city'])
            city_run.font.size = Pt(12)
            city_run.font.name = 'Times New Roman'
            
            logger.info("Referat title page created with template design")
            
        except Exception as e:
            logger.error(f"Error creating referat title page: {e}")
            # Fallback to simple title if template fails
            title_para = doc.add_paragraph()
            title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title_run = title_para.add_run("REFERAT")
            title_run.font.size = Pt(16)
            title_run.font.bold = True

    def _get_referat_template_texts(self, language: str) -> Dict[str, str]:
        """Get language-specific texts for referat template"""
        if language == 'russian':
            return {
                'from_subject': 'по предмету',
                'referat': 'РЕФЕРАТ',
                'topic': 'Тема',
                'prepared_by': 'Выполнил',
                'course': 'курс',
                'group_student': '(рус) группы студент',
                'accepted_by': 'Принял',
                'city': 'Ташкент'
            }
        elif language == 'english':
            return {
                'from_subject': 'on the subject',
                'referat': 'REPORT',
                'topic': 'Topic',
                'prepared_by': 'Prepared by',
                'course': 'course',
                'group_student': '(eng) group student',
                'accepted_by': 'Accepted by',
                'city': 'Tashkent'
            }
        else:  # uzbek (default)
            return {
                'from_subject': 'fanidan',
                'referat': 'REFERAT',
                'topic': 'Mavzu',
                'prepared_by': 'Bajardi',
                'course': 'kurs',
                'group_student': "(o'zb) guruhi talabasi",
                'accepted_by': 'Qabul qildi',
                'city': 'Toshkent'
            }

    async def _create_independent_work_title_page(self, doc, topic: str, language: str = 'uzbek'):
        """Create independent work title page with exact template design from user's image, language-specific"""
        try:
            # Language-specific texts
            texts = self._get_independent_work_template_texts(language)
            
            # Add border around the page (simulate with underlines and spacing)
            # Top border line
            border_para = doc.add_paragraph()
            border_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            border_run = border_para.add_run("_" * 80)
            border_run.font.size = Pt(12)
            border_run.font.name = 'Times New Roman'
            
            # Add some spacing
            for _ in range(2):
                doc.add_paragraph()
            
            # Faculty line - right aligned
            faculty_para = doc.add_paragraph()
            faculty_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            faculty_run = faculty_para.add_run("_" * 30 + f" {texts['faculty']}")
            faculty_run.font.size = Pt(12)
            faculty_run.font.name = 'Times New Roman'
            
            doc.add_paragraph()  # Empty line
            
            # Subject line - right aligned  
            subject_para = doc.add_paragraph()
            subject_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            subject_run = subject_para.add_run("_" * 30 + f" {texts['from_subject']}")
            subject_run.font.size = Pt(12)
            subject_run.font.name = 'Times New Roman'
            
            # Add 4 empty lines for spacing
            for _ in range(4):
                doc.add_paragraph()
            
            # MUSTAQIL ISH title (large and bold, centered)
            title_para = doc.add_paragraph()
            title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title_run = title_para.add_run(texts['independent_work'])
            title_run.font.size = Pt(32)
            title_run.font.bold = True
            title_run.font.name = 'Times New Roman'
            
            # Add 3 empty lines for spacing
            for _ in range(3):
                doc.add_paragraph()
                
            # Topic with underline (left aligned)
            topic_para = doc.add_paragraph()
            topic_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            topic_run = topic_para.add_run(f"{texts['topic']}:")
            topic_run.font.size = Pt(14)
            topic_run.font.name = 'Times New Roman'
            
            topic_line_run = topic_para.add_run("_" * 45)
            topic_line_run.font.size = Pt(14)
            topic_line_run.font.name = 'Times New Roman'
            
            # Add second line for topic continuation
            topic_cont_para = doc.add_paragraph()
            topic_cont_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            topic_cont_run = topic_cont_para.add_run("_" * 55)
            topic_cont_run.font.size = Pt(14)
            topic_cont_run.font.name = 'Times New Roman'
            
            # Add the actual topic below the lines (smaller font, left aligned)
            topic_name_para = doc.add_paragraph()
            topic_name_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            topic_name_run = topic_name_para.add_run(f'"{topic}"')
            topic_name_run.font.size = Pt(12)
            topic_name_run.font.name = 'Times New Roman'
            topic_name_run.font.italic = True
            
            # Add 5 empty lines
            for _ in range(5):
                doc.add_paragraph()
            
            # Bajardi section (left aligned)
            bajardi_para = doc.add_paragraph()
            bajardi_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            bajardi_run = bajardi_para.add_run(f"{texts['prepared_by']}. ")
            bajardi_run.font.size = Pt(12)
            bajardi_run.font.name = 'Times New Roman'
            
            bajardi_line_run = bajardi_para.add_run("_" * 20)
            bajardi_line_run.font.size = Pt(12)
            bajardi_line_run.font.name = 'Times New Roman'
            
            # Add new line
            doc.add_paragraph()
            
            # Qabul qildi section (left aligned)
            qabul_para = doc.add_paragraph()
            qabul_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            qabul_run = qabul_para.add_run(f"{texts['accepted_by']} ")
            qabul_run.font.size = Pt(12)
            qabul_run.font.name = 'Times New Roman'
            
            qabul_line_run = qabul_para.add_run("_" * 18)
            qabul_line_run.font.size = Pt(12)
            qabul_line_run.font.name = 'Times New Roman'
            
            # Add spacing before bottom border
            for _ in range(6):
                doc.add_paragraph()
            
            # Bottom border line
            bottom_border_para = doc.add_paragraph()
            bottom_border_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            bottom_border_run = bottom_border_para.add_run("_" * 80)
            bottom_border_run.font.size = Pt(12)
            bottom_border_run.font.name = 'Times New Roman'
            
            logger.info("Independent work title page created with template design")
            
        except Exception as e:
            logger.error(f"Error creating independent work title page: {e}")
            # Fallback to simple title if template fails
            title_para = doc.add_paragraph()
            title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title_run = title_para.add_run("MUSTAQIL ISH")
            title_run.font.size = Pt(16)
            title_run.font.bold = True

    def _get_independent_work_template_texts(self, language: str) -> Dict[str, str]:
        """Get language-specific texts for independent work template"""
        if language == 'russian':
            return {
                'faculty': 'факультети',
                'from_subject': 'по предмету',
                'independent_work': 'Самостоятельная работа',
                'topic': 'Тема',
                'prepared_by': 'Выполнил',
                'accepted_by': 'Принял'
            }
        elif language == 'english':
            return {
                'faculty': 'fakulteti',
                'from_subject': 'on the subject',
                'independent_work': 'Independent work',
                'topic': 'Topic',
                'prepared_by': 'Prepared by',
                'accepted_by': 'Accepted by'
            }
        else:  # uzbek (default)
            return {
                'faculty': 'fakulteti',
                'from_subject': 'fanidan',
                'independent_work': 'Mustaqil ish',
                'topic': 'Mavzu',
                'prepared_by': 'Bajardi',
                'accepted_by': 'Qabul qildi'
            }

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

            # Get images for each slide topic
            images_dict = {}
            for idx, slide in enumerate(slides_data):
                slide_num = idx + 1

                # Skip title slide
                if slide_num == 1:
                    continue

                # Use slide title and extract key words for better search
                slide_title = slide.get('title', '')
                slide_content = slide.get('content', '')

                # Create search query from title and key content words
                search_query = self._extract_search_keywords(slide_title, slide_content, topic)

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