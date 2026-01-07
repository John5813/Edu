import json
import logging
import os
from openai import AsyncOpenAI
from typing import Dict, List
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)

def is_rate_limit_error(exception: BaseException) -> bool:
    """Check if the exception is a rate limit or quota violation error."""
    error_msg = str(exception)
    return (
        "429" in error_msg
        or "RATELIMIT_EXCEEDED" in error_msg
        or "quota" in error_msg.lower()
        or "rate limit" in error_msg.lower()
        or (hasattr(exception, "status_code") and exception.status_code == 429)
    )

class AIService:
    """AI Service using DeepSeek via OpenRouter (Replit AI Integrations)"""
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY"),
            base_url=os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL")
        )
        self.model = "deepseek/deepseek-v3.2"

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception(is_rate_limit_error),
        reraise=True
    )
    async def _make_request(self, messages: List[Dict], max_tokens: int = 4000, temperature: float = 0.7) -> str:
        """Make API request with retry logic"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content.strip()

    async def generate_presentation_content(self, topic: str, slide_count: int, language: str) -> Dict:
        """Generate presentation content with AI - new structured format"""
        try:
            if language == "uz":
                prompt = self._get_presentation_prompt_uz(topic, slide_count)
            elif language == "ru":
                prompt = self._get_presentation_prompt_ru(topic, slide_count)
            else:
                prompt = self._get_presentation_prompt_en(topic, slide_count)

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8192,
                temperature=0.7
            )

            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            content = json.loads(content_str.strip())
            
            if 'slides' not in content:
                logger.error("No 'slides' key in content")
                raise ValueError("Content must contain 'slides' key")
            
            for idx, slide in enumerate(content['slides']):
                if 'title' not in slide:
                    slide['title'] = f"Slayd {idx + 1}"
                if 'content' not in slide:
                    slide['content'] = ""
                    
            logger.info(f"Generated presentation with {len(content['slides'])} slides")
            return content

        except Exception as e:
            logger.error(f"Error generating presentation content: {e}")
            raise

    def _get_presentation_prompt_uz(self, topic: str, slide_count: int) -> str:
        """Get Uzbek prompt for presentation generation"""
        main_slides = slide_count - 5
        return f"""O'zbek tilida "{topic}" mavzusida professional taqdimot yarating.

STRUKTURA (jami {slide_count} slayd):
1. Muqova slayd (mavzu nomi va muallif uchun joy)
2. Reja slayd (4 ta asosiy reja punkti)
3. Kirish slayd (~50 so'z, mavzuga umumiy kirish)
4-{slide_count-3}. Asosiy slaidlar ({main_slides} ta) - har biri mavzuning turli jihatlarini yoritadi
{slide_count-2}. Xulosa slayd (~50 so'z)
{slide_count-1}. Adabiyotlar ro'yxati (5-6 ta manba)
{slide_count}. Rahmat slayd ("E'tiboringiz uchun rahmat!")

ASOSIY SLAIDLAR UCHUN 6 TA SHABLON (takrorlanadi):
1. 2 ustunli - har ustun 30 so'zdan iborat
2. O'ng 50% rasm, chap matn - 40 so'z
3. Chap 50% rasm, o'ng matn - 40 so'z
4. 3 ustunli - har ustun 20 so'z
5. Pastda gorizontal rasm, ustida 20 so'z
6. Oddiy matn, raqamlar bilan - 50 so'z

Har bir slayd uchun:
- title: Slayd sarlavhasi
- content: Asosiy mazmun
- layout: shablon turi (cover, plan, intro, two_column, right_image, left_image, three_column, horizontal_image, text_with_numbers, conclusion, references, thanks)
- columns (agar kerak bo'lsa): ustunlar ma'lumotlari

MUHIM: Faqat JSON formatda javob bering!
{{
    "slides": [
        {{"title": "...", "content": "...", "layout": "cover"}},
        {{"title": "Reja", "content": "...", "layout": "plan", "plan_items": ["1. ...", "2. ...", "3. ...", "4. ..."]}},
        ...
    ]
}}"""

    def _get_presentation_prompt_ru(self, topic: str, slide_count: int) -> str:
        """Get Russian prompt for presentation generation"""
        main_slides = slide_count - 5
        return f"""Создайте профессиональную презентацию на тему "{topic}" на русском языке.

СТРУКТУРА (всего {slide_count} слайдов):
1. Титульный слайд (название темы и место для автора)
2. Слайд с планом (4 основных пункта)
3. Введение (~50 слов, общее введение в тему)
4-{slide_count-3}. Основные слайды ({main_slides} шт) - каждый освещает разные аспекты темы
{slide_count-2}. Заключение (~50 слов)
{slide_count-1}. Список литературы (5-6 источников)
{slide_count}. Слайд благодарности ("Спасибо за внимание!")

ШАБЛОНЫ ДЛЯ ОСНОВНЫХ СЛАЙДОВ (повторяются):
1. 2 колонки - по 30 слов каждая
2. Справа 50% изображение, слева текст - 40 слов
3. Слева 50% изображение, справа текст - 40 слов
4. 3 колонки - по 20 слов каждая
5. Внизу горизонтальное изображение, сверху 20 слов
6. Простой текст с числами - 50 слов

ВАЖНО: Отвечайте только в формате JSON!
{{
    "slides": [
        {{"title": "...", "content": "...", "layout": "cover"}},
        {{"title": "План", "content": "...", "layout": "plan", "plan_items": ["1. ...", "2. ...", "3. ...", "4. ..."]}},
        ...
    ]
}}"""

    def _get_presentation_prompt_en(self, topic: str, slide_count: int) -> str:
        """Get English prompt for presentation generation"""
        main_slides = slide_count - 5
        return f"""Create a professional presentation on "{topic}" in English.

STRUCTURE (total {slide_count} slides):
1. Cover slide (topic name and author placeholder)
2. Agenda slide (4 main points)
3. Introduction (~50 words, general intro to topic)
4-{slide_count-3}. Main slides ({main_slides} total) - each covers different aspects
{slide_count-2}. Conclusion (~50 words)
{slide_count-1}. References (5-6 sources)
{slide_count}. Thank you slide ("Thank you for your attention!")

TEMPLATES FOR MAIN SLIDES (rotating):
1. 2 columns - 30 words each
2. Right 50% image, left text - 40 words
3. Left 50% image, right text - 40 words
4. 3 columns - 20 words each
5. Bottom horizontal image, top 20 words
6. Plain text with numbers - 50 words

IMPORTANT: Respond only in JSON format!
{{
    "slides": [
        {{"title": "...", "content": "...", "layout": "cover"}},
        {{"title": "Agenda", "content": "...", "layout": "plan", "plan_items": ["1. ...", "2. ...", "3. ...", "4. ..."]}},
        ...
    ]
}}"""

    async def generate_document_content(self, topic: str, section_count: int, document_type: str, language: str) -> Dict:
        """Generate document content with AI - each section separately"""
        try:
            outline = await self._generate_document_outline(topic, section_count, document_type, language)
            
            sections = []
            for i, section_title in enumerate(outline['sections']):
                section_content = await self._generate_section_content(
                    topic, section_title, i + 1, section_count, document_type, language
                )
                sections.append({
                    "title": section_title,
                    "content": section_content
                })

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

JSON formatda javob bering:
{{"sections": ["Bo'lim 1 sarlavhasi", "Bo'lim 2 sarlavhasi", ...]}}"""
                else:
                    prompt = f"""O'zbek tilida "{topic}" mavzusida referat uchun {section_count} ta bo'lim sarlavhalarini yarating.

Bo'limlar:
1. Kirish
2-{section_count-1}. Asosiy bo'limlar  
{section_count}. Xulosa

JSON formatda javob bering:
{{"sections": ["Bo'lim 1 sarlavhasi", "Bo'lim 2 sarlavhasi", ...]}}"""
            elif language == "ru":
                doc_type_ru = "самостоятельной работы" if document_type == "independent_work" else "реферата"
                prompt = f"""Создайте {section_count} заголовков разделов для {doc_type_ru} на тему "{topic}" на русском языке.

Разделы:
1. Введение
2-{section_count-1}. Основные разделы
{section_count}. Заключение

Ответьте в формате JSON:
{{"sections": ["Заголовок раздела 1", "Заголовок раздела 2", ...]}}"""
            else:
                doc_type_en = "independent work" if document_type == "independent_work" else "research paper"
                prompt = f"""Create {section_count} section titles for {doc_type_en} on "{topic}" in English.

Sections:
1. Introduction
2-{section_count-1}. Main sections
{section_count}. Conclusion

Respond in JSON format:
{{"sections": ["Section 1 title", "Section 2 title", ...]}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.7
            )

            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            outline = json.loads(content_str.strip())
            return outline

        except Exception as e:
            logger.error(f"Error generating document outline: {e}")
            raise

    async def _generate_section_content(self, topic: str, section_title: str, section_num: int, total_sections: int, document_type: str, language: str) -> str:
        """Generate content for a specific section"""
        try:
            if language == "uz":
                if section_num == 1:
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun professional akademik mazmun yarating.

Bu kirish bo'limi. 150-200 so'z yozing. Professional akademik til, ravon matn."""
                elif section_num == total_sections:
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun xulosa yozing.

300-400 so'z, professional akademik til."""
                else:
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun chuqur akademik mazmun yarating.

400-500 so'z, professional akademik til, misollar bilan."""

            elif language == "ru":
                if section_num == 1:
                    prompt = f"""Создайте профессиональное академическое введение для раздела "{section_title}" по теме "{topic}" на русском языке.

150-200 слов, академический язык."""
                elif section_num == total_sections:
                    prompt = f"""Создайте заключение для раздела "{section_title}" по теме "{topic}" на русском языке.

150 слов, академический язык."""
                else:
                    prompt = f"""Создайте профессиональное академическое содержание для раздела "{section_title}" по теме "{topic}" на русском языке.

350 слов, академический язык с примерами."""
            else:
                if section_num == 1:
                    prompt = f"""Create professional academic introduction for "{section_title}" on "{topic}" in English.

150-200 words, academic language."""
                elif section_num == total_sections:
                    prompt = f"""Create conclusion for "{section_title}" on "{topic}" in English.

150 words, academic language."""
                else:
                    prompt = f"""Create professional academic content for "{section_title}" on "{topic}" in English.

350 words, academic language with examples."""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an academic writer. Write clear, well-structured content."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.8
            )

            matn = response.strip()
            matn = matn.replace('\n\n', ' ')
            matn = matn.replace('\n', ' ')
            
            return matn

        except Exception as e:
            logger.error(f"Error generating section content: {e}")
            raise

    async def _generate_references(self, topic: str, language: str) -> List[str]:
        """Generate references for the document"""
        try:
            if language == "uz":
                prompt = f"""O'zbek tilida "{topic}" mavzusi bo'yicha 5 ta ilmiy manba (kitob, maqola, veb-sayt) ro'yxatini yarating.

JSON formatda javob bering:
{{"references": ["Manba 1", "Manba 2", ...]}}"""
            elif language == "ru":
                prompt = f"""Создайте список из 5 научных источников по теме "{topic}" на русском языке.

Ответьте в формате JSON:
{{"references": ["Источник 1", "Источник 2", ...]}}"""
            else:
                prompt = f"""Create a list of 5 academic sources for "{topic}" in English.

Respond in JSON format:
{{"references": ["Source 1", "Source 2", ...]}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.7
            )

            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            refs = json.loads(content_str.strip())
            return refs.get('references', [])

        except Exception as e:
            logger.error(f"Error generating references: {e}")
            return []

    async def generate_slide_titles(self, topic: str, slide_count: int, language: str) -> List[str]:
        """Generate individual slide titles for the presentation"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusi uchun {slide_count} ta slayd sarlavhasini yarating.

JSON formatda:
{{"titles": ["Sarlavha 1", "Sarlavha 2", ...]}}"""
            elif language == "ru":
                prompt = f"""Создайте {slide_count} заголовков слайдов для темы "{topic}".

В формате JSON:
{{"titles": ["Заголовок 1", "Заголовок 2", ...]}}"""
            else:
                prompt = f"""Create {slide_count} slide titles for the topic "{topic}".

In JSON format:
{{"titles": ["Title 1", "Title 2", ...]}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.7
            )

            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            data = json.loads(content_str.strip())
            return data.get('titles', [])

        except Exception as e:
            logger.error(f"Error generating slide titles: {e}")
            return []

    async def generate_image_prompt(self, topic: str, slide_title: str, language: str) -> str:
        """Generate detailed English prompt for image generation"""
        try:
            prompt = f"""Create a detailed, professional image generation prompt in English for:
Topic: {topic}
Slide: {slide_title}

The prompt should describe:
- Visual style (modern, professional, high-quality)
- Key visual elements related to the topic
- Color scheme
- Composition
- Any text overlay in {language} language if needed

Output only the image prompt, nothing else. Make it detailed and specific for best results."""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.8
            )

            return response.strip()

        except Exception as e:
            logger.error(f"Error generating image prompt: {e}")
            return f"Professional presentation image about {topic} - {slide_title}, modern corporate style, high quality, 4K"

    async def generate_presentation_in_batches(self, topic: str, slide_count: int, language: str) -> Dict:
        """Generate presentation content in batches - wrapper for generate_presentation_content"""
        return await self.generate_presentation_content(topic, slide_count, language)

    async def generate_presentation_with_manual_titles(self, topic: str, manual_titles: List[str], language: str) -> Dict:
        """Generate presentation content with manually provided titles"""
        try:
            slides = []
            
            slides.append({
                'title': topic,
                'content': '',
                'layout': 'cover'
            })
            
            slides.append({
                'title': 'Reja' if language == 'uz' else ('План' if language == 'ru' else 'Agenda'),
                'content': '',
                'layout': 'plan',
                'plan_items': manual_titles[:4]
            })
            
            slides.append({
                'title': 'Kirish' if language == 'uz' else ('Введение' if language == 'ru' else 'Introduction'),
                'content': await self._generate_intro_content(topic, language),
                'layout': 'intro'
            })
            
            layouts = ['two_column', 'right_image', 'left_image', 'three_column', 'horizontal_image', 'text_with_numbers']
            for i, title in enumerate(manual_titles):
                layout = layouts[i % len(layouts)]
                content = await self._generate_slide_content(topic, title, language, layout)
                slides.append({
                    'title': title,
                    'content': content,
                    'layout': layout
                })
            
            slides.append({
                'title': 'Xulosa' if language == 'uz' else ('Заключение' if language == 'ru' else 'Conclusion'),
                'content': await self._generate_conclusion_content(topic, language),
                'layout': 'conclusion'
            })
            
            slides.append({
                'title': 'Adabiyotlar' if language == 'uz' else ('Литература' if language == 'ru' else 'References'),
                'content': '',
                'layout': 'references',
                'references': await self._generate_references(topic, language)
            })
            
            slides.append({
                'title': '',
                'content': '',
                'layout': 'thanks'
            })
            
            return {'slides': slides}
            
        except Exception as e:
            logger.error(f"Error generating presentation with manual titles: {e}")
            raise

    async def generate_references(self, topic: str, language: str) -> List[str]:
        """Public method to generate references"""
        return await self._generate_references(topic, language)

    async def generate_plan_items(self, topic: str, language: str) -> List[str]:
        """Generate 4 plan items for presentation"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusi uchun 4 ta asosiy reja punktini yarating.

JSON formatda:
{{"items": ["Punkt 1", "Punkt 2", "Punkt 3", "Punkt 4"]}}"""
            elif language == "ru":
                prompt = f"""Создайте 4 основных пункта плана для темы "{topic}".

В формате JSON:
{{"items": ["Пункт 1", "Пункт 2", "Пункт 3", "Пункт 4"]}}"""
            else:
                prompt = f"""Create 4 main agenda items for "{topic}".

In JSON format:
{{"items": ["Item 1", "Item 2", "Item 3", "Item 4"]}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7
            )

            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            data = json.loads(content_str.strip())
            return data.get('items', [])

        except Exception as e:
            logger.error(f"Error generating plan items: {e}")
            return []

    async def _generate_intro_content(self, topic: str, language: str) -> str:
        """Generate introduction content (~50 words)"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusiga kirish yozing. 50 so'z atrofida."""
            elif language == "ru":
                prompt = f"""Напишите введение к теме "{topic}". Около 50 слов."""
            else:
                prompt = f"""Write an introduction to "{topic}". Around 50 words."""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.7
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating intro: {e}")
            return ""

    async def _generate_conclusion_content(self, topic: str, language: str) -> str:
        """Generate conclusion content (~50 words)"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusiga xulosa yozing. 50 so'z atrofida."""
            elif language == "ru":
                prompt = f"""Напишите заключение к теме "{topic}". Около 50 слов."""
            else:
                prompt = f"""Write a conclusion for "{topic}". Around 50 words."""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.7
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating conclusion: {e}")
            return ""

    async def _generate_slide_content(self, topic: str, title: str, language: str, layout: str) -> str:
        """Generate content for a specific slide based on layout"""
        try:
            word_counts = {
                'two_column': 60,
                'right_image': 40,
                'left_image': 40,
                'three_column': 60,
                'horizontal_image': 20,
                'text_with_numbers': 50
            }
            word_count = word_counts.get(layout, 50)
            
            if language == "uz":
                prompt = f""""{topic}" mavzusi, "{title}" slayd uchun mazmun yozing. {word_count} so'z atrofida."""
            elif language == "ru":
                prompt = f"""Напишите содержание для слайда "{title}" по теме "{topic}". Около {word_count} слов."""
            else:
                prompt = f"""Write content for slide "{title}" on topic "{topic}". Around {word_count} words."""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.7
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating slide content: {e}")
            return ""
