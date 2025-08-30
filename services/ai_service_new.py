import json
import logging
from openai import AsyncOpenAI
import os
import aiohttp
from typing import Dict, List
import asyncio

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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
                layout_type = self._get_layout_type_for_slide(slide_num)
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
                        if slide_num == 2:
                            prompt += f"Slayd {slide_num}: UZLUKSIZ MATN SLAYD\n- BITTA UZUN PARAGRAF (bullet pointsiz)\n- 120-150 SO'ZLIK uzluksiz matn\n- Mavzu haqida batafsilroq tushuntirish\n- Professional akademik uslub\n"
                        else:
                            prompt += f"Slayd {slide_num}: BULLET POINT SLAYDI\n- AYNAN 5 ta bullet point\n- HAR NUQTADA 70-80 SO'Z (jami 350-400 so'z)\n- Faqat bullet belgisi (•), raqam va qo'shimcha belgisiz\n- Har nuqta to'liq batafsil paragraf tarzida\n- Professional akademik uslub\n"
                    elif layout == "text_with_image":
                        prompt += f"Slayd {slide_num}: MATN+RASM SLAYD (3,6,9,12...)\n- ANIQ 50 SO'ZLIK batafsil paragraf\n- Faqat mavzu haqida yozing, rasm/DALL-E haqida gap qo'shmang\n- To'liq akademik tushuntirish\n- Professional uslub, mavzuga e'tibor\n"
                    elif layout == "three_column":
                        prompt += f"Slayd {slide_num}: 3 USTUNLI SLAYD (4,7,10,13...)\n- 3 ta turli xil ustun yarating (bir xil so'zlarni takrorlamang!)\n- Har ustun: ALOHIDA KALIT SO'Z + 80 SO'ZLIK BATAFSIL MATN\n- Mavzuga mos 3 ta kategori (masalan: Texnologiya/Jamiyat/Kelajak)\n- HAR USTUN MUSTAQIL va turli jihatlarni ko'rsatsin\n- CONTENT da: Ustun1sarlavha|||80so'zlikmatn|||Ustun2sarlavha|||80so'zlikmatn|||Ustun3sarlavha|||80so'zlikmatn\n- Jami 240+ so'z (3 x 80)\n"
                    elif layout == "three_bullets": # Specific layout for slide 5
                        prompt += f"Slayd {slide_num}: 3 TA NUQTALI SLAYD\n- AYNAN 3 ta bullet point\n- Har nuqtada 70-80 so'z\n- Faqat bullet belgisi (•), raqam va qo'shimcha belgisiz\n- Professional akademik uslub\n"
                    elif layout == "four_numbered": # Specific layout for slide 8
                        prompt += f"Slayd {slide_num}: 4 RAQAMLI MATN SLAYD\n- Har raqam bir-biridan o'ng tarafga siljib boradi\n- Har raqam ostida ANIQ 30 SO'ZLIK ixcham matn\n- Raqamlar quyidagicha: 1., 2., 3., 4.\n- Professional akademik uslub\n"

                prompt += f"""
QATTIQ QOIDALAR:
1. BULLET POINT slaydlar: AYNAN 5 nuqta, HAR NUQTADA 70-80 SO'Z (jami 350-400 so'z), faqat • belgisi, raqamsiz
2. MATN+RASM slaydlar: KAMIDA 100-120 SO'ZLIK uzluksiz matn, to'liq akademik tushuntirish
3. 3 USTUNLI slaydlar: 
   - 3 ta TURLI XIL ustun: har birida alohida kalit so'z + 80 so'zlik batafsil matn  
   - HAR USTUN mustaqil jihat (bir xil so'zlarni takrorlamang!)
   - Mavzuga mos kategoriyalar (masalan: Texnologiya, Jamiyat, Kelajak)
   - CONTENT format: Sarlavha1|||80so'zlikmatn|||Sarlavha2|||80so'zlikmatn|||Sarlavha3|||80so'zlikmatn
   - Jami 240+ so'z (3 x 80)
4. 3 TA NUQTALI SLAYD (2,5,8,11...): AYNAN 3 nuqta, har nuqtada 70-80 so'z, faqat • belgisi, raqamsiz.
5. 4 RAQAMLI MATN SLAYD (8,11,14...): Har raqam bir-biridan o'ng tarafga siljib boradi, har raqam ostida ANIQ 30 SO'Z. Raqamlar: 1., 2., 3., 4.

MUHIM: Oddiy matn yozing, ortiqcha belgilar va shakllar ishlatmang. Mantiqiy ketma-ketlikni saqlang.

JSON formatda javob bering:
{{
    "slides": [
        {{
            "title": "Slayd sarlavhasi",
            "content": "MATN+RASM slayd uchun: Uzun matn",
            "layout_type": "bullet_points/text_with_image/three_column/three_bullets/four_numbered"
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
                        prompt += f"Slide {slide_num}: TEXT+IMAGE SLIDE (3,6,9,12...)\n- EXACTLY 50 words detailed paragraph\n- Only write about the topic, no mention of images/DALL-E\n- Full academic explanation\n- Professional style, focus on topic\n"
                    elif layout == "three_column":
                        prompt += f"Slide {slide_num}: 3 COLUMN SLIDE (4,7,10,13...)\n- Logical headers (not Part 1,2,3!)\n- 2-3 points per column\n- Topic-relevant categories\n"
                    elif layout == "three_bullets": # Specific layout for slide 5
                        prompt += f"Slide {slide_num}: 3 BULLET POINTS SLIDE\n- Exactly 3 bullet points\n- Minimum 30 words per point\n- Professional academic style\n"
                    elif layout == "four_numbered": # Specific layout for slide 8
                        prompt += f"Slide {slide_num}: 4 NUMBERED TEXT SLIDE\n- Each number shifts to the right of the previous one\n- EXACTLY 30 words per number\n- Professional academic style\n"


                prompt += f"""
IMPORTANT RULES:
1. BULLET POINT slides: Exactly 5 points, 30+ words each, small font
2. TEXT+IMAGE slides: 80+ words continuous text, large font, space for image
3. 3 COLUMN slides: Not "Part 1,2,3", use logical headers (e.g. "Causes", "Effects", "Solutions")
4. 3 BULLET POINTS SLIDE (2,5,8,11...): Exactly 3 points, 30+ words each, only bullet symbols.
5. 4 NUMBERED TEXT SLIDE (8,11,14...): Each number shifts to the right of the previous one, EXACTLY 30 words per number. Numbers: 1., 2., 3., 4.

Maintain logical flow. Each batch should be interconnected.

Respond in JSON format:
{{
    "slides": [
        {{
            "title": "Slide title",
            "content": "Slide content...",
            "layout_type": "bullet_points/text_with_image/three_column/three_bullets/four_numbered"
        }}
    ]
}}"""

            response = await self.client.chat.completions.create(
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
                    slide['title'] = f"Slide {actual_slide_num}"
                if 'content' not in slide:
                    slide['content'] = "Content being generated..."
                if 'layout_type' not in slide:
                    slide['layout_type'] = layouts_info[idx] if idx < len(layouts_info) else "bullet_points"

                # Add slide number for reference
                slide['slide_number'] = actual_slide_num

                logger.info(f"Slide {actual_slide_num}: {slide['layout_type']} - {slide['title'][:30]}... ({len(slide['content'])} chars)")

            return slides

        except Exception as e:
            logger.error(f"Error generating slide batch {batch_num}: {e}")
            raise

    def _get_layout_type_for_slide(self, slide_num: int) -> str:
        """Get layout type based on USER's REQUESTED sequence"""
        if slide_num == 1:
            return "title"  # 1. Mavzu haqida tushuncha

        # 5-slide repeating pattern after title (2,3,4,5,6 then repeats)
        cycle_position = (slide_num - 2) % 5  # Start from slide 2
        
        if cycle_position == 0:    # Slides 2,7,12,17...
            return "text_with_image"   # 2. Rasmli varoq
        elif cycle_position == 1:  # Slides 3,8,13,18...
            return "three_column"      # 3. Uch ustun
        elif cycle_position == 2:  # Slides 4,9,14,19...
            return "three_bullets"     # 4. Uch nuqta
        elif cycle_position == 3:  # Slides 5,10,15,20...
            return "text_with_image"   # 5. Rasm
        elif cycle_position == 4:  # Slides 6,11,16,21...
            return "four_numbered"     # 6. 4talik zinasimon
        
        # Fallback (should never reach here)
        return "text_with_image"

    async def generate_dalle_image(self, prompt: str, slide_title: str) -> str | None:
        """Generate image using DALL-E for text+image slides"""
        try:
            # Create image generation prompt - FIXED TO AVOID RANDOM CONTENT
            safe_prompt = slide_title.replace("Bialogiya", "Biology").replace("biologik", "biological")
            image_prompt = f"Professional educational illustration about {safe_prompt}, academic style diagram or concept visualization, clean background, no text overlay"

            logger.info(f"Generating DALL-E image: {image_prompt[:50]}...")

            # Add timeout for DALL-E generation (15 seconds max)
            response = await asyncio.wait_for(
                self.client.images.generate(
                    model="dall-e-3",
                    prompt=image_prompt,
                    size="1024x1024",
                    quality="standard",
                    n=1
                ),
                timeout=15.0  # 15 second timeout
            )

            if response.data and len(response.data) > 0 and response.data[0].url:
                image_url = response.data[0].url
                logger.info(f"Generated DALL-E image URL: {image_url[:50]}...")
                return image_url
            else:
                logger.error("No image data received from DALL-E")
                return None

        except asyncio.TimeoutError:
            logger.warning(f"DALL-E image generation timeout for: {slide_title}")
            return None
        except Exception as e:
            logger.error(f"Error generating DALL-E image: {e}")
            return None

    async def download_image(self, image_url: str, filename: str) -> str | None:
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
        """Generate document outline using AI"""
        try:
            if language == "uz":
                prompt = f"""
"{topic}" mavzusi bo'yicha {document_type} uchun {section_count} ta bo'lim yarating.

QOIDALAR:
1. Har bo'lim mantiqiy ketma-ketlikda
2. Akademik yondashuvda yozing  
3. Mavzuni to'liq qamrab olsin
4. Bo'limlar bir-biriga bog'liq bo'lsin

{document_type.upper()} UCHUN BO'LIMLAR:
- Kirish/Asosiy qismlar/Xulosa tartibida
- Har bo'lim aniq va tushunarli
- Akademik uslubda

JSON formatda javob bering:
{{
    "sections": ["Bo'lim 1 nomi", "Bo'lim 2 nomi", ...]
}}"""
            else:
                prompt = f"""
Create {section_count} sections for {document_type} on topic "{topic}".

REQUIREMENTS:
1. Logical sequence
2. Academic approach
3. Comprehensive coverage
4. Interconnected sections

{document_type.upper()} STRUCTURE:
- Introduction/Main parts/Conclusion format
- Clear and understandable sections
- Academic style

Respond in JSON format:
{{
    "sections": ["Section 1 title", "Section 2 title", ...]
}}"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7
            )

            content_str = response.choices[0].message.content
            if content_str:
                content_str = content_str.strip()
            else:
                content_str = '{"sections": []}'

            content = json.loads(content_str)
            sections = content.get('sections', [])

            # Fallback if AI doesn't provide enough sections
            while len(sections) < section_count:
                sections.append(f"Bo'lim {len(sections) + 1}")

            return {"sections": sections[:section_count]}

        except Exception as e:
            logger.error(f"Error generating document outline: {e}")
            # Fallback outline
            return {"sections": [f"Bo'lim {i+1}" for i in range(section_count)]}

    async def _generate_section_content(self, topic: str, section_title: str, section_num: int, total_sections: int, document_type: str, language: str) -> str:
        """Generate individual section content using AI"""
        try:
            if language == "uz":
                prompt = f"""
"{topic}" mavzusi bo'yicha "{section_title}" bo'limi uchun batafsil matn yozing.

TALABLAR:
1. Bu {section_num}-bo'lim {total_sections} ta bo'limdan
2. {document_type} uchun akademik uslub
3. Kamida 200-300 so'z
4. Mantiqli paragraflar
5. Aniq faktlar va ma'lumotlar
6. O'zbek tilida to'liq matn

MATN TUZILISHI:
- Kirish gap
- Asosiy ma'lumotlar  
- Misollar yoki dalillar
- Bo'lim xulosasi

Faqat matnni qaytaring, boshqa formatlar kerak emas."""
            else:
                prompt = f"""
Write detailed content for section "{section_title}" on topic "{topic}".

REQUIREMENTS:
1. This is section {section_num} of {total_sections} sections
2. Academic style for {document_type}
3. Minimum 200-300 words
4. Logical paragraphs
5. Clear facts and information
6. Complete text in {language}

TEXT STRUCTURE:
- Introduction sentence
- Main information
- Examples or evidence
- Section conclusion

Return only the text content, no other formatting needed."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )

            content = response.choices[0].message.content
            if content:
                return content.strip()
            else:
                return f"{section_title} bo'yicha batafsil ma'lumot. {topic} mavzusi doirasida muhim jihatlar ko'rib chiqiladi."

        except Exception as e:
            logger.error(f"Error generating section content: {e}")
            return f"{section_title} bo'yicha batafsil ma'lumot. {topic} mavzusi doirasida muhim jihatlar ko'rib chiqiladi."

    async def _generate_references(self, topic: str, language: str) -> List[str]:
        """Generate academic references using AI"""
        try:
            if language == "uz":
                prompt = f"""
"{topic}" mavzusi bo'yicha ANIQ 5 ta akademik adabiyot ro'yxati yarating.

TALABLAR:
1. Haqiqiy ko'rinishdagi manbalar
2. Kitoblar, maqolalar, veb-saytlar
3. O'zbek va xorijiy manbalar
4. Akademik formatda
5. Turli xil manba turlari

MANBA TURLARI:
- Ilmiy kitoblar
- Jurnal maqolalari  
- Veb-resurslar
- Dissertatsiyalar
- Konferentsiya materiallari

Har bir manbani alohida qatorda qaytaring."""
            else:
                prompt = f"""
Create EXACTLY 5 academic references for topic "{topic}".

REQUIREMENTS:
1. Realistic-looking sources
2. Books, articles, websites
3. Academic format
4. Various source types
5. Mix of local and international sources

SOURCE TYPES:
- Scientific books
- Journal articles
- Web resources
- Dissertations
- Conference materials

Return each reference on a separate line."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )

            content = response.choices[0].message.content
            if content:
                references = [ref.strip() for ref in content.split('\n') if ref.strip()]
                return references[:5]  # Limit to EXACTLY 5 references
            else:
                return [
                    f"{topic} bo'yicha asosiy adabiyot - Akademiya nashriyoti, 2023",
                    f"{topic} tadqiqotlari - Ilmiy jurnal, 2024",
                    f"{topic} zamonaviy yondashuvlar - Internet resurs"
                ]

        except Exception as e:
            logger.error(f"Error generating references: {e}")
            return [
                f"{topic} bo'yicha asosiy adabiyot - Akademiya nashriyoti, 2023",
                f"{topic} tadqiqotlari - Ilmiy jurnal, 2024",
                f"{topic} zamonaviy yondashuvlar - Internet resurs"
            ]