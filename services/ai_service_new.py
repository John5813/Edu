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

    async def generate_slide_titles(self, topic: str, num_slides: int, language: str = "uz") -> List[str]:
        """Generate slide titles first as foundation for content generation"""
        logger.info(f"Generating {num_slides} slide titles for topic: {topic}")
        
        if language == "uz":
            prompt = f"""
            Siz taqdimot yaratish uchun yordamchi bo'lasiz. 
            Mavzu: "{topic}".
            Foydalanuvchi {num_slides} ta slayd xohladi. 
            
            JUDA MUHIM TALABLAR:
            1. Har bir sarlavha MAVZUNING TURLI JIHATI haqida bo'lsin
            2. Sarlavhalar bir-birini TAKRORLAMASIN
            3. Hammasi "{topic}" so'zi bilan boshlanmasin - xilma-xil yozing
            4. Har bir sarlavha ANIQ VA BOSHQACHA mavzu bo'lsin
            
            Masalan, agar mavzu "Iqtisodiy faoliyat" bo'lsa:
            - ❌ NOTO'G'RI: "Iqtisodiy faoliyat turlari", "Iqtisodiy faoliyat asoslari", "Iqtisodiy faoliyat yo'nalishlari"
            - ✅ TO'G'RI: "Bozor iqtisodiyoti asoslari", "Moliyaviy tahlil usullari", "Raqobat strategiyalari"
            
            Faqat sarlavhalarni ro'yxat ko'rinishida bering (1. 2. 3. ... formatida), boshqa matn yo'q.
            """
        elif language == "ru":
            prompt = f"""
            Вы помощник для создания презентаций.
            Тема: "{topic}".
            Пользователь хочет {num_slides} слайдов.
            
            ОЧЕНЬ ВАЖНЫЕ ТРЕБОВАНИЯ:
            1. Каждый заголовок должен быть о РАЗНЫХ АСПЕКТАХ темы
            2. Заголовки НЕ ДОЛЖНЫ ПОВТОРЯТЬСЯ
            3. Не все должны начинаться со слов "{topic}" - разнообразьте
            4. Каждый заголовок должен быть ЧЕТКИМ И УНИКАЛЬНЫМ
            
            Дайте только заголовки в виде списка (в формате 1. 2. 3. ...), без дополнительного текста.
            """
        else:  # English
            prompt = f"""
            You are a presentation creation assistant.
            Topic: "{topic}".
            User wants {num_slides} slides.
            
            VERY IMPORTANT REQUIREMENTS:
            1. Each title should be about DIFFERENT ASPECTS of the topic
            2. Titles should NOT REPEAT each other
            3. Don't all start with "{topic}" - diversify
            4. Each title should be CLEAR AND UNIQUE
            
            Provide only the titles as a list (in format 1. 2. 3. ...), no additional text.
            """
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            content = response.choices[0].message.content
            # Parse titles from response (assuming one per line)
            if content:
                titles = [title.strip().lstrip('1234567890.-• ') for title in content.split('\n') if title.strip()]
            else:
                titles = []
            return titles[:num_slides]  # Ensure we don't exceed requested count
            
        except Exception as e:
            logger.error(f"Error generating slide titles: {e}")
            return [f"Slayd {i+1}" for i in range(num_slides)]  # Fallback titles

    async def generate_presentation_in_batches(self, topic: str, slide_count: int, language: str) -> Dict:
        """Generate presentation content using improved step-by-step method with context continuation"""
        logger.info(f"Starting improved batch presentation generation for '{topic}' with {slide_count} slides in {language}")
        
        # Step 1: Generate slide titles first - BARCHA SLAYDLAR UCHUN
        slide_titles = await self.generate_slide_titles(topic, slide_count, language)
        logger.info(f"Generated {len(slide_titles)} slide titles: {slide_titles}")
        
        all_slides = []
        used_topics = set()  # Allaqachon ishlatilgan mavzularni kuzatish
        
        # Step 2: Har bir slayd uchun ALOHIDA kontent yaratish (batches emas, individual)
        for slide_num in range(1, slide_count + 1):
            logger.info(f"Generating individual slide {slide_num} of {slide_count}")
            
            # Get title for this slide
            slide_title = slide_titles[slide_num-1] if slide_num-1 < len(slide_titles) else f"Slayd {slide_num}"
            
            # Get layout type for this slide
            layout_type = self._get_layout_type(slide_num)
            
            # Generate unique content for this specific slide
            slide_content = await self._generate_single_slide_unique(
                topic, slide_num, slide_title, layout_type, language, used_topics, slide_titles
            )
            
            if slide_content:
                all_slides.append(slide_content)
                # Track used content to avoid repetition
                used_topics.add(slide_title)
                if 'content' in slide_content:
                    # Add key phrases from content to used topics
                    content_words = str(slide_content['content']).split()[:10]
                    used_topics.update(content_words)
            
            # Small delay between slides
            if slide_num < slide_count:
                await asyncio.sleep(0.3)

        logger.info(f"Generated complete presentation with {len(all_slides)} unique slides")
        return {"slides": all_slides}

    async def _generate_single_slide_unique(self, topic: str, slide_num: int, slide_title: str, layout_type: str, language: str, used_topics: set, all_titles: List[str]) -> Dict:
        """Generate unique content for a single slide, avoiding repetition"""
        
        language_instructions = {
            'uz': "O'zbek tilida",
            'ru': "На русском языке", 
            'en': "In English"
        }
        
        lang_instruction = language_instructions.get(language, "O'zbek tilida")
        
        # Create context of what has been covered
        covered_topics_str = ", ".join(list(used_topics)[:20]) if used_topics else "Hali hech narsa yozilmagan"
        all_titles_str = "\n".join([f"{i+1}. {t}" for i, t in enumerate(all_titles)])
        
        # Layout-specific instructions
        layout_instructions = {
            "bullet_points": f"""
LAYOUT: 4 nuqtali matn (bullet_points)
- Har bir nuqta alohida bullet tarzida yozilsin.
- FAQAT 50-70 so'z (barcha nuqtalar birgalikda)
- Fikrlar xilma-xil bo'lsin.
""",
            "text_with_image": f"""
LAYOUT: Uzun yahlit matn (text_with_image)
- FAQAT 40-60 so'zli matn yozing.
- Matn bir butun tarzida, sarlavhaga chuqurroq sharh sifatida yozilsin.
- MUHIM: RASM HAQIDA YOZMANG! Faqat mavzu haqida ma'lumot yozing.
""",
            "three_column": f"""
LAYOUT: 3 ustunli matn (three_column)
MUHIM: Har bir ustun alohida mavzu bo'lishi kerak!
Format: "COLUMN1: Sarlavha1|Matn1 (50-70 so'z) COLUMN2: Sarlavha2|Matn2 (50-70 so'z) COLUMN3: Sarlavha3|Matn3 (50-70 so'z)"
- Har ustun uchun BOSHQA mavzu: masalan, sabablari, ta'siri, yechimlar
- Har ustunda to'liq 50-70 so'zli mazmun
"""
        }
        
        layout_instruction = layout_instructions.get(layout_type, layout_instructions["bullet_points"])
        
        prompt = f"""
Siz taqdimot yaratish bo'yicha yordamchisiz. 
{lang_instruction} javob bering.

UMUMIY MAVZU: "{topic}"
SLAYD RAQAMI: {slide_num}
SLAYD SARLAVHASI: "{slide_title}"

BARCHA SLAYDLAR RO'YXATI (takrorlanmasin):
{all_titles_str}

ALLAQACHON YOZILGAN MAVZULAR (bularni TAKRORLAMANG):
{covered_topics_str}

{layout_instruction}

JUDA MUHIM TALABLAR:
1. "{slide_title}" sarlavhasi uchun FAQAT SHU SARLAVHAGA OID ma'lumot yozing
2. Oldingi slaydlarda yozilgan ma'lumotlarni TAKRORLAMANG
3. Har bir slayd BOSHQA JIHAT haqida bo'lsin
4. Agar 3 ustunli bo'lsa, har ustun ALOHIDA mavzu bo'lsin (bir matnni 3 ga bo'lmang!)

JSON formatda javob bering:
{{
  "slide_number": {slide_num},
  "title": "{slide_title}",
  "content": "Layout tipiga mos NOYOB kontent...",
  "layout_type": "{layout_type}"
}}
"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.8  # Higher temperature for more unique content
            )
            
            content_text = response.choices[0].message.content
            import json
            if content_text:
                slide_data = json.loads(content_text)
                logger.info(f"Generated unique slide {slide_num}: {slide_title[:50]}")
                return slide_data
            else:
                return None
            
        except Exception as e:
            logger.error(f"Error generating unique slide {slide_num}: {e}")
            return None

    async def _generate_slide_batch_with_context(self, topic: str, start_slide: int, end_slide: int, total_slides: int, language: str, titles: List[str], previous_context: str = "") -> Dict:
        """Generate a batch of 3 slides using pre-generated titles with improved layouts"""
        
        # Create slide layout mapping for this batch
        slides_info = []
        for i, slide_num in enumerate(range(start_slide, end_slide + 1)):
            title = titles[i] if i < len(titles) else f"Slayd {slide_num}"
            layout_type = self._get_layout_type(slide_num)
            slides_info.append({
                "slide_number": slide_num,
                "title": title,
                "layout_type": layout_type
            })
        
        language_instructions = {
            'uz': "O'zbek tilida",
            'ru': "На русском языке", 
            'en': "In English"
        }
        
        lang_instruction = language_instructions.get(language, "O'zbek tilida")
        
        prompt = f"""
Siz taqdimot yaratish bo'yicha yordamchisiz. 
Umumiy mavzu: "{topic}".
{lang_instruction} javob bering.

{"OLDINGI KONTEKST: " + previous_context if previous_context else ""}

JUDA MUHIM TALABLAR:
1. HAR BIR SLAYD BOSHQACHA MA'LUMOTGA EGA BO'LISHI KERAK - takrorlanmasin!
2. Har bir slayd mavzuning TURLI JIHATLARI haqida bo'lsin
3. Bir xil ma'lumot yoki tushuncha TAKRORLANMASIN
4. Rasm bo'lgan slaidlarda RASM HAQIDA GAP QILMANG - faqat mavzuga oid ma'lumot bering

Quyidagi slaydlar uchun kontent yarating:

{self._get_layout_descriptions(slides_info)}

Har bir slayd uchun layout tipiga mos matn yozing:

1️⃣ 3 ustunli matn (agar kerak bo'lsa):
MUHIM: Har bir ustun alohida mavzu bo'lishi kerak, bir matnni 3 ga bo'lish EMAS!
Format: "COLUMN1: Sarlavha1|Matn1 (50-70 so'z) COLUMN2: Sarlavha2|Matn2 (50-70 so'z) COLUMN3: Sarlavha3|Matn3 (50-70 so'z)"
- Har ustun uchun boshqa mavzu: masalan, sabablari, ta'siri, yechimlar
- Har ustunda to'liq 50-70 so'zli mazmun

2️⃣ 4 nuqtali matn (agar kerak bo'lsa):
- Har bir nuqta alohida bullet tarzida yozilsin.
- FAQAT 50-70 so'z (barcha nuqtalar birgalikda)
- Fikrlar xilma-xil bo'lsin.

3️⃣ Uzun yahlit matn (agar kerak bo'lsa):
- FAQAT 40-60 so'zli matn yozing.
- Matn bir butun tarzida, sarlavhaga chuqurroq sharh sifatida yozilsin.
- MUHIM: RASM HAQIDA YOZMANG! Faqat mavzu haqida ma'lumot yozing.

JSON formatda javob bering:
{{
  "slides": [
    {{
      "slide_number": {start_slide},
      "title": "Berilgan sarlavha",
      "content": "Layout tipiga mos kontent...",
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
            if content_text:
                return json.loads(content_text)
            else:
                return {"slides": []}
            
        except Exception as e:
            logger.error(f"Error generating batch {start_slide}-{end_slide} with titles: {e}")
            return {"slides": []}

    async def generate_presentation_page(self, topic: str, title: str, language: str = "uz") -> Dict:
        """
        Generate comprehensive content for a single presentation page with 3 layout options
        """
        
        if language == "uz":
            prompt = f"""
            Siz taqdimot yaratish bo'yicha yordamchisiz. 
            Umumiy mavzu: "{topic}".
            Slayd sarlavhasi: "{title}".

            Uch qismda natija bering:

            1️⃣ 3 ustunli matn:
            - Har bir ustun alohida sarlavha ostida yozilsin.
            - Har bir ustun matni sarlavhaga mos asosiy gap bilan boshlansin.
            - Har bir ustunda 50–60 so'z bo'lsin.

            2️⃣ 4 nuqtali matn:
            - Har bir nuqta alohida bullet tarzida yozilsin.
            - Har bir nuqta kamida 20 so'zdan iborat bo'lsin.
            - Fikrlar xilma-xil bo'lsin.

            3️⃣ Uzun yahlit matn:
            - 200–250 so'zli matn yozing.
            - Matn bir butun tarzida, sarlavhaga chuqurroq sharh sifatida yozilsin.
            - Bu matnga mos rasm tavsifini ham yozing (AI rasm yaratishi uchun).
            
            JSON formatda javob bering.
            """
        elif language == "ru":
            prompt = f"""
            Вы помощник по созданию презентаций.
            Общая тема: "{topic}".
            Заголовок слайда: "{title}".

            Дайте результат в трех частях:

            1️⃣ Текст в 3 колонки:
            - Каждая колонка под отдельным заголовком.
            - Текст каждой колонки начинается с основного предложения, соответствующего заголовку.
            - В каждой колонке 50–60 слов.

            2️⃣ Текст в 4 пункта:
            - Каждый пункт в стиле маркированного списка.
            - Каждый пункт состоит минимум из 20 слов.
            - Идеи должны быть разнообразными.

            3️⃣ Длинный связный текст:
            - Напишите текст 200–250 слов.
            - Текст как единое целое, как глубокий комментарий к заголовку.
            - Также напишите описание изображения, соответствующего этому тексту (для создания AI-изображения).
            
            Ответьте в формате JSON.
            """
        else:  # English
            prompt = f"""
            You are a presentation creation assistant.
            Overall topic: "{topic}".
            Slide title: "{title}".

            Provide results in three parts:

            1️⃣ 3-column text:
            - Each column under a separate heading.
            - Each column's text starts with a main sentence matching the heading.
            - 50–60 words in each column.

            2️⃣ 4-point text:
            - Each point in bullet style.
            - Each point consists of at least 20 words.
            - Ideas should be diverse.

            3️⃣ Long coherent text:
            - Write 200–250 words of text.
            - Text as a whole, as a deep commentary on the title.
            - Also write an image description matching this text (for AI image creation).
            
            Respond in JSON format.
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
            if content_text:
                return json.loads(content_text)
            else:
                return {"slides": []}
            
        except Exception as e:
            logger.error(f"Error generating presentation page: {e}")
            return {"error": str(e)}

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
            'uz': "O'zbek tilida",
            'ru': "На русском языке", 
            'en': "In English"
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
- layout_type: One of [bullet_points, text_with_image, three_column]

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
            if content_text:
                return json.loads(content_text)
            else:
                return {"slides": []}
            
        except Exception as e:
            logger.error(f"Error generating batch {start_slide}-{end_slide}: {e}")
            return {"slides": []}

    def _get_layout_type(self, slide_number: int) -> str:
        """Determine layout type based on slide number using rotating 3-layout system"""
        if slide_number == 1:
            return "title"
        
        # Calculate position in content slides (excluding title slide)
        content_position = slide_number - 1
        
        # 3-layout rotation: bullet_points, text_with_image, three_column
        layout_cycle = ["bullet_points", "text_with_image", "three_column"]
        layout_index = (content_position - 1) % 3
        
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
                descriptions.append(f"Slide {slide_num} (text_with_image): Generate as ONE CONTINUOUS STRING TEXT with 100-120 words for image generation. NOT A LIST OR ARRAY!")
            elif layout == "three_column":
                descriptions.append(f"Slide {slide_num} (three_column): Generate structured content with 3 separate column topics. Use format: 'COLUMN1: Title1|Content1 text (80 words) COLUMN2: Title2|Content2 text (80 words) COLUMN3: Title3|Content3 text (80 words)'. Each column should have its OWN TOPIC related to main theme, NOT split of one text!")
        
        return "\n".join(descriptions)

    async def generate_dalle_image(self, slide_content: str, slide_title: str) -> str | None:
        """Generate image using DALL-E for text+image slides with photorealistic style"""
        try:
            # Create better image generation prompt based on content and title
            safe_title = slide_title.replace("Bialogiya", "Biology").replace("biologik", "biological")
            
            # Extract key concepts from slide content for better image generation
            content_words = str(slide_content).split()[:20]  # First 20 words for context
            content_context = " ".join(content_words)
            
            # Create PHOTOREALISTIC prompt - HAQIQIY (REAL) rasmlar uchun
            image_prompt = f"Photorealistic, high-quality professional photograph related to {safe_title}. Real-world scene showing {content_context}. Professional photography, natural lighting, realistic details, not artificial or illustrated, authentic and genuine appearance, high resolution"

            logger.info(f"Generating DALL-E image for '{safe_title}': {image_prompt[:80]}...")

            # Generate DALL-E image
            response = await self.client.images.generate(
                model="dall-e-3",
                prompt=image_prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )

            if response.data and len(response.data) > 0 and response.data[0].url:
                image_url = response.data[0].url
                logger.info(f"✅ Generated DALL-E image successfully for '{safe_title}'")
                return image_url
            else:
                logger.error("No image data received from DALL-E")
                return None

        except Exception as e:
            logger.error(f"Error generating DALL-E image for '{slide_title}': {e}")
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
            if content_text:
                content = json.loads(content_text)
            else:
                content = {"sections": []}
            
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
            'uz': "O'zbek tilida",
            'ru': "На русском языке", 
            'en': "In English"
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
            if content_text:
                content = json.loads(content_text)
            else:
                content = {"sections": []}
            
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