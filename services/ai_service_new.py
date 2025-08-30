import asyncio
import logging
import random
import string
from datetime import datetime
from typing import Dict, List, Optional
import aiohttp
import os
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4o"

    async def generate_presentation_in_batches(self, topic: str, slide_count: int, language: str) -> Dict:
        """Generate presentation content using batch method for better results"""
        logger.info(f"Starting batch presentation generation for '{topic}' with {slide_count} slides in {language}")
        
        all_slides = []
        
        # Generate in batches of 3 slides
        for batch_start in range(1, slide_count + 1, 3):
            batch_end = min(batch_start + 2, slide_count)
            logger.info(f"Generating batch: slides {batch_start}-{batch_end}")
            
            batch_content = await self._generate_slide_batch(topic, batch_start, batch_end, slide_count, language)
            if batch_content and 'slides' in batch_content:
                all_slides.extend(batch_content['slides'])
            
            # Small delay between batches
            if batch_end < slide_count:
                await asyncio.sleep(0.5)

        logger.info(f"Generated complete presentation with {len(all_slides)} slides")
        return {"slides": all_slides}

    async def _generate_slide_batch(self, topic: str, start_slide: int, end_slide: int, total_slides: int, language: str) -> Dict:
        """Generate a batch of 3 slides with proper layout assignment"""
        
        # Create slide layout mapping for this batch
        slides_info = []
        for slide_num in range(start_slide, end_slide + 1):
            layout_type = self._get_layout_type(slide_num)
            slides_info.append({
                "slide_number": slide_num,
                "layout_type": layout_type
            })
        
        language_instructions = {
            'uzbek': "O'zbek tilida",
            'russian': "На русском языке", 
            'english': "In English"
        }
        
        lang_instruction = language_instructions.get(language, "O'zbek tilida")
        
        prompt = f"""
Generate content for slides {start_slide}-{end_slide} of {total_slides} for presentation about "{topic}". {lang_instruction}.

CRITICAL LAYOUT REQUIREMENTS:
{self._get_layout_descriptions(slides_info)}

For each slide, provide:
- slide_number: {start_slide} to {end_slide}
- title: Relevant slide title
- content: ALWAYS STRING TEXT (never array/list). Content according to layout type
- layout_type: One of [bullet_points, text_with_image, three_column, three_bullets, four_numbered]

CRITICAL: "content" must ALWAYS be a string, NEVER an array or list!

Return valid JSON with "slides" array.

Example format:
{{
  "slides": [
    {{
      "slide_number": {start_slide},
      "title": "Slide Title",
      "content": "Content according to layout...",
      "layout_type": "bullet_points"
    }}
  ]
}}
"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7
            )
            
            content_text = response.choices[0].message.content
            import json
            return json.loads(content_text)
            
        except Exception as e:
            logger.error(f"Error generating batch {start_slide}-{end_slide}: {e}")
            return {"slides": []}

    def _get_layout_type(self, slide_number: int) -> str:
        """Determine layout type based on slide number using rotating 4-layout system"""
        if slide_number == 1:
            return "title"
        
        # Calculate position in content slides (excluding title slide)
        content_position = slide_number - 1
        
        # 4-layout rotation: bullet_points, text_with_image, three_column, three_bullets
        layout_cycle = ["bullet_points", "text_with_image", "three_column", "three_bullets"]
        layout_index = (content_position - 1) % 4
        
        return layout_cycle[layout_index]

    def _get_layout_descriptions(self, slides_info: List[Dict]) -> str:
        """Get descriptions for each layout type"""
        descriptions = []
        
        for slide_info in slides_info:
            slide_num = slide_info["slide_number"]
            layout = slide_info["layout_type"]
            
            if layout == "bullet_points":
                descriptions.append(f"Slide {slide_num} (bullet_points): Generate as ONE CONTINUOUS STRING TEXT with 150-200 words explaining key concepts. NOT A LIST OR ARRAY!")
            elif layout == "text_with_image":
                descriptions.append(f"Slide {slide_num} (text_with_image): Generate as ONE CONTINUOUS STRING TEXT with 40-50 words for image generation. NOT A LIST OR ARRAY!")
            elif layout == "three_column":
                descriptions.append(f"Slide {slide_num} (three_column): Generate as ONE CONTINUOUS STRING TEXT with 120+ words, different aspects. NOT A LIST OR ARRAY!")
            elif layout == "three_bullets":
                descriptions.append(f"Slide {slide_num} (three_bullets): Generate as ONE CONTINUOUS STRING TEXT with 120+ words, comprehensive coverage. NOT A LIST OR ARRAY!")
        
        return "\n".join(descriptions)

    async def generate_dalle_image(self, prompt: str, slide_title: str) -> str | None:
        """Generate image using DALL-E for text+image slides"""
        try:
            # Create image generation prompt - FIXED TO AVOID RANDOM CONTENT
            safe_prompt = slide_title.replace("Bialogiya", "Biology").replace("biologik", "biological")
            image_prompt = f"Professional educational illustration about {safe_prompt}, academic style diagram or concept visualization, clean background, no text overlay"

            logger.info(f"Generating DALL-E image: {image_prompt[:50]}...")

            # NO TIMEOUT - Generate DALL-E image
            response = await self.client.images.generate(
                model="dall-e-3",
                prompt=image_prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )

            if response.data and len(response.data) > 0 and response.data[0].url:
                image_url = response.data[0].url
                logger.info(f"Generated DALL-E image URL: {image_url[:50]}...")
                return image_url
            else:
                logger.error("No image data received from DALL-E")
                return None

        except Exception as e:
            logger.error(f"Error generating DALL-E image: {e}")
            return None

    async def download_image(self, image_url: str, filename: str) -> str | None:
        """Download image from URL and save to temp folder"""
        try:
            import os
            os.makedirs("temp", exist_ok=True)
            file_path = os.path.join("temp", filename)

            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        with open(file_path, 'wb') as f:
                            f.write(await response.read())
                        logger.info(f"Downloaded image: {file_path}")
                        return file_path
                    else:
                        logger.error(f"Failed to download image: HTTP {response.status}")
                        return None

        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None

    async def generate_independent_work(self, topic: str, page_count: int, language: str) -> Dict:
        """Generate independent work content"""
        language_instructions = {
            'uzbek': "O'zbek tilida",
            'russian': "На русском языке",
            'english': "In English"
        }
        
        lang_instruction = language_instructions.get(language, "O'zbek tilida")
        
        prompt = f"""
{lang_instruction} "{topic}" mavzusida {page_count} sahifali mustaqil ish tayyorla.

Struktura:
1. Kirish (1 sahifa)
2. Asosiy qism ({page_count-2} sahifa) - 3-4 ta bo'lim
3. Xulosa (1 sahifa)

Har bir bo'lim uchun:
- title: Bo'lim sarlavhasi
- content: To'liq matn (300-400 so'z har sahifa uchun)

JSON formatida qaytaring:
{{
  "title": "Ish sarlavhasi",
  "sections": [
    {{
      "title": "Bo'lim nomi",
      "content": "To'liq matn..."
    }}
  ]
}}
"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7
            )
            
            content_text = response.choices[0].message.content
            import json
            content = json.loads(content_text)
            
            # Ensure we have enough sections
            sections = content.get('sections', [])
            
            # Calculate target sections based on page count
            target_sections = max(3, page_count - 2)  # At least 3 sections
            
            # Fill missing sections if needed
            while len(sections) < target_sections:
                sections.append({
                    "title": f"Bo'lim {len(sections) + 1}",
                    "content": f"Bu bo'limda {topic} haqida qo'shimcha ma'lumotlar keltirilgan."
                })
            
            content['sections'] = sections[:target_sections]
            return content
            
        except Exception as e:
            logger.error(f"Error generating independent work: {e}")
            return {
                "title": topic,
                "sections": [
                    {"title": "Kirish", "content": f"{topic} haqida umumiy ma'lumot."},
                    {"title": "Asosiy qism", "content": f"{topic} ning asosiy jihatlari."},
                    {"title": "Xulosa", "content": f"{topic} bo'yicha yakuniy fikrlar."}
                ]
            }

    async def generate_referat_sections(self, topic: str, section_count: int, language: str) -> Dict:
        """Generate referat sections"""
        language_instructions = {
            'uzbek': "O'zbek tilida",
            'russian': "На русском языке", 
            'english': "In English"
        }
        
        lang_instruction = language_instructions.get(language, "O'zbek tilida")
        
        prompt = f"""
{lang_instruction} "{topic}" mavzusida {section_count} ta bo'limli referat tayyorla.

Har bir bo'lim uchun:
- title: Bo'lim sarlavhasi  
- content: Batafsil matn (400-500 so'z)

JSON formatida qaytaring:
{{
  "sections": [
    {{
      "title": "Bo'lim nomi",
      "content": "Batafsil matn..."
    }}
  ]
}}
"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7
            )
            
            content_text = response.choices[0].message.content
            import json
            content = json.loads(content_text)
            
            sections = content.get('sections', [])

            # Fallback if AI doesn't provide enough sections
            while len(sections) < section_count:
                sections.append(f"Bo'lim {len(sections) + 1}")

            return {"sections": sections[:section_count]}

        except Exception as e:
            logger.error(f"Error generating referat sections: {e}")
            # Fallback sections
            sections = []
            for i in range(section_count):
                sections.append({
                    "title": f"{topic} - Bo'lim {i+1}",
                    "content": f"Bu bo'limda {topic} ning {i+1}-qismi haqida batafsil ma'lumot berilgan."
                })
            
            return {"sections": sections}