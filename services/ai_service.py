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
        """Generate document content with AI"""
        try:
            # Create language-specific prompt
            if language == "uz":
                if document_type == "independent_work":
                    prompt = f"""O'zbek tilida "{topic}" mavzusida mustaqil ish yarating.

{section_count} ta bo'limga bo'ling:
- Kirish
- {section_count - 2} ta asosiy bo'lim
- Xulosa

Har bir bo'lim uchun:
- Sarlavha
- Mazmun (kamida 400 ta so'z)

JSON formatda javob bering:
{{
    "title": "{topic}",
    "sections": [
        {{
            "title": "Bo'lim sarlavhasi",
            "content": "Bo'lim mazmuni..."
        }}
    ],
    "references": [
        "Adabiyot 1",
        "Adabiyot 2",
        "Adabiyot 3",
        "Adabiyot 4",
        "Adabiyot 5"
    ]
}}"""
                else:  # referat
                    prompt = f"""O'zbek tilida "{topic}" mavzusida referat yarating.

{section_count} ta bo'limga bo'ling:
- Kirish
- {section_count - 2} ta asosiy bo'lim
- Xulosa

Har bir bo'lim uchun:
- Sarlavha
- Mazmun (kamida 400 ta so'z)

JSON formatda javob bering:
{{
    "title": "{topic}",
    "sections": [
        {{
            "title": "Bo'lim sarlavhasi",
            "content": "Bo'lim mazmuni..."
        }}
    ],
    "references": [
        "Adabiyot 1",
        "Adabiyot 2",
        "Adabiyot 3",
        "Adabiyot 4",
        "Adabiyot 5"
    ]
}}"""
            elif language == "ru":
                doc_type_ru = "самостоятельную работу" if document_type == "independent_work" else "реферат"
                prompt = f"""Создайте {doc_type_ru} на тему "{topic}" на русском языке.

Разделите на {section_count} разделов:
- Введение
- {section_count - 2} основных раздела
- Заключение

Для каждого раздела:
- Заголовок
- Содержание (минимум 400 слов)

Ответьте в формате JSON:
{{
    "title": "{topic}",
    "sections": [
        {{
            "title": "Заголовок раздела",
            "content": "Содержание раздела..."
        }}
    ],
    "references": [
        "Литература 1",
        "Литература 2",
        "Литература 3",
        "Литература 4",
        "Литература 5"
    ]
}}"""
            else:  # English
                doc_type_en = "independent work" if document_type == "independent_work" else "research paper"
                prompt = f"""Create {doc_type_en} on "{topic}" in English.

Divide into {section_count} sections:
- Introduction
- {section_count - 2} main sections
- Conclusion

For each section:
- Title
- Content (minimum 400 words)

Respond in JSON format:
{{
    "title": "{topic}",
    "sections": [
        {{
            "title": "Section title",
            "content": "Section content..."
        }}
    ],
    "references": [
        "Reference 1",
        "Reference 2",
        "Reference 3",
        "Reference 4",
        "Reference 5"
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
            logger.error(f"Error generating document content: {e}")
            raise
    
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
