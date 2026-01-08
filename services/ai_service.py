import json
import logging
import os
import re
from openai import AsyncOpenAI
from typing import Dict, List
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)

def clean_text(text: str) -> str:
    """Clean text from special characters and formatting issues"""
    if not text:
        return ""
    
    text = re.sub(r'[#@&*{}\[\]<>|\\^~`]', '', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text

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
    """AI Service using OpenRouter with dynamic model selection"""
    
    _cached_model = None
    _cache_time = None
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY"),
            base_url=os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL")
        )
    
    @classmethod
    def clear_model_cache(cls):
        """Clear the model cache to force refresh on next request"""
        cls._cached_model = None
        cls._cache_time = None
        logger.info("AI model cache cleared")
    
    async def _get_current_model_id(self) -> str:
        """Get current AI model ID from database with caching"""
        import time
        from config import AI_MODELS, DEFAULT_AI_MODEL
        from database.database import Database
        
        cache_duration = 30
        
        if AIService._cached_model and AIService._cache_time:
            if time.time() - AIService._cache_time < cache_duration:
                return AIService._cached_model
        
        try:
            model_key = await Database.get_current_ai_model()
            model_info = AI_MODELS.get(model_key, AI_MODELS[DEFAULT_AI_MODEL])
            AIService._cached_model = model_info["id"]
            AIService._cache_time = time.time()
            return AIService._cached_model
        except Exception as e:
            logger.error(f"Error getting current model: {e}")
            return AI_MODELS[DEFAULT_AI_MODEL]["id"]

    def _parse_json_safely(self, json_str: str) -> Dict:
        """Parse JSON with automatic repair for common AI output issues"""
        import re
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error, attempting repair: {e}")
            
            repaired = json_str
            
            repaired = re.sub(r',\s*}', '}', repaired)
            repaired = re.sub(r',\s*]', ']', repaired)
            
            quote_count = repaired.count('"') - repaired.count('\\"')
            if quote_count % 2 != 0:
                last_complete_slide = repaired.rfind('},')
                if last_complete_slide > 0:
                    repaired = repaired[:last_complete_slide+1]
                else:
                    last_quote = repaired.rfind('"')
                    if last_quote > 0:
                        repaired = repaired[:last_quote] + '"'
            
            open_braces = repaired.count('{')
            close_braces = repaired.count('}')
            open_brackets = repaired.count('[')
            close_brackets = repaired.count(']')
            
            if open_brackets > close_brackets:
                repaired += ']' * (open_brackets - close_brackets)
            if open_braces > close_braces:
                repaired += '}' * (open_braces - close_braces)
            
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
            
            slides_match = re.search(r'"slides"\s*:\s*\[', json_str)
            if slides_match:
                slides_start = slides_match.end() - 1
                
                slide_objects = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', json_str[slides_start:])
                valid_slides = []
                for slide_obj in slide_objects:
                    try:
                        parsed = json.loads(slide_obj)
                        if 'title' in parsed:
                            valid_slides.append(parsed)
                    except:
                        continue
                
                if valid_slides:
                    logger.info(f"Recovered {len(valid_slides)} slides from truncated JSON")
                    return {"slides": valid_slides}
            
            logger.error(f"Could not repair JSON: {json_str[:500]}...")
            raise ValueError(f"Failed to parse AI response as JSON: {str(e)}")

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception(is_rate_limit_error),
        reraise=True
    )
    async def _make_request(self, messages: List[Dict], max_tokens: int = 4000, temperature: float = 0.7) -> str:
        """Make API request with retry logic - uses dynamically selected model"""
        current_model = await self._get_current_model_id()
        logger.info(f"Using AI model: {current_model}")
        
        response = await self.client.chat.completions.create(
            model=current_model,
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
            
            content = self._parse_json_safely(content_str.strip())
            
            if 'slides' not in content:
                logger.error("No 'slides' key in content")
                raise ValueError("Content must contain 'slides' key")
            
            for idx, slide in enumerate(content['slides']):
                if 'title' not in slide:
                    slide['title'] = f"Slayd {idx + 1}"
                if 'content' not in slide:
                    slide['content'] = ""
                    
            logger.info(f"Generated presentation with {len(content['slides'])} slides")
            
            content = self._normalize_slide_structure(content, slide_count, language)
            return content

        except Exception as e:
            logger.error(f"Error generating presentation content: {e}")
            raise

    def _normalize_slide_structure(self, content: Dict, slide_count: int, language: str) -> Dict:
        """Ensure slides follow the mandatory structure: cover→plan→intro→rotating layouts→conclusion→references→thanks"""
        slides = content.get('slides', [])
        normalized = []
        
        cover_slide = None
        plan_slide = None
        intro_slide = None
        main_slides = []
        conclusion_slide = None
        references_slide = None
        thanks_slide = None
        
        for slide in slides:
            layout = slide.get('layout', '')
            if layout == 'cover' and not cover_slide:
                cover_slide = slide
            elif layout == 'plan' and not plan_slide:
                plan_slide = slide
            elif layout == 'intro' and not intro_slide:
                intro_slide = slide
            elif layout == 'conclusion' and not conclusion_slide:
                conclusion_slide = slide
            elif layout == 'references' and not references_slide:
                references_slide = slide
            elif layout == 'thanks' and not thanks_slide:
                thanks_slide = slide
            elif layout in ['two_column', 'right_image', 'left_image', 'three_column', 'horizontal_image', 'text_with_numbers']:
                main_slides.append(slide)
            else:
                main_slides.append(slide)
        
        title_labels = {
            'uz': {'cover': '', 'plan': 'Reja', 'intro': 'Kirish', 'conclusion': 'Xulosa', 'references': 'Foydalangan adabiyotlar', 'thanks': ''},
            'ru': {'cover': '', 'plan': 'План', 'intro': 'Введение', 'conclusion': 'Заключение', 'references': 'Литература', 'thanks': ''},
            'en': {'cover': '', 'plan': 'Agenda', 'intro': 'Introduction', 'conclusion': 'Conclusion', 'references': 'References', 'thanks': ''}
        }
        labels = title_labels.get(language, title_labels['uz'])
        
        if not cover_slide:
            cover_slide = {'title': '', 'content': '', 'layout': 'cover'}
        normalized.append(cover_slide)
        
        if not plan_slide:
            plan_slide = {'title': labels['plan'], 'content': '', 'layout': 'plan', 'plan_items': []}
        normalized.append(plan_slide)
        
        if not intro_slide:
            intro_slide = {'title': labels['intro'], 'content': '', 'layout': 'intro'}
        normalized.append(intro_slide)
        
        layouts = ['two_column', 'right_image', 'left_image', 'three_column', 'horizontal_image', 'text_with_numbers']
        for i, slide in enumerate(main_slides):
            if slide.get('layout') not in layouts:
                slide['layout'] = layouts[i % len(layouts)]
            normalized.append(slide)
        
        if not conclusion_slide:
            conclusion_slide = {'title': labels['conclusion'], 'content': '', 'layout': 'conclusion'}
        normalized.append(conclusion_slide)
        
        if not references_slide:
            references_slide = {'title': labels['references'], 'content': '', 'layout': 'references', 'references': []}
        normalized.append(references_slide)
        
        if not thanks_slide:
            thanks_slide = {'title': labels['thanks'], 'content': '', 'layout': 'thanks'}
        normalized.append(thanks_slide)
        
        return {'slides': normalized}

    def _get_presentation_prompt_uz(self, topic: str, slide_count: int) -> str:
        """Get Uzbek prompt for presentation generation"""
        main_slides = slide_count - 5
        return f"""O'zbek tilida "{topic}" mavzusida professional taqdimot yarating.

STRUKTURA (jami {slide_count} slayd):
1. Muqova slayd (mavzu nomi va muallif uchun joy)
2. Reja slayd (4 ta sodda va qisqa reja punkti, har biri 3-5 so'z)
3. Kirish slayd (~50 so'z, mavzuga umumiy kirish)
4-{slide_count-3}. Asosiy slaidlar ({main_slides} ta) - har biri mavzuning turli jihatlarini yoritadi
{slide_count-2}. Xulosa slayd (~50 so'z)
{slide_count-1}. Adabiyotlar ro'yxati (4 ta manba)
{slide_count}. Rahmat slayd ("E'tiboringiz uchun rahmat!")

ASOSIY SLAIDLAR UCHUN 6 TA SHABLON (tartib bilan takrorlanadi):
1. two_column - 2 ustun, har biri AYNAN 60 so'z (kam bo'lmasin!)
2. right_image - o'ngda rasm, chapda 74-76 so'z matn
3. left_image - chapda rasm, o'ngda 74-76 so'z matn
4. three_column - 3 ustun, har birida: 1 ta asosiy so'z (BOLD) va unga 15-18 so'z tarif
5. horizontal_image - pastda rasm, ustida AYNAN 50 so'z matn
6. text_with_numbers - raqamli matn 40-50 so'z

Har bir slayd uchun:
- title: Slayd sarlavhasi
- content: Asosiy mazmun
- layout: shablon turi (cover, plan, intro, two_column, right_image, left_image, three_column, horizontal_image, text_with_numbers, conclusion, references, thanks)
- columns (ustunli slaidlar uchun): {{"column_content": "matn"}} har bir ustun uchun

MUHIM: Faqat JSON formatda javob bering!
{{
    "slides": [
        {{"title": "{topic}", "content": "", "layout": "cover"}},
        {{"title": "Reja", "content": "", "layout": "plan", "plan_items": ["1. Punkt", "2. Punkt", "3. Punkt", "4. Punkt"]}},
        {{"title": "Kirish", "content": "kirish matni ~50 so'z", "layout": "intro"}},
        {{"title": "Sarlavha", "content": "", "layout": "two_column", "columns": [{{"column_content": "matn 60 so'z"}}, {{"column_content": "matn 60 so'z"}}]}},
        {{"title": "Sarlavha", "content": "matn 80 so'z", "layout": "right_image"}},
        {{"title": "Sarlavha", "content": "matn 80 so'z", "layout": "left_image"}},
        {{"title": "Sarlavha", "content": "", "layout": "three_column", "columns": [{{"keyword": "Kalit so'z", "column_content": "15-18 so'z tarif"}}, {{"keyword": "Kalit so'z", "column_content": "15-18 so'z tarif"}}, {{"keyword": "Kalit so'z", "column_content": "15-18 so'z tarif"}}]}},
        {{"title": "Sarlavha", "content": "matn 50 so'z", "layout": "horizontal_image"}},
        {{"title": "Sarlavha", "content": "matn 40-50 so'z", "layout": "text_with_numbers"}},
        {{"title": "Xulosa", "content": "matn ~50 so'z", "layout": "conclusion"}},
        {{"title": "Adabiyotlar", "content": "", "layout": "references", "references": ["Manba 1", "Manba 2", "Manba 3", "Manba 4"]}},
        {{"title": "", "content": "", "layout": "thanks"}}
    ]
}}"""

    def _get_presentation_prompt_ru(self, topic: str, slide_count: int) -> str:
        """Get Russian prompt for presentation generation"""
        main_slides = slide_count - 5
        return f"""Создайте профессиональную презентацию на тему "{topic}" на русском языке.

СТРУКТУРА (всего {slide_count} слайдов):
1. Титульный слайд (название темы и место для автора)
2. Слайд с планом (4 простых и коротких пункта, каждый 3-5 слов)
3. Введение (~50 слов, общее введение в тему)
4-{slide_count-3}. Основные слайды ({main_slides} шт) - каждый освещает разные аспекты темы
{slide_count-2}. Заключение (~50 слов)
{slide_count-1}. Список литературы (4 источника)
{slide_count}. Слайд благодарности ("Спасибо за внимание!")

ШАБЛОНЫ ДЛЯ ОСНОВНЫХ СЛАЙДОВ (чередуются по порядку):
1. two_column - 2 колонки РОВНО по 60 слов каждая (не меньше!)
2. right_image - справа изображение, слева текст 74-76 слов
3. left_image - слева изображение, справа текст 74-76 слов
4. three_column - 3 колонки, в каждой: 1 ключевое слово (BOLD) и 15-18 слов описание
5. horizontal_image - внизу изображение, сверху текст РОВНО 50 слов
6. text_with_numbers - текст с цифрами 40-50 слов

Для каждого слайда:
- title: Заголовок слайда
- content: Основной текст
- layout: тип шаблона (cover, plan, intro, two_column, right_image, left_image, three_column, horizontal_image, text_with_numbers, conclusion, references, thanks)
- columns (для колоночных): {{"column_content": "текст"}} для каждой колонки

ВАЖНО: Отвечайте ТОЛЬКО в формате JSON!
{{
    "slides": [
        {{"title": "{topic}", "content": "", "layout": "cover"}},
        {{"title": "План", "content": "", "layout": "plan", "plan_items": ["1. Пункт", "2. Пункт", "3. Пункт", "4. Пункт"]}},
        {{"title": "Введение", "content": "текст введения ~50 слов", "layout": "intro"}},
        {{"title": "Заголовок", "content": "", "layout": "two_column", "columns": [{{"column_content": "текст 60 слов"}}, {{"column_content": "текст 60 слов"}}]}},
        {{"title": "Заголовок", "content": "текст 80 слов", "layout": "right_image"}},
        {{"title": "Заголовок", "content": "текст 80 слов", "layout": "left_image"}},
        {{"title": "Заголовок", "content": "", "layout": "three_column", "columns": [{{"keyword": "Ключевое слово", "column_content": "15-18 слов описание"}}, {{"keyword": "Ключевое слово", "column_content": "15-18 слов описание"}}, {{"keyword": "Ключевое слово", "column_content": "15-18 слов описание"}}]}},
        {{"title": "Заголовок", "content": "текст 50 слов", "layout": "horizontal_image"}},
        {{"title": "Заголовок", "content": "текст 40-50 слов", "layout": "text_with_numbers"}},
        {{"title": "Заключение", "content": "текст ~50 слов", "layout": "conclusion"}},
        {{"title": "Литература", "content": "", "layout": "references", "references": ["Источник 1", "Источник 2", "Источник 3", "Источник 4"]}},
        {{"title": "", "content": "", "layout": "thanks"}}
    ]
}}"""

    def _get_presentation_prompt_en(self, topic: str, slide_count: int) -> str:
        """Get English prompt for presentation generation"""
        main_slides = slide_count - 5
        return f"""Create a professional presentation on "{topic}" in English.

STRUCTURE (total {slide_count} slides):
1. Cover slide (topic name and author placeholder)
2. Agenda slide (4 simple and short points, each 3-5 words)
3. Introduction (~50 words, general intro to topic)
4-{slide_count-3}. Main slides ({main_slides} total) - each covers different aspects
{slide_count-2}. Conclusion (~50 words)
{slide_count-1}. References (4 sources)
{slide_count}. Thank you slide ("Thank you for your attention!")

TEMPLATES FOR MAIN SLIDES (rotate in order):
1. two_column - 2 columns with EXACTLY 60 words each (no less!)
2. right_image - image on right, text 74-76 words on left
3. left_image - image on left, text 74-76 words on right
4. three_column - 3 columns, each with: 1 keyword (BOLD) and 15-18 words description
5. horizontal_image - image at bottom, text EXACTLY 50 words on top
6. text_with_numbers - text with numbers 40-50 words

For each slide:
- title: Slide title
- content: Main text
- layout: template type (cover, plan, intro, two_column, right_image, left_image, three_column, horizontal_image, text_with_numbers, conclusion, references, thanks)
- columns (for column layouts): {{"column_content": "text"}} for each column

IMPORTANT: Respond ONLY in JSON format!
{{
    "slides": [
        {{"title": "{topic}", "content": "", "layout": "cover"}},
        {{"title": "Agenda", "content": "", "layout": "plan", "plan_items": ["1. Point", "2. Point", "3. Point", "4. Point"]}},
        {{"title": "Introduction", "content": "intro text ~50 words", "layout": "intro"}},
        {{"title": "Title", "content": "", "layout": "two_column", "columns": [{{"column_content": "text 60 words"}}, {{"column_content": "text 60 words"}}]}},
        {{"title": "Title", "content": "text 80 words", "layout": "right_image"}},
        {{"title": "Title", "content": "text 80 words", "layout": "left_image"}},
        {{"title": "Title", "content": "", "layout": "three_column", "columns": [{{"keyword": "Keyword", "column_content": "15-18 words description"}}, {{"keyword": "Keyword", "column_content": "15-18 words description"}}, {{"keyword": "Keyword", "column_content": "15-18 words description"}}]}},
        {{"title": "Title", "content": "text 50 words", "layout": "horizontal_image"}},
        {{"title": "Title", "content": "text 40-50 words", "layout": "text_with_numbers"}},
        {{"title": "Conclusion", "content": "text ~50 words", "layout": "conclusion"}},
        {{"title": "References", "content": "", "layout": "references", "references": ["Source 1", "Source 2", "Source 3", "Source 4"]}},
        {{"title": "", "content": "", "layout": "thanks"}}
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
            common_rules = """
QOIDALAR:
- Faqat oddiy matn yozing, hech qanday maxsus belgi ishlatmang (#, @, &, *, {, }, [, ], va h.k.)
- Matnda takrorlanish bo'lmasin - har bir gap yangi ma'lumot bersin
- Markdown formatlash ishlatmang (**, *, _, __ va h.k.)
- Professional akademik til ishlating
- Faqat sof matn, ro'yxatlar yoki raqamli punktlar bo'lmasin"""

            common_rules_ru = """
ПРАВИЛА:
- Пишите только простой текст без специальных символов (#, @, &, *, {, }, [, ] и т.д.)
- Избегайте повторений - каждое предложение должно содержать новую информацию
- Не используйте форматирование Markdown (**, *, _, __ и т.д.)
- Используйте профессиональный академический язык
- Только чистый текст без списков и нумерации"""

            common_rules_en = """
RULES:
- Write only plain text without special characters (#, @, &, *, {, }, [, ], etc.)
- Avoid repetition - each sentence should provide new information
- Do not use Markdown formatting (**, *, _, __, etc.)
- Use professional academic language
- Only plain text without lists or numbered points"""

            if language == "uz":
                if section_num == 1:
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun professional akademik kirish yozing.

250-300 so'z yozing. Mavzuning dolzarbligi, maqsadi va ahamiyatini yoritib bering.
{common_rules}"""
                elif section_num == total_sections:
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun xulosa yozing.

350-450 so'z. Asosiy xulosalar, natijalar va tavsiyalarni yozing.
{common_rules}"""
                else:
                    prompt = f"""O'zbek tilida "{topic}" mavzusidagi "{section_title}" bo'limi uchun chuqur akademik mazmun yarating.

500-600 so'z yozing. Mavzuni to'liq yoritib, misollar va dalillar keltiring.
{common_rules}"""

            elif language == "ru":
                if section_num == 1:
                    prompt = f"""Напишите профессиональное академическое введение для раздела "{section_title}" по теме "{topic}" на русском языке.

250-300 слов. Опишите актуальность темы, цели и значимость.
{common_rules_ru}"""
                elif section_num == total_sections:
                    prompt = f"""Напишите заключение для раздела "{section_title}" по теме "{topic}" на русском языке.

350-450 слов. Изложите основные выводы, результаты и рекомендации.
{common_rules_ru}"""
                else:
                    prompt = f"""Напишите глубокое академическое содержание для раздела "{section_title}" по теме "{topic}" на русском языке.

500-600 слов. Полностью раскройте тему с примерами и аргументами.
{common_rules_ru}"""
            else:
                if section_num == 1:
                    prompt = f"""Write professional academic introduction for "{section_title}" on "{topic}" in English.

250-300 words. Describe the relevance, objectives and significance of the topic.
{common_rules_en}"""
                elif section_num == total_sections:
                    prompt = f"""Write conclusion for "{section_title}" on "{topic}" in English.

350-450 words. Present main conclusions, results and recommendations.
{common_rules_en}"""
                else:
                    prompt = f"""Write deep academic content for "{section_title}" on "{topic}" in English.

500-600 words. Fully cover the topic with examples and arguments.
{common_rules_en}"""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an academic writer. Write clear, well-structured content as plain text only. Never use special characters, markdown, or formatting."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.8
            )

            matn = response.strip()
            matn = matn.replace('\n\n', ' ')
            matn = matn.replace('\n', ' ')
            matn = clean_text(matn)
            
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
                'right_image': 75,
                'left_image': 75,
                'three_column': 18,
                'horizontal_image': 50,
                'text_with_numbers': 45
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
