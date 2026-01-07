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
        # OpenRouter provides access to DeepSeek models
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENRouter_API_KEY")
        )
        self.model = "deepseek/deepseek-chat"

    async def generate_presentation_content(self, topic: str, slide_count: int, language: str) -> Dict:
        """Generate presentation content with AI"""
        try:
            # Create language-specific prompt
            if language == "uz":
                prompt = f"""O'zbek tilida "{topic}" mavzusida {slide_count} ta slaydli professional taqdimot yarating.
                
Mavzu olingach, har bir slayd uchun sarlavha yarating.

Varoqlar ketma-ketligi va tarkibi:

1-varoq (Titul):
- Sarlavha: Mavzu nomi
- Matn: Mijoz ismi uchun joy (Muallif: ...)
- Rasm tavsifi: Mavzuga mos, ichida mavzu so'zlari bo'lgan murakkab rasm (Together AI uchun inglizcha prompt).

2-varoq (Reja):
- Sarlavha: Reja
- Matn: 4 ta asosiy reja bandi.

3-varoq (Kirish):
- Sarlavha: Kirish
- Matn: Mavzu haqida umumiy ma'lumot, taxminan 50 so'z.

Asosiy qism (shu ketma-ketlikda takrorlanadi):
1. Slayd (Layout 1): 2 ustunli. Har bir ustun 30 so'zdan iborat.
2. Slayd (Layout 2): O'ngda 50% rasm, chapda matn.
3. Slayd (Layout 3): Chapda 50% rasm, o'ngda matn.
4. Slayd (Layout 4): 3 ustunli. Har bir ustun 20 so'zdan iborat.
5. Slayd (Layout 5): Gorizontal, pastki tarafda 21:9 rasm, ustida 20 so'z matn.
6. Slayd (Layout 6): Faqat matn, raqamlar ishtirok etadigan, taxminan 50 so'z.

Yakuniy varoqlar:
- Xulosa: Taxminan 50 so'z.
- Adabiyotlar ro'yxati.
- "E'tiboringiz uchun rahmat" varog'i.

JUDA MUHIM:
- Slayd sarlavhasi: qalin qora, 42pt.
- Asosiy gaplar: qalin, 26pt.
- Asosiy ma'lumotlar: 24pt, justify (ikki tomon tekis).
- Rasmlar uchun "image_prompt" (inglizcha, batafsil) maydonini qo'shing.

JSON formatda javob bering:
{{
    "slides": [
        {{
            "title": "...",
            "content": "...",
            "layout": "titul/plan/intro/layout1/layout2/layout3/layout4/layout5/layout6/conclusion/references/thanks",
            "image_prompt": "...",
            "columns": [...]
        }}
    ]
}}"""
            elif language == "ru":
                prompt = f"""Создайте профессиональную презентацию на тему "{topic}" из {slide_count} слайдов на русском языке.

ОЧЕНЬ ВАЖНЫЕ ТРЕБОВАНИЯ:
1. КАЖДЫЙ СЛАЙД ДОЛЖЕН СОДЕРЖАТЬ РАЗНУЮ ИНФОРМАЦИЮ - не повторяйте!
2. Каждый слайд должен освещать РАЗНЫЕ АСПЕКТЫ темы
3. Одинаковая информация или понятия НЕ ДОЛЖНЫ ПОВТОРЯТЬСЯ
4. На слайдах с изображениями НЕ ПИШИТЕ ОБ ИЗОБРАЖЕНИИ - только о теме

3 ТИПА ШАБЛОНОВ - повторяются каждые 3 слайда:
- Слайд 2,5,8,11,14... = ШАБЛОН 1 (только текст)
- Слайд 3,6,9,12,15... = ШАБЛОН 2 (текст + изображение)  
- Слайд 4,7,10,13,16... = ШАБЛОН 3 (3 колонки)

ШАБЛОН 1 - Только текст:
- Заголовок + 3-4 пункта
- ТОЛЬКО 50-70 слов, кратко и четко

ШАБЛОН 2 - Текст + изображение:
- Заголовок + 2-3 кратких пункта
- ТОЛЬКО 40-60 слов
- ВАЖНО: НЕ ПИШИТЕ ОБ ИЗОБРАЖЕНИИ! Пишите только информацию о теме.

ШАБЛОН 3 - 3 колонки:
- Заголовок + разделите текст на 3 части
- По 2-3 пункта в каждой колонке
- Всего 50-70 слов (все колонки вместе)

ВАЖНО: Отвечайте только в формате JSON. Никакого другого текста!

{{
    "slides": [
        {{
            "title": "Заголовок слайда",
            "content": "Содержание слайда (пункты или параграф)"
        }},
        {{
            "title": "Заголовок слайда",
            "content": "Содержание слайда (короче, для изображения)"
        }},
        {{
            "title": "Заголовок слайда", 
            "content": "Содержание слайда",
            "columns": [
                {{"title": "Колонка 1", "points": ["• Пункт 1", "• Пункт 2"]}},
                {{"title": "Колонка 2", "points": ["• Пункт 1", "• Пункт 2"]}},
                {{"title": "Колонка 3", "points": ["• Пункт 1", "• Пункт 2"]}}
            ]
        }}
    ]
}}"""
            else:  # English
                prompt = f"""Create a professional presentation on "{topic}" with {slide_count} slides in English.

VERY IMPORTANT REQUIREMENTS:
1. EACH SLIDE MUST CONTAIN DIFFERENT INFORMATION - no repetition!
2. Each slide should cover DIFFERENT ASPECTS of the topic
3. Same information or concepts MUST NOT BE REPEATED
4. On slides with images, DO NOT WRITE ABOUT THE IMAGE - only about the topic

3 TEMPLATE TYPES - repeat every 3 slides:
- Slide 2,5,8,11,14... = TEMPLATE 1 (text only)
- Slide 3,6,9,12,15... = TEMPLATE 2 (text + image)  
- Slide 4,7,10,13,16... = TEMPLATE 3 (3 columns)

TEMPLATE 1 - Text only:
- Title + 3-4 bullet points
- ONLY 50-70 words, brief and clear

TEMPLATE 2 - Text + image:
- Title + 2-3 brief bullet points
- ONLY 40-60 words
- IMPORTANT: DO NOT WRITE ABOUT THE IMAGE! Write only information about the topic.

TEMPLATE 3 - 3 columns:
- Title + divide content into 3 parts
- 2-3 points per column
- Total 50-70 words (all columns combined)

IMPORTANT: Respond only in JSON format. No other text!

{{
    "slides": [
        {{
            "title": "Slide title",
            "content": "Slide content (bullet points or paragraph)"
        }},
        {{
            "title": "Slide title",
            "content": "Slide content (shorter, for image)"
        }},
        {{
            "title": "Slide title", 
            "content": "Slide content",
            "columns": [
                {{"title": "Column 1", "points": ["• Point 1", "• Point 2"]}},
                {{"title": "Column 2", "points": ["• Point 1", "• Point 2"]}},
                {{"title": "Column 3", "points": ["• Point 1", "• Point 2"]}}
            ]
        }}
    ]
}}"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7
            )

            content_str = response.choices[0].message.content.strip()
            logger.info(f"Raw AI response for presentation: {content_str[:200]}...")
            
            content = json.loads(content_str)
            
            # Validate and fix content
            if 'slides' not in content:
                logger.error("No 'slides' key in content")
                raise ValueError("Content must contain 'slides' key")
            
            # Ensure each slide has title and content
            for idx, slide in enumerate(content['slides']):
                if 'title' not in slide:
                    slide['title'] = f"Slayd {idx + 1}"
                    logger.warning(f"Added missing title to slide {idx + 1}")
                if 'content' not in slide:
                    slide['content'] = "Mazmun yaratilmoqda..."
                    logger.warning(f"Added missing content to slide {idx + 1}")
                    
            logger.info(f"Validated presentation with {len(content['slides'])} slides")
            return content

        except Exception as e:
            logger.error(f"Error generating presentation content: {e}")
            raise

    async def generate_document_content(self, topic: str, section_count: int, document_type: str, language: str) -> Dict:
        """Generate document content with AI - each section separately"""
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
        """Generate document outline with section titles"""
        try:
            if language == "uz":
                if document_type == "independent_work":
                    prompt = f"""O'zbek tilida "{topic}" mavzusida mustaqil ish uchun {section_count} ta bo'lim sarlavhalarini yarating.

Bo'limlar:
1. Kirish
2-{section_count-1}. Asosiy bo'limlar
{section_count}. Xulosa

Har bir bo'lim sarlavhasi aniq va mavzuga mos bo'lishi kerak.

JSON formatda javob bering:
{{
    "sections": [
        "Bo'lim 1 sarlavhasi",
        "Bo'lim 2 sarlavhasi",
        ...
    ]
}}"""
                else:  # referat
                    prompt = f"""O'zbek tilida "{topic}" mavzusida referat uchun {section_count} ta bo'lim sarlavhalarini yarating.

Bo'limlar:
1. Kirish
2-{section_count-1}. Asosiy bo'limlar  
{section_count}. Xulosa

Har bir bo'lim sarlavhasi aniq va mavzuga mos bo'lishi kerak.

JSON formatda javob bering:
{{
    "sections": [
        "Bo'lim 1 sarlavhasi",
        "Bo'lim 2 sarlavhasi",
        ...
    ]
}}"""
            elif language == "ru":
                doc_type_ru = "самостоятельной работы" if document_type == "independent_work" else "реферата"
                prompt = f"""Создайте {section_count} заголовков разделов для {doc_type_ru} на тему "{topic}" на русском языке.

Разделы:
1. Введение
2-{section_count-1}. Основные разделы
{section_count}. Заключение

Каждый заголовок должен быть четким и соответствовать теме.

Ответьте в формате JSON:
{{
    "sections": [
        "Заголовок раздела 1",
        "Заголовок раздела 2",
        ...
    ]
}}"""
            else:  # English
                doc_type_en = "independent work" if document_type == "independent_work" else "research paper"
                prompt = f"""Create {section_count} section titles for {doc_type_en} on "{topic}" in English.

Sections:
1. Introduction
2-{section_count-1}. Main sections
{section_count}. Conclusion

Each title should be clear and relevant to the topic.

Respond in JSON format:
{{
    "sections": [
        "Section 1 title",
        "Section 2 title",
        ...
    ]
}}"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7
            )

            outline = json.loads(response.choices[0].message.content)
            return outline

        except Exception as e:
            logger.error(f"Error generating document outline: {e}")
            raise

    async def _generate_section_content(self, topic: str, section_title: str, section_num: int, total_sections: int, document_type: str, language: str) -> str:
        """Generate content for a specific section"""
        try:
            if language == "uz":
                if section_num == 1:  # Kirish
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun professional akademik mazmun yarating.

Bu kirish bo'limi bo'lib, quyidagi talablarga javob berishi kerak:
- Mavzuning dolzarbligi va zamonaviy ahamiyatini ko'rsatish
- Ishning maqsadi va vazifalari aniq ta'riflangan bo'lishi
- Tadqiqot metodologiyasi va yondashuvlari
- Mavzu bo'yicha mavjud adabiyotlarga qisqacha sharh

MUHIM TALABLAR:
- Aniq 150-200 so'z yozing, ortiqcha emas
- Har bir paragraf 3-4 ta jumla bo'lsin
- Matnda bo'sh qatorlar bo'lmasin
- Professional akademik til ishlatilsin
- Har bir jumla oldingi jumla bilan mantiqan bog'langan bo'lsin
- Matnda belgilar yoki simvollar ishlatmang
- Matn ravon va uzluksiz bo'lishi kerak
- Har bir fikr to'liq va batafsil bayon etilsin"""

                elif section_num == total_sections:  # Xulosa
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun professional akademik mazmun yarating.

Bu xulosa bo'limi bo'lib, quyidagi talablarga javob berishi kerak:
- Barcha asosiy bo'limlardagi natijalarning umumlashtirilishi
- Tadqiqotning asosiy xulosalari va natijalari
- Amaliy tavsiyalar va takliflar
- Kelajakdagi tadqiqotlar yo'nalishlari
- Umumiy baholash va yakuniy fikrlar

MUHIM TALABLAR:
- Aniq 300-400 so'z yozing, ortiqcha emas
- Har bir paragraf 5-7 ta jumla bo'lsin
- Matnda bo'sh qatorlar bo'lmasin
- Professional akademik til ishlatilsin
- Har bir jumla oldingi jumla bilan mantiqan bog'langan bo'lsin
- Matnda belgilar yoki simvollar ishlatmang
- Matn ravon va uzluksiz bo'lishi kerak
- Barcha bo'limlarga havola qilinsin"""

                else:  # Asosiy bo'limlar
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun chuqur professional akademik mazmun yarating.

Quyidagi talablarga qat'iy rioya qiling:
1. Matnning barcha qismlari o'zaro mantiqiy bog'langan bo'lsin
2. Paragraflar o'rtasida sekin o'tishlar bo'lsin (misollar, bog'lovchi so'zlar)
3. Har xil uzunlikdagi jumlalar ishlating (qisqa 5-8 so'z, o'rta 10-15 so'z, uzun 20+ so'z)
4. Akademik uslubda, lekin quruq emas, balki tushunarli tarzda yozing
5. Har bir asosiy fikrdan keyin amaliy misol yoki dalil keltiring
6. Nazariy asoslar va ilmiy yondashuvlar batafsil bayon etilsin
7. Amaliy misollar va tadqiqot natijalari keltirilsin
8. Turli mualliflarning fikrlari va tahlillari berilsin

USLUB VA FORMAT TALABLARI:
- Aniq 400-500 so'z yozing, ortiqcha emas
- Har bir paragraf mantiqiy tugallangan bo'lsin
- Matnda bo'sh qatorlar bo'lmasin
- Professional akademik til, lekin tushunarli bo'lsin
- Jumlalar orasida ravon o'tishlar bo'lsin
- Matnda belgilar yoki simvollar ishlatmang
- Har bir fikr to'liq dalillangan va misollar bilan tasdiqlangan bo'lsin
- Bo'lim boshqa bo'limlar bilan bog'langan bo'lsin"""

            elif language == "ru":
                if section_num == 1:  # Введение
                    prompt = f"""Создайте профессиональное академическое содержание для раздела "{section_title}" по теме "{topic}" на русском языке.

Это введение должно соответствовать следующим требованиям:
- Обоснование актуальности и современной значимости темы
- Четкое определение целей и задач работы
- Методология исследования и подходы
- Краткий обзор существующей литературы по теме

ВАЖНЫЕ ТРЕБОВАНИЯ:
- Напишите точно 150-200 слов, не больше
- Каждый абзац должен содержать 3-4 предложения
- Текст без пустых строк
- Используйте профессиональный академический язык
- Каждое предложение логически связано с предыдущим
- Не используйте символы или знаки в тексте
- Текст должен быть плавным и непрерывным
- Каждая мысль полно и детально изложена"""

                elif section_num == total_sections:  # Заключение
                    prompt = f"""Создайте профессиональное академическое содержание для раздела "{section_title}" по теме "{topic}" на русском языке.

Это заключение должно соответствовать следующим требованиям:
- Обобщение результатов всех основных разделов
- Основные выводы и результаты исследования
- Практические рекомендации и предложения
- Направления дальнейших исследований
- Общая оценка и заключительные мысли

ВАЖНЫЕ ТРЕБОВАНИЯ:
- Напишите максимум 150 слов, не больше
- Каждый абзац должен содержать 3-4 предложения
- Текст без пустых строк
- Используйте профессиональный академический язык
- Каждое предложение логически связано с предыдущим
- Не используйте символы или знаки в тексте
- Текст должен быть плавным и непрерывным
- Ссылки на все разделы работы"""

                else:  # Основные разделы
                    prompt = f"""Создайте профессиональное академическое содержание для раздела "{section_title}" по теме "{topic}" на русском языке.

Этот основной раздел должен соответствовать следующим требованиям:
- Освещение данного аспекта темы
- Теоретические основы и научные подходы
- Практические примеры и результаты исследований
- Мнения и анализы различных авторов

ВАЖНЫЕ ТРЕБОВАНИЯ:
- Напишите максимум 350 слов, не больше
- Каждый абзац должен содержать 4-5 предложений
- Текст без пустых строк
- Используйте профессиональный академический язык
- Каждое предложение логически связано с предыдущим
- Не используйте символы или знаки в тексте
- Текст должен быть плавным и непрерывным
- Раздел связан с другими разделами"""

            else:  # English
                if section_num == 1:  # Introduction
                    prompt = f"""Create professional academic content for the section "{section_title}" on the topic "{topic}" in English.

This introduction must meet the following requirements:
- Justification of relevance and contemporary significance of the topic
- Clear definition of goals and objectives of the work
- Research methodology and approaches
- Brief review of existing literature on the topic

IMPORTANT REQUIREMENTS:
- Write exactly 150-200 words, no more
- Each paragraph should contain 3-4 sentences
- No empty lines in the text
- Use professional academic language
- Each sentence logically connected to the previous one
- Do not use symbols or signs in the text
- Text should be smooth and continuous
- Each idea fully and thoroughly presented"""

                elif section_num == total_sections:  # Conclusion
                    prompt = f"""Create professional academic content for the section "{section_title}" on the topic "{topic}" in English.

This conclusion must meet the following requirements:
- Synthesis of results from all main sections
- Main conclusions and research findings
- Practical recommendations and suggestions
- Future research directions
- Overall assessment and final thoughts

IMPORTANT REQUIREMENTS:
- Write maximum 150 words, no more
- Each paragraph should contain 3-4 sentences
- No empty lines in the text
- Use professional academic language
- Each sentence logically connected to the previous one
- Do not use symbols or signs in the text
- Text should be smooth and continuous
- References to all sections of the work"""

                else:  # Main sections
                    prompt = f"""Create professional academic content for the section "{section_title}" on the topic "{topic}" in English.

This main section must meet the following requirements:
- Coverage of this aspect of the topic
- Theoretical foundations and scientific approaches
- Practical examples and research findings
- Opinions and analyses of various authors

IMPORTANT REQUIREMENTS:
- Write maximum 350 words, no more
- Each paragraph should contain 4-5 sentences
- No empty lines in the text
- Use professional academic language
- Each sentence logically connected to the previous one
- Do not use symbols or signs in the text
- Text should be smooth and continuous
- Section connected to other sections"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Siz akademik yozuvchi sifatida har xil uzunlikdagi jumlalar, izchil bog'lanish va boy misollar bilan mustaqil ishlar yozasiz"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,  # Ijodkorlikni oshirish
                frequency_penalty=0.5,  # Takrorlanishlarni kamaytirish
                presence_penalty=0.4,   # Yangi fikrlarni qo'shish
                max_tokens=4000
            )

            matn = response.choices[0].message.content.strip()
            
            # Bo'sh qatorlarni tozalash
            matn = matn.replace('\n\n', ' ')  # ikki bo'sh qatorni bitta bo'shliqqa
            matn = matn.replace('\n', ' ')    # qolgan bitta bo'sh qatordek ko'rinadiganlarni ham
            
            return matn

        except Exception as e:
            logger.error(f"Error generating section content: {e}")
            raise

    async def _generate_references(self, topic: str, language: str) -> List[str]:
        """Generate references for the document"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusi uchun 5 ta adabiyot manbai yarating.

Har bir adabiyotni alohida qatorda yozing.
Raqam qo'ymasdan yozing.

Adabiyotlar ro'yxati turli xil bo'lishi kerak:
- Kitoblar (muallif, kitob nomi, nashr yili)
- Ilmiy maqolalar (muallif, maqola nomi, jurnal nomi, yil)
- Internet manbalari (sayt nomi, URL, foydalanish sanasi)

MUHIM: Adabiyotlarni yangidan eskiga qarab tartiblang (eng yangi nashr birinchi bo'lsin).
Har bir manba haqiqiy va mavzuga mos ko'rinishi kerak.
Faqat matn yozing, hech qanday raqam va belgisiz."""

            elif language == "ru":
                prompt = f"""Создайте список из 5 литературных источников для темы "{topic}".

Каждый источник пишите на отдельной строке.
Пишите без номеров.

Список литературы должен быть разнообразным:
- Книги (автор, название книги, год издания)
- Научные статьи (автор, название статьи, название журнала, год)
- Интернет-источники (название сайта, URL, дата обращения)

Каждый источник должен выглядеть реалистично и соответствовать теме.
Только текст, без номеров и символов."""

            else:  # English
                prompt = f"""Create a list of 5 references for the topic "{topic}".

Write each reference on a separate line.
Write without numbers.

The reference list should be diverse:
- Books (author, book title, publication year)
- Scientific articles (author, article title, journal name, year)
- Internet sources (website name, URL, access date)

Each source should look realistic and relevant to the topic.
Only text, no numbers or symbols."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )

            references_text = response.choices[0].message.content.strip()
            # Split references by line and clean them
            references = [ref.strip() for ref in references_text.split('\n') if ref.strip()]

            return references[:5]  # Ensure we have exactly 5 references

        except Exception as e:
            logger.error(f"Error generating references: {e}")
            return [
                "Ma'lumotnoma 1",
                "Ma'lumotnoma 2", 
                "Ma'lumotnoma 3",
                "Ma'lumotnoma 4",
                "Ma'lumotnoma 5"
            ]

    async def generate_slide_image(self, slide_title: str, language: str) -> str:
        """Generate image for slide using DALL-E"""
        try:
            # Create language-specific prompt for image generation - HAQIQIY (REAL) rasmlar uchun
            if language == "uz":
                prompt = f"Photorealistic, high-quality photograph related to: {slide_title}. Real-world scene, professional photography, natural lighting, realistic details, not artificial or illustrated."
            elif language == "ru":
                prompt = f"Фотореалистичная, высококачественная фотография на тему: {slide_title}. Реальная сцена, профессиональная фотография, естественное освещение, реалистичные детали, не искусственная и не иллюстрированная."
            else:  # English
                prompt = f"Photorealistic, high-quality photograph related to: {slide_title}. Real-world scene, professional photography, natural lighting, realistic details, not artificial or illustrated."

            response = await self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size="1024x1024",
                quality="standard"
            )

            return response.data[0].url

        except Exception as e:
            logger.error(f"Error generating slide image: {e}")
            return None

    async def download_image(self, image_url: str, file_path: str):
        """Download image from URL to local file"""
        try:
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