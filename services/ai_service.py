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
                prompt = f"""O'zbek tilida "{topic}" mavzusida {slide_count} ta slaydli taqdimot yarating.

Har bir slayd uchun:
- Sarlavha (qisqa va aniq)
- Mazmun (kamida 50 ta so'z)

Taqdimot mantiqiy ketma-ketlikda bo'lishi kerak.

JSON formatda javob bering:
{{
    "slides": [
        {{
            "title": "Slayd sarlavhasi",
            "content": "Slayd mazmuni..."
        }}
    ]
}}"""
            elif language == "ru":
                prompt = f"""Создайте презентацию на тему "{topic}" из {slide_count} слайдов на русском языке.

Для каждого слайда:
- Заголовок (краткий и точный)
- Содержание (минимум 50 слов)

Презентация должна быть логически последовательной.

Ответьте в формате JSON:
{{
    "slides": [
        {{
            "title": "Заголовок слайда",
            "content": "Содержание слайда..."
        }}
    ]
}}"""
            else:  # English
                prompt = f"""Create a presentation on "{topic}" with {slide_count} slides in English.

For each slide:
- Title (short and precise)
- Content (minimum 50 words)

The presentation should be logically structured.

Respond in JSON format:
{{
    "slides": [
        {{
            "title": "Slide title",
            "content": "Slide content..."
        }}
    ]
}}"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7
            )
            
            content = json.loads(response.choices[0].message.content)
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
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun mazmun yarating.

Bu kirish bo'limi bo'lib, quyidagilarni o'z ichiga olishi kerak:
- Mavzuning dolzarbligi
- Ishning maqsadi va vazifalari
- Tadqiqot usullari haqida qisqacha

Kamida 600 so'z yozing. Matn akademik uslubda bo'lishi kerak."""

                elif section_num == total_sections:  # Xulosa
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun mazmun yarating.

Bu xulosa bo'limi bo'lib, quyidagilarni o'z ichiga olishi kerak:
- Asosiy xulosalar
- Tadqiqot natijalari
- Amaliy tavsiyalar
- Kelajakdagi tadqiqotlar yo'nalishlari

Kamida 500 so'z yozing. Matn akademik uslubda bo'lishi kerak."""

                else:  # Asosiy bo'limlar
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun batafsil mazmun yarating.

Bu asosiy bo'lim bo'lib, mavzuning muhim jihatlarini batafsil yoritishi kerak.
Nazariy va amaliy ma'lumotlarni kiritish kerak.

Kamida 800 so'z yozing. Matn akademik uslubda, ilmiy faktlar bilan bo'lishi kerak."""

            elif language == "ru":
                if section_num == 1:  # Введение
                    prompt = f"""Создайте содержание для раздела "{section_title}" по теме "{topic}" на русском языке.

Это введение, которое должно включать:
- Актуальность темы
- Цели и задачи работы
- Краткое описание методов исследования

Напишите минимум 600 слов. Текст должен быть в академическом стиле."""

                elif section_num == total_sections:  # Заключение
                    prompt = f"""Создайте содержание для раздела "{section_title}" по теме "{topic}" на русском языке.

Это заключение, которое должно включать:
- Основные выводы
- Результаты исследования
- Практические рекомендации
- Направления дальнейших исследований

Напишите минимум 500 слов. Текст должен быть в академическом стиле."""

                else:  # Основные разделы
                    prompt = f"""Создайте подробное содержание для раздела "{section_title}" по теме "{topic}" на русском языке.

Это основной раздел, который должен подробно раскрывать важные аспекты темы.
Включите теоретические и практические сведения.

Напишите минимум 800 слов. Текст должен быть в академическом стиле с научными фактами."""

            else:  # English
                if section_num == 1:  # Introduction
                    prompt = f"""Create content for the section "{section_title}" on the topic "{topic}" in English.

This is an introduction that should include:
- Topic relevance
- Goals and objectives of the work
- Brief description of research methods

Write at least 600 words. The text should be in academic style."""

                elif section_num == total_sections:  # Conclusion
                    prompt = f"""Create content for the section "{section_title}" on the topic "{topic}" in English.

This is a conclusion that should include:
- Main conclusions
- Research results
- Practical recommendations
- Future research directions

Write at least 500 words. The text should be in academic style."""

                else:  # Main sections
                    prompt = f"""Create detailed content for the section "{section_title}" on the topic "{topic}" in English.

This is a main section that should thoroughly cover important aspects of the topic.
Include theoretical and practical information.

Write at least 800 words. The text should be in academic style with scientific facts."""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
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
