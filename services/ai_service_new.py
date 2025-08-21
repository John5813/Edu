import json
import logging
from openai import OpenAI
import os
import aiohttp
from typing import Dict, List
import asyncio

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4o"

    async def generate_presentation_in_batches(self, topic: str, slide_count: int, language: str) -> Dict:
        """Generate presentation content in batches of 3 slides each with specific layouts"""
        try:
            all_slides = []
            batch_size = 3
            
            for batch_start in range(0, slide_count, batch_size):
                batch_end = min(batch_start + batch_size, slide_count)
                current_batch_size = batch_end - batch_start
                batch_number = (batch_start // batch_size) + 1
                
                logger.info(f"Generating batch {batch_number}: slides {batch_start + 1}-{batch_end}")
                
                # Generate batch with specific layout instructions
                batch_slides = await self._generate_slide_batch(
                    topic, batch_start + 1, current_batch_size, batch_number, language
                )
                
                all_slides.extend(batch_slides)
                
                # Small delay between batches
                await asyncio.sleep(0.5)
            
            logger.info(f"Generated complete presentation with {len(all_slides)} slides")
            return {"slides": all_slides}
            
        except Exception as e:
            logger.error(f"Error generating presentation in batches: {e}")
            raise

    async def _generate_slide_batch(self, topic: str, start_slide_num: int, batch_size: int, batch_num: int, language: str) -> List[Dict]:
        """Generate a batch of 3 slides with specific layouts and detailed content"""
        try:
            # Determine layouts for this batch
            layouts_info = []
            for i in range(batch_size):
                slide_num = start_slide_num + i
                if slide_num == 1:
                    layouts_info.append("title")
                else:
                    content_slide_num = slide_num - 1  # Skip title slide
                    layout_type = self._get_batch_layout_type(content_slide_num)
                    layouts_info.append(layout_type)
            
            if language.lower() == 'uzbek' or language.lower() == 'uz':
                prompt = f""""{topic}" mavzusi bo'yicha {batch_size} ta slayd yarating. Bu {batch_num}-chi guruh slaydlar ({start_slide_num}-{start_slide_num + batch_size - 1}).

YANGI TIZIM - LAYOUT TALABLARI:
"""
                for i, layout in enumerate(layouts_info):
                    slide_num = start_slide_num + i
                    if layout == "title":
                        prompt += f"Slayd {slide_num}: SARLAVHA SLAYDI\n"
                    elif layout == "bullet_points":
                        prompt += f"Slayd {slide_num}: BULLET POINT SLAYD (2,5,8,11...)\n- AYNAN 5 ta bullet point\n- HAR NUQTADA KAMIDA 35-40 SO'Z (jami 175-200 so'z)\n- Har nuqta to'liq jumla va batafsil tushuntirish\n- Professional akademik uslub\n"
                    elif layout == "text_with_image":
                        prompt += f"Slayd {slide_num}: MATN+DALL-E RASM SLAYD (3,6,9,12...)\n- KAMIDA 100-120 SO'ZLIK uzluksiz paragraf\n- To'liq akademik tushuntirish, misollar bilan\n- Chuqur tahlil va batafsil ma'lumot\n- Professional uslub\n"
                    elif layout == "three_column":
                        prompt += f"Slayd {slide_num}: 3 USTUNLI SLAYD (4,7,10,13...)\n- Mantiqli sarlavhalar: 'Sabablari/Ta'siri/Yechimlar' yoki shunga o'xshash\n- HAR USTUNDA 3-4 ta batafsil nuqta\n- HAR NUQTA KAMIDA 15-20 SO'Z (har ustun 50+ so'z)\n- Jami 150+ so'z\n- Professional tahlil va misollar\n"

                prompt += f"""
QATTIQ QOIDALAR - BAJARILISHI SHART:
1. BULLET POINT slaydlar: AYNAN 5 nuqta, HAR NUQTADA 35-40 SO'Z (jami 175-200 so'z)
2. MATN+RASM slaydlar: KAMIDA 100-120 SO'ZLIK uzluksiz matn, to'liq akademik tushuntirish
3. 3 USTUNLI slaydlar: 
   - Mantiqli sarlavhalar: "Sabablari/Ta'siri/Yechimlar" yoki shu kabi
   - HAR USTUNDA 3-4 BATAFSIL NUQTA
   - HAR NUQTA 15-20 SO'Z
   - HAR USTUN 50+ SO'Z
   - JAMI 150+ SO'Z

Mantiqiy ketma-ketlikni saqlang. Har guruh slaydlar bir-biriga bog'langan bo'lsin.

JSON formatda javob bering:
{{
    "slides": [
        {{
            "title": "Slayd sarlavhasi",
            "content": "Slayd mazmuni...",
            "layout_type": "bullet_points/text_with_image/three_column"
        }}
    ]
}}"""

            else:  # English/Russian
                prompt = f"""Create {batch_size} slides for topic "{topic}". This is batch {batch_num} (slides {start_slide_num}-{start_slide_num + batch_size - 1}).

NEW SYSTEM - LAYOUT REQUIREMENTS:
"""
                for i, layout in enumerate(layouts_info):
                    slide_num = start_slide_num + i
                    if layout == "title":
                        prompt += f"Slide {slide_num}: TITLE SLIDE\n"
                    elif layout == "bullet_points":
                        prompt += f"Slide {slide_num}: BULLET POINT SLIDE (2,5,8,11...)\n- Exactly 5 bullet points\n- Minimum 30 words per point\n- Total 150+ words\n- Small font detailed content\n"
                    elif layout == "text_with_image":
                        prompt += f"Slide {slide_num}: TEXT+DALL-E IMAGE SLIDE (3,6,9,12...)\n- 80+ words continuous paragraph\n- Large font main content\n- Right side image (50% space)\n"
                    elif layout == "three_column":
                        prompt += f"Slide {slide_num}: 3 COLUMN SLIDE (4,7,10,13...)\n- Logical headers (not Part 1,2,3!)\n- 2-3 points per column\n- Topic-relevant categories\n"

                prompt += f"""
IMPORTANT RULES:
1. BULLET POINT slides: Exactly 5 points, 30+ words each, small font
2. TEXT+IMAGE slides: 80+ words continuous text, large font, space for image
3. 3 COLUMN slides: Not "Part 1,2,3", use logical headers (e.g. "Causes", "Effects", "Solutions")

Maintain logical flow. Each batch should be interconnected.

Respond in JSON format:
{{
    "slides": [
        {{
            "title": "Slide title",
            "content": "Slide content...",
            "layout_type": "bullet_points/text_with_image/three_column"
        }}
    ]
}}"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7
            )

            content_str = response.choices[0].message.content
            if content_str:
                content_str = content_str.strip()
            else:
                content_str = '{"slides": []}'
            logger.info(f"Batch {batch_num} AI response length: {len(content_str)}")
            
            content = json.loads(content_str)
            slides = content.get('slides', [])
            
            # Validate each slide
            for idx, slide in enumerate(slides):
                actual_slide_num = start_slide_num + idx
                if 'title' not in slide:
                    slide['title'] = f"Slayd {actual_slide_num}"
                if 'content' not in slide:
                    slide['content'] = "Mazmun yaratilmoqda..."
                if 'layout_type' not in slide:
                    slide['layout_type'] = layouts_info[idx] if idx < len(layouts_info) else "bullet_points"
                
                # Add slide number for reference
                slide['slide_number'] = actual_slide_num
                
                logger.info(f"Slide {actual_slide_num}: {slide['layout_type']} - {slide['title'][:30]}... ({len(slide['content'])} chars)")
            
            return slides
            
        except Exception as e:
            logger.error(f"Error generating slide batch {batch_num}: {e}")
            raise

    def _get_batch_layout_type(self, content_slide_num: int) -> str:
        """Get layout type for content slides: bullet_points -> text_with_image -> three_column"""
        layout_cycle = ["bullet_points", "text_with_image", "three_column"]
        return layout_cycle[(content_slide_num - 1) % 3]

    async def generate_dalle_image(self, prompt: str, slide_title: str) -> str:
        """Generate image using DALL-E for text+image slides"""
        try:
            # Create image generation prompt
            image_prompt = f"Professional presentation slide illustration for '{slide_title}': {prompt[:100]}. Clean, modern, educational style, suitable for academic presentation."
            
            logger.info(f"Generating DALL-E image: {image_prompt[:50]}...")
            
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=image_prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            
            if response.data and len(response.data) > 0:
                image_url = response.data[0].url
                logger.info(f"Generated DALL-E image URL: {image_url[:50]}...")
                return image_url
            else:
                logger.error("No image data received from DALL-E")
                return None
            
        except Exception as e:
            logger.error(f"Error generating DALL-E image: {e}")
            return None

    async def download_image(self, image_url: str, filename: str) -> str:
        """Download image from URL and save to temp folder"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        content = await response.read()
                        
                        # Ensure temp directory exists
                        os.makedirs("temp", exist_ok=True)
                        filepath = f"temp/{filename}"
                        
                        with open(filepath, "wb") as f:
                            f.write(content)
                        
                        logger.info(f"Downloaded DALL-E image: {filepath}")
                        return filepath
                    else:
                        logger.error(f"Failed to download image: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None

    async def generate_document_content(self, topic: str, section_count: int, document_type: str, language: str) -> Dict:
        """Generate document content with AI - keep existing method for documents"""
        try:
            # First, generate the outline
            outline = await self._generate_document_outline(topic, section_count, document_type, language)

            # Then generate each section individually
            sections = []
            for i, section_title in enumerate(outline['sections']):
                section_content = await self._generate_section_content(
                    topic, section_title, i + 1, section_count, document_type, language
                )
                sections.append({
                    "title": section_title,
                    "content": section_content
                })

            # Generate references
            references = await self._generate_references(topic, language)

            return {
                "title": topic,
                "sections": sections,
                "references": references
            }

        except Exception as e:
            logger.error(f"Error generating document content: {e}")
            raise

    async def _generate_document_outline(self, topic: str, section_count: int, document_type: str, language: str) -> Dict:
        """Generate document outline - placeholder for existing functionality"""
        return {"sections": [f"Section {i+1}" for i in range(section_count)]}

    async def _generate_section_content(self, topic: str, section_title: str, section_num: int, total_sections: int, document_type: str, language: str) -> str:
        """Generate individual section content - placeholder for existing functionality"""  
        return f"Content for {section_title} about {topic}."

    async def _generate_references(self, topic: str, language: str) -> List[str]:
        """Generate references for document - placeholder for existing functionality"""
        return [f"Reference 1 about {topic}", f"Reference 2 about {topic}"]