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

    async def generate_presentation_content(self, topic: str, slide_count: int, language: str) -> Dict:
        """Generate presentation content with AI"""
        try:
            # Create language-specific prompt
            if language == "uz":
                prompt = f"""O'zbek tilida "{topic}" mavzusida {slide_count} ta slaydli professional taqdimot yarating.

3 XIL SHABLON TIZIMI - har 3 slaydda takrorlanadi:
- Slayd 2,5,8,11,14... = SHABLON 1 (faqat matn)
- Slayd 3,6,9,12,15... = SHABLON 2 (matn + rasm)  
- Slayd 4,7,10,13,16... = SHABLON 3 (3 ustunli)

SHABLON 1 - Faqat matn:
- Sarlavha + 4-5 ta bullet point yoki 2 paragraf
- 150-200 so'z, batafsil tushuntirish

SHABLON 2 - Matn + rasm:
- Sarlavha + 3-4 ta qisqa bullet point
- 100-120 so'z (rasm ham bo'lgani uchun)

SHABLON 3 - 3 ustunli:
- Sarlavha + matnni 3 qismga bo'lish
- Har ustun uchun 2-3 bullet point
- Jami 120-150 so'z

MUHIM: Faqat JSON formatda javob bering. Boshqa matn yo'q!

{{
    "slides": [
        {{
            "title": "Slayd sarlavhasi",
            "content": "Slayd mazmuni (bullet points yoki paragraf)"
        }},
        {{
            "title": "Slayd sarlavhasi",
            "content": "Slayd mazmuni (qisqaroq, rasm uchun)"
        }},
        {{
            "title": "Slayd sarlavhasi", 
            "content": "Slayd mazmuni",
            "columns": [
                {{"title": "Ustun 1", "points": ["• Nuqta 1", "• Nuqta 2"]}},
                {{"title": "Ustun 2", "points": ["• Nuqta 1", "• Nuqta 2"]}},
                {{"title": "Ustun 3", "points": ["• Nuqta 1", "• Nuqta 2"]}}
            ]
        }}
    ]
}}"""
            elif language == "ru":
                prompt = f"""Создайте профессиональную презентацию на тему "{topic}" из {slide_count} слайдов на русском языке.

ВАЖНЫЕ ТРЕБОВАНИЯ:
- Напишите минимум 150-200 слов для каждого слайда
- Слайды должны быть в разных форматах:
  * Некоторые слайды со списком (3-5 основных пунктов)
  * Некоторые слайды с непрерывным текстом в параграфах
  * Некоторые слайды с нумерованным списком (1, 2, 3...)
  * Некоторые слайды с классификацией и категориями
- Каждый слайд должен содержать глубокую и детальную информацию
- Приводите практические примеры и факты
- Используйте профессиональный академический стиль

Типы слайдов:
1. Вводный слайд - общая информация о теме
2-3. Теоретические основы - в форме параграфов
4-5. Основные понятия - в виде списка
6-7. Практические примеры - нумерованный список
8-9. Проблемы и решения - категории
10+. Заключение и рекомендации

Ответьте в формате JSON:
{{
    "slides": [
        {{
            "title": "Заголовок слайда",
            "content": "Содержание слайда (150-200 слов)..."
        }}
    ]
}}"""
            else:  # English
                prompt = f"""Create a professional presentation on "{topic}" with {slide_count} slides in English.

IMPORTANT REQUIREMENTS:
- Write at least 150-200 words for each slide
- Slides should be in different formats:
  * Some slides with bullet points (3-5 main points)
  * Some slides with continuous paragraph text
  * Some slides with numbered lists (1, 2, 3...)
  * Some slides with classifications and categories
- Each slide should contain deep and detailed information
- Include practical examples and facts
- Use professional academic style

Slide types:
1. Introduction slide - general information about the topic
2-3. Theoretical foundations - in paragraph form
4-5. Key concepts - as bullet points
6-7. Practical examples - numbered list
8-9. Problems and solutions - categories
10+. Conclusion and recommendations

Respond in JSON format:
{{
    "slides": [
        {{
            "title": "Slide title",
            "content": "Slide content (150-200 words)..."
        }}
    ]
}}"""

            response = self.client.chat.completions.create(
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

            response = self.client.chat.completions.create(
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
- Kamida 800 so'z yozing
- Har bir paragraf 5-7 ta jumla bo'lsin
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
- Kamida 700 so'z yozing
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
- Kamida 1000 so'z yozing
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
- Напишите минимум 800 слов
- Каждый абзац должен содержать 5-7 предложений
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
- Напишите минимум 700 слов
- Каждый абзац должен содержать 5-7 предложений
- Текст без пустых строк
- Используйте профессиональный академический язык
- Каждое предложение логически связано с предыдущим
- Не используйте символы или знаки в тексте
- Текст должен быть плавным и непрерывным
- Ссылки на все разделы работы"""

                else:  # Основные разделы
                    prompt = f"""Создайте глубокое профессиональное академическое содержание для раздела "{section_title}" по теме "{topic}" на русском языке.

Этот основной раздел должен соответствовать следующим требованиям:
- Подробное и глубокое освещение данного аспекта темы
- Теоретические основы и научные подходы
- Практические примеры и результаты исследований
- Мнения и анализы различных авторов
- Проблемы и их решения
- Анализ зарубежного и отечественного опыта

ВАЖНЫЕ ТРЕБОВАНИЯ:
- Напишите минимум 1000 слов
- Каждый абзац должен содержать 6-8 предложений
- Текст без пустых строк
- Используйте профессиональный академический язык
- Каждое предложение логически связано с предыдущим
- Не используйте символы или знаки в тексте
- Текст должен быть плавным и непрерывным
- Каждая мысль полностью обоснована
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
- Write at least 800 words
- Each paragraph should contain 5-7 sentences
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
- Write at least 700 words
- Each paragraph should contain 5-7 sentences
- No empty lines in the text
- Use professional academic language
- Each sentence logically connected to the previous one
- Do not use symbols or signs in the text
- Text should be smooth and continuous
- References to all sections of the work"""

                else:  # Main sections
                    prompt = f"""Create deep professional academic content for the section "{section_title}" on the topic "{topic}" in English.

This main section must meet the following requirements:
- Detailed and thorough coverage of this aspect of the topic
- Theoretical foundations and scientific approaches
- Practical examples and research findings
- Opinions and analyses of various authors
- Problems and their solutions
- Analysis of international and domestic experience

IMPORTANT REQUIREMENTS:
- Write at least 1000 words
- Each paragraph should contain 6-8 sentences
- No empty lines in the text
- Use professional academic language
- Each sentence logically connected to the previous one
- Do not use symbols or signs in the text
- Text should be smooth and continuous
- Each idea fully substantiated
- Section connected to other sections"""

            response = self.client.chat.completions.create(
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
                prompt = f""""{topic}" mavzusi uchun 8 ta adabiyot manbai yarating.

Adabiyotlar ro'yxati turli xil bo'lishi kerak:
- Kitoblar
- Ilmiy maqolalar
- Internet manbalari
- Qonuniy hujjatlar (agar kerak bo'lsa)

Har bir manba haqiqiy va mavzuga mos ko'rinishi kerak."""

            elif language == "ru":
                prompt = f"""Создайте список из 8 литературных источников для темы "{topic}".

Список литературы должен быть разнообразным:
- Книги
- Научные статьи
- Интернет-источники
- Правовые документы (если необходимо)

Каждый источник должен выглядеть реалистично и соответствовать теме."""

            else:  # English
                prompt = f"""Create a list of 8 references for the topic "{topic}".

The reference list should be diverse:
- Books
- Scientific articles
- Internet sources
- Legal documents (if necessary)

Each source should look realistic and relevant to the topic."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )

            references_text = response.choices[0].message.content.strip()
            # Split references by line and clean them
            references = [ref.strip() for ref in references_text.split('\n') if ref.strip()]

            return references[:8]  # Ensure we have exactly 8 references

        except Exception as e:
            logger.error(f"Error generating references: {e}")
            return [
                "Ma'lumotnoma 1",
                "Ma'lumotnoma 2", 
                "Ma'lumotnoma 3",
                "Ma'lumotnoma 4",
                "Ma'lumotnoma 5",
                "Ma'lumotnoma 6",
                "Ma'lumotnoma 7",
                "Ma'lumotnoma 8"
            ]

    async def generate_slide_image(self, slide_title: str, language: str) -> str:
        """Generate image for slide using DALL-E"""
        try:
            # Create language-specific prompt for image generation
            if language == "uz":
                prompt = f"Professional academic illustration for: {slide_title}. Clean, educational style, high quality."
            elif language == "ru":
                prompt = f"Профессиональная академическая иллюстрация для: {slide_title}. Чистый образовательный стиль, высокое качество."
            else:  # English
                prompt = f"Professional academic illustration for: {slide_title}. Clean, educational style, high quality."

            response = self.client.images.generate(
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