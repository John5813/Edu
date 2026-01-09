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
    
    text = re.sub(r"^\s*\{?\s*['\"]?columns['\"]?\s*:\s*\[?\s*\{?\s*['\"]?keyword['\"]?\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"['\"]?column_content['\"]?\s*:\s*['\"]?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"['\"]?text['\"]?\s*:\s*['\"]?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"['\"]?content['\"]?\s*:\s*['\"]?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"['\"]?keyword['\"]?\s*:\s*['\"]?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*['\"]", "", text)
    text = re.sub(r"['\"]?\s*\}?\s*\]?\s*\}?\s*$", "", text)
    
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
{slide_count-1}. Adabiyotlar ro'yxati (4 ta sodda manba, har biri 5-8 so'z)
{slide_count}. Rahmat slayd ("E'tiboringiz uchun rahmat!")

ASOSIY SLAIDLAR UCHUN 6 TA SHABLON (tartib bilan takrorlanadi):
1. two_column - 2 MUSTAQIL ustun, har biri ~60 so'z
2. right_image - o'ngda rasm, chapda ~75 so'z matn
3. left_image - chapda rasm, o'ngda ~75 so'z matn
4. three_column - 3 MUSTAQIL ustun, har birida: 1 ta kalit so'z va ~20 so'z tarif
5. horizontal_image - pastda rasm, ustida ~50 so'z matn
6. text_with_numbers - raqamli matn ~50 so'z

JUDA MUHIM QOIDA - USTUNLAR UCHUN:
- two_column va three_column da har bir ustun O'Z ALOHIDA MAVZUSI bo'lishi kerak!
- Bir ustundagi gap BOSHQA ustunda davom etmasin!
- Har bir ustun TUGALLANGAN, MUSTAQIL paragraf bo'lsin!
- Masalan: Ustun1="Bank kreditlari haqida...", Ustun2="Bank depozitlari haqida..." - ALOHIDA mavzular!
- XATO misol: Ustun1="Bank faoliyatining", Ustun2="asosiy yo'nalishlari" - BU XATO!

Har bir slayd uchun:
- title: Slayd sarlavhasi
- content: Asosiy mazmun (FAQAT ustunli bo'lmagan slaidlar uchun)
- layout: shablon turi
- columns: MAJBURIY two_column va three_column uchun - har bir ustun ALOHIDA matn!

MUHIM: Faqat JSON formatda javob bering!
{{
    "slides": [
        {{"title": "{topic}", "content": "", "layout": "cover"}},
        {{"title": "Reja", "content": "", "layout": "plan", "plan_items": ["1. Mavzu haqida", "2. Asosiy tushunchalar", "3. Amaliy qo'llanilishi", "4. Xulosa"]}},
        {{"title": "Kirish", "content": "[BU YERGA HAQIQIY KIRISH MATNI YOZING]", "layout": "intro"}},
        {{"title": "Ikki Jihat", "content": "", "layout": "two_column", "columns": [{{"column_content": "Birinchi jihat haqida to'liq va tugallangan matn. Bu ustun o'z mavzusini yoritadi va boshqa ustundan mustaqil."}}, {{"column_content": "Ikkinchi jihat haqida alohida va tugallangan matn. Bu ustun boshqa mavzuni yoritadi va birinchi ustundan mustaqil."}}]}},
        {{"title": "Sarlavha", "content": "[RASM YONIGA TUGALLANGAN MATN]", "layout": "right_image"}},
        {{"title": "Sarlavha", "content": "[RASM YONIGA TUGALLANGAN MATN]", "layout": "left_image"}},
        {{"title": "Uchta Tushuncha", "content": "", "layout": "three_column", "columns": [{{"keyword": "Birinchi", "column_content": "Birinchi tushuncha haqida tugallangan tarif."}}, {{"keyword": "Ikkinchi", "column_content": "Ikkinchi tushuncha haqida alohida tarif."}}, {{"keyword": "Uchinchi", "column_content": "Uchinchi tushuncha haqida mustaqil tarif."}}]}},
        {{"title": "Sarlavha", "content": "[RASM USTIGA MAZMUNLI MATN]", "layout": "horizontal_image"}},
        {{"title": "Sarlavha", "content": "[RAQAMLI MAZMUNLI MATN]", "layout": "text_with_numbers"}},
        {{"title": "Xulosa", "content": "[XULOSA MATNI]", "layout": "conclusion"}},
        {{"title": "Adabiyotlar", "content": "", "layout": "references", "references": ["Manba nomi va yili", "Manba nomi va yili", "Manba nomi va yili", "Manba nomi va yili"]}},
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
{slide_count-1}. Список литературы (4 простых источника, каждый 5-8 слов)
{slide_count}. Слайд благодарности ("Спасибо за внимание!")

ШАБЛОНЫ ДЛЯ ОСНОВНЫХ СЛАЙДОВ (чередуются по порядку):
1. two_column - 2 НЕЗАВИСИМЫЕ колонки, каждая ~60 слов
2. right_image - справа изображение, слева ~75 слов текста
3. left_image - слева изображение, справа ~75 слов текста
4. three_column - 3 НЕЗАВИСИМЫЕ колонки, каждая: ключевое слово + ~20 слов описание
5. horizontal_image - внизу изображение, сверху ~50 слов текста
6. text_with_numbers - текст с цифрами ~50 слов

ОЧЕНЬ ВАЖНОЕ ПРАВИЛО - ДЛЯ КОЛОНОК:
- В two_column и three_column каждая колонка должна иметь СВОЮ ОТДЕЛЬНУЮ ТЕМУ!
- Предложение из одной колонки НЕ ДОЛЖНО продолжаться в другой колонке!
- Каждая колонка - это ЗАКОНЧЕННЫЙ, НЕЗАВИСИМЫЙ абзац!
- Пример: Колонка1="О банковских кредитах...", Колонка2="О банковских депозитах..." - ОТДЕЛЬНЫЕ темы!
- НЕПРАВИЛЬНО: Колонка1="Банковская деятельность", Колонка2="включает много аспектов" - ЭТО ОШИБКА!

Для каждого слайда:
- title: Заголовок слайда
- content: Основной текст (ТОЛЬКО для слайдов без колонок)
- layout: тип шаблона
- columns: ОБЯЗАТЕЛЬНО для two_column и three_column - каждая колонка ОТДЕЛЬНЫЙ текст!

ВАЖНО: Отвечайте ТОЛЬКО в формате JSON!
{{
    "slides": [
        {{"title": "{topic}", "content": "", "layout": "cover"}},
        {{"title": "План", "content": "", "layout": "plan", "plan_items": ["1. О теме", "2. Основные понятия", "3. Применение", "4. Выводы"]}},
        {{"title": "Введение", "content": "[НАПИШИТЕ РЕАЛЬНЫЙ ТЕКСТ ВВЕДЕНИЯ]", "layout": "intro"}},
        {{"title": "Два Аспекта", "content": "", "layout": "two_column", "columns": [{{"column_content": "Первый аспект темы с полным и законченным описанием. Эта колонка независима от второй."}}, {{"column_content": "Второй аспект темы с отдельным и законченным описанием. Эта колонка независима от первой."}}]}},
        {{"title": "Заголовок", "content": "[ЗАКОНЧЕННЫЙ ТЕКСТ РЯДОМ С ИЗОБРАЖЕНИЕМ]", "layout": "right_image"}},
        {{"title": "Заголовок", "content": "[ЗАКОНЧЕННЫЙ ТЕКСТ РЯДОМ С ИЗОБРАЖЕНИЕМ]", "layout": "left_image"}},
        {{"title": "Три Понятия", "content": "", "layout": "three_column", "columns": [{{"keyword": "Первое", "column_content": "Описание первого понятия, законченное."}}, {{"keyword": "Второе", "column_content": "Описание второго понятия, отдельное."}}, {{"keyword": "Третье", "column_content": "Описание третьего понятия, независимое."}}]}},
        {{"title": "Заголовок", "content": "[ТЕКСТ НАД ИЗОБРАЖЕНИЕМ]", "layout": "horizontal_image"}},
        {{"title": "Заголовок", "content": "[ТЕКСТ С ЦИФРАМИ]", "layout": "text_with_numbers"}},
        {{"title": "Заключение", "content": "[ТЕКСТ ЗАКЛЮЧЕНИЯ]", "layout": "conclusion"}},
        {{"title": "Литература", "content": "", "layout": "references", "references": ["Название источника и год", "Название источника и год", "Название источника и год", "Название источника и год"]}},
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
{slide_count-1}. References (4 simple sources, each 5-8 words)
{slide_count}. Thank you slide ("Thank you for your attention!")

TEMPLATES FOR MAIN SLIDES (rotate in order):
1. two_column - 2 INDEPENDENT columns, each ~60 words
2. right_image - image on right, ~75 words text on left
3. left_image - image on left, ~75 words text on right
4. three_column - 3 INDEPENDENT columns, each: keyword + ~20 words description
5. horizontal_image - image at bottom, ~50 words text on top
6. text_with_numbers - text with numbers ~50 words

CRITICAL RULE - FOR COLUMNS:
- In two_column and three_column, each column must have its OWN SEPARATE TOPIC!
- A sentence from one column must NOT continue in another column!
- Each column must be a COMPLETE, INDEPENDENT paragraph!
- Example: Column1="About bank loans...", Column2="About bank deposits..." - SEPARATE topics!
- WRONG: Column1="Banking activities", Column2="include many aspects" - THIS IS AN ERROR!

For each slide:
- title: Slide title
- content: Main text (ONLY for non-column slides)
- layout: template type
- columns: REQUIRED for two_column and three_column - each column SEPARATE text!

IMPORTANT: Respond ONLY in JSON format!
{{
    "slides": [
        {{"title": "{topic}", "content": "", "layout": "cover"}},
        {{"title": "Agenda", "content": "", "layout": "plan", "plan_items": ["1. About the topic", "2. Key concepts", "3. Applications", "4. Conclusions"]}},
        {{"title": "Introduction", "content": "[WRITE ACTUAL INTRODUCTION TEXT]", "layout": "intro"}},
        {{"title": "Two Aspects", "content": "", "layout": "two_column", "columns": [{{"column_content": "First aspect of the topic with complete description. This column is independent from the second."}}, {{"column_content": "Second aspect of the topic with separate description. This column is independent from the first."}}]}},
        {{"title": "Title", "content": "[COMPLETE TEXT NEXT TO IMAGE]", "layout": "right_image"}},
        {{"title": "Title", "content": "[COMPLETE TEXT NEXT TO IMAGE]", "layout": "left_image"}},
        {{"title": "Three Concepts", "content": "", "layout": "three_column", "columns": [{{"keyword": "First", "column_content": "Description of first concept, complete."}}, {{"keyword": "Second", "column_content": "Description of second concept, separate."}}, {{"keyword": "Third", "column_content": "Description of third concept, independent."}}]}},
        {{"title": "Title", "content": "[TEXT ABOVE IMAGE]", "layout": "horizontal_image"}},
        {{"title": "Title", "content": "[TEXT WITH NUMBERS]", "layout": "text_with_numbers"}},
        {{"title": "Conclusion", "content": "[CONCLUSION TEXT]", "layout": "conclusion"}},
        {{"title": "References", "content": "", "layout": "references", "references": ["Source name and year", "Source name and year", "Source name and year", "Source name and year"]}},
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
        """Generate academic references for course work"""
        try:
            target_lang_name = "Russian" if language == "ru" else "English" if language == "en" else "Uzbek"
            prompt = f"""Create a list of 6-8 real-looking academic references for a course work on the topic: "{topic}".
THE ENTIRE LIST MUST BE IN {target_lang_name.upper()} LANGUAGE. 
Include author, title, city, publisher, and year. 
Format: Author. Title. City: Publisher, Year.

Return as a JSON list:
{{"references": ["Reference 1", "Reference 2", ...]}}"""

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
            return data.get('references', [])
            
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

    async def generate_course_work_content(self, topic: str, chapters: int, language: str) -> Dict:
        """Generate course work content with chapter structure and footnotes
        
        Structure:
        - Kirish (Introduction) - 2 pages
        - Bo'limlar (Chapters) with 3 subsections each
        - Xulosa (Conclusion)
        - Adabiyotlar (References)
        """
        try:
            content = {
                "title": topic,
                "chapters": [],
                "introduction": "",
                "intro_points": {},
                "conclusion": "",
                "references": []
            }
            
            # Generate chapter titles first
            chapter_titles = await self._generate_chapter_titles(topic, chapters, language)
            
            # Generate introduction (2 pages worth ~600 words)
            content["introduction"] = await self._generate_course_intro(topic, language)
            
            # Generate specific intro points (Subject, Object, Goal, etc.)
            content["intro_points"] = await self._generate_intro_points(topic, language)
            
            # Generate each chapter with 3 subsections
            for i, chapter_title in enumerate(chapter_titles, 1):
                chapter = {
                    "number": i,
                    "title": chapter_title,
                    "subsections": []
                }
                
                # Generate 3 subsections for each chapter
                subsection_titles = await self._generate_subsection_titles(topic, chapter_title, language)
                
                for j, sub_title in enumerate(subsection_titles[:3], 1):
                    sub_content = await self._generate_subsection_content(topic, chapter_title, sub_title, language)
                    
                    chapter["subsections"].append({
                        "number": f"{i}.{j}",
                        "title": sub_title,
                        "content": sub_content
                    })
                
                content["chapters"].append(chapter)
            
            # Generate conclusion
            content["conclusion"] = await self._generate_course_conclusion(topic, language)
            
            # Generate references
            content["references"] = await self._generate_references(topic, language)
            
            return content
            
        except Exception as e:
            logger.error(f"Error generating course work content: {e}")
            raise

    async def _generate_chapter_titles(self, topic: str, chapters: int, language: str) -> List[str]:
        """Generate chapter titles for course work"""
        try:
            # First, ensure we have the topic in the target language
            translated_topic = topic
            if language != "uz":
                translation_prompt = f"Translate this topic into {'Russian' if language == 'ru' else 'English'}: {topic}. Provide only the translated text."
                translated_topic = await self._make_request(
                    messages=[{"role": "user", "content": translation_prompt}],
                    max_tokens=100
                )
                translated_topic = translated_topic.strip()

            if language == "ru":
                prompt = f"""Для темы "{translated_topic}" создайте {chapters} названий глав для курсовой работы.
Каждая глава должна охватывать разные аспекты темы. ВСЕ ДОЛЖНО БЫТЬ НА РУССКОМ ЯЗЫКЕ.

Ответьте в формате JSON:
{{"chapters": ["Название главы 1", "Название главы 2", ...]}}"""
            elif language == "en":
                prompt = f"""For topic "{translated_topic}", create {chapters} chapter titles for course work.
Each chapter should cover different aspects of the topic. EVERYTHING MUST BE IN ENGLISH.

Respond in JSON format:
{{"chapters": ["Chapter 1 title", "Chapter 2 title", ...]}}"""
            else: # uz
                prompt = f""""{topic}" mavzusi uchun {chapters} ta bo'lim (chapter) sarlavhasini yarating.
Har bir bo'lim mavzuning turli jihatlarini qamrab olishi kerak. HAMMASI O'ZBEK TILIDA BO'LSIN.

JSON formatda javob bering:
{{"chapters": ["1-bo'lim sarlavhasi", "2-bo'lim sarlavhasi", ...]}}"""

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
            return data.get('chapters', [f"Bo'lim {i}" for i in range(1, chapters + 1)])
            
        except Exception as e:
            logger.error(f"Error generating chapter titles: {e}")
            return [f"Bo'lim {i}" for i in range(1, chapters + 1)]

    async def _generate_subsection_titles(self, topic: str, chapter_title: str, language: str) -> List[str]:
        """Generate 3 subsection titles for a chapter"""
        try:
            # Use chapter_title directly as it should already be in the target language
            if language == "ru":
                prompt = f"""Создайте 3 названия подразделов для главы "{chapter_title}" по теме. ВСЕ НА РУССКОМ ЯЗЫКЕ.

В формате JSON:
{{"subsections": ["Подраздел 1", "Подраздел 2", "Подраздел 3"]}}"""
            elif language == "en":
                prompt = f"""Create 3 subsection titles for chapter "{chapter_title}". EVERYTHING IN ENGLISH.

In JSON format:
{{"subsections": ["Subsection 1", "Subsection 2", "Subsection 3"]}}"""
            else: # uz
                prompt = f""""{chapter_title}" bo'limi uchun 3 ta kichik bo'lim sarlavhasini yarating. HAMMASI O'ZBEK TILIDA BO'LSIN.

JSON formatda:
{{"subsections": ["1.1 sarlavha", "1.2 sarlavha", "1.3 sarlavha"]}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
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
            return data.get('subsections', ["Kirish qismi", "Asosiy mazmun", "Yakuniy fikrlar"])
            
        except Exception as e:
            logger.error(f"Error generating subsection titles: {e}")
            return ["Kirish qismi", "Asosiy mazmun", "Yakuniy fikrlar"]

    async def _generate_subsection_content(self, topic: str, chapter_title: str, subsection_title: str, language: str) -> str:
        """Generate content for a subsection (~400-500 words)"""
        try:
            common_rules = """
QOIDALAR:
- Faqat oddiy matn yozing, hech qanday maxsus belgi ishlatmang
- Hech qanday markdown formatidan foydalanmang
- Har bir gap to'liq va mustaqil bo'lishi kerak
- Professional akademik uslubda yozing"""

            common_rules_ru = """
ПРАВИЛА:
- Пишите только простой текст без специальных символов
- Не используйте markdown форматирование
- Каждое предложение должно быть полным и самостоятельным
- Пишите в профессиональном академическом стиле"""

            common_rules_en = """
RULES:
- Write only plain text without special characters
- Do not use markdown formatting
- Each sentence must be complete and independent
- Write in professional academic style"""

            if language == "uz":
                prompt = f""""{topic}" mavzusi, "{chapter_title}" bo'limi, "{subsection_title}" kichik bo'limi uchun akademik mazmun yozing.

400-500 so'z yozing. Mavzuni chuqur yoritib, misollar va dalillar keltiring.
{common_rules}"""
            elif language == "ru":
                prompt = f"""Напишите академическое содержание для подраздела "{subsection_title}" главы "{chapter_title}" по теме "{topic}".

400-500 слов. Глубоко раскройте тему с примерами и аргументами.
{common_rules_ru}"""
            else:
                prompt = f"""Write academic content for subsection "{subsection_title}" of chapter "{chapter_title}" on topic "{topic}".

400-500 words. Deeply cover the topic with examples and arguments.
{common_rules_en}"""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an academic writer. Write clear, well-structured content as plain text only."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.8
            )
            
            matn = response.strip()
            matn = clean_text(matn)
            return matn
            
        except Exception as e:
            logger.error(f"Error generating subsection content: {e}")
            return ""

    async def _generate_intro_points(self, topic: str, language: str) -> Dict[str, str]:
        """Generate specific introduction points: Subject, Object, Goal, Tasks, etc."""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi kurs ishi uchun quyidagi 6 ta punktga juda batafsil va aynan mavzuga asoslangan akademik tarif bering. 
DIQQAT: Umumiy gaplardan qoching, har bir punkt aynan "{topic}" mavzusining ichki jihatlarini, uning ilmiy va amaliy ahamiyatini yoritib berishi shart. 

Punktlar (har biri kamida 40-50 so'zdan iborat bo'lsin):
1. Kurs ishining predmeti (Mavzuning qaysi jihatlari o'rganiladi?).
2. Kurs ishining obyekti (Mavzu qaysi soha yoki tushunchaga tegishli?).
3. Mavzuning o‘rganilganlik darajasi (Hozirgi kunda bu mavzu qanchalik o'rganilgan?).
4. Kurs ishining maqsadi (Tadqiqotdan ko'zlangan asosiy natija nima?).
5. Kurs ishining vazifalari (Maqsadga erishish uchun bajarilishi kerak bo'lgan bosqichlarni punktma-punkt yozing).
6. Kurs ishining tarkibiy tuzilishi (Kirish, bo'limlar va xulosaning qisqacha tavsifi).

JSON formatda javob bering:
{{
  "point_1": "konkret mavzu predmeti haqida chuqur tahlil...",
  "point_2": "mavzu obyekti haqida batafsil ma'lumot...",
  "point_3": "ilmiy daraja tahlili...",
  "point_4": "aniq maqsad tarifi...",
  "point_5": "1. ...\\n2. ...\\n3. ...",
  "point_6": "tuzilish bayoni..."
}}"""
            elif language == "ru":
                prompt = f"""Дайте подробное академическое описание следующих 6 пунктов для курсовой работы по теме "{topic}". 
ВНИМАНИЕ: Избегайте общих фраз. Каждый пункт должен быть глубоко связан именно с темой "{topic}", раскрывая её научные и практические аспекты.

Пункты (минимум 40-50 слов каждый):
1. Предмет курсовой работы (какие именно стороны темы изучаются?).
2. Объект курсовой работы (к какой области или понятию относится тема?).
3. Степень изученности темы (насколько глубоко эта тема изучена на данный момент?).
4. Цель курсовой работы (основной ожидаемый результат исследования?).
5. Задачи курсовой работы (напишите по пунктам шаги для достижения цели).
6. Структура курсовой работы (краткое описание введения, глав и заключения).

Ответьте в формате JSON:
{{
  "point_1": "глубокий анализ предмета темы...",
  "point_2": "подробное описание объекта темы...",
  "point_3": "анализ научной степени изученности...",
  "point_4": "описание конкретной цели...",
  "point_5": "1. ...\\n2. ...\\n3. ...",
  "point_6": "описание структуры..."
}}"""
            else:
                prompt = f"""Provide detailed academic descriptions for the following 6 points for a course work on "{topic}".
ATTENTION: Avoid general phrases. Each point must be deeply connected specifically to the topic "{topic}", revealing its scientific and practical aspects.

Points (at least 40-50 words each):
1. Subject of the course work (what specific aspects of the topic are studied?).
2. Object of the course work (what area or concept does the topic belong to?).
3. Degree of study of the topic (how well is this topic studied currently?).
4. Goal of the course work (what is the main expected result of the study?).
5. Tasks of the course work (write point by point steps to achieve the goal).
6. Structure of the course work (brief description of introduction, chapters, and conclusion).

Respond in JSON format:
{{
  "point_1": "deep analysis of the topic subject...",
  "point_2": "detailed description of the topic object...",
  "point_3": "scientific study degree analysis...",
  "point_4": "specific goal description...",
  "point_5": "1. ...\\n2. ...\\n3. ...",
  "point_6": "structure description..."
}}"""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=0.7
            )
            
            content_str = response.strip()
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            if content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            
            return json.loads(content_str.strip())
            
        except Exception as e:
            logger.error(f"Error generating intro points: {e}")
            return {f"point_{i}": "" for i in range(1, 7)}

    async def _generate_course_intro(self, topic: str, language: str) -> str:
        """Generate course work introduction (~600 words for 2 pages)"""
        try:
            target_lang_name = "Russian" if language == "ru" else "English" if language == "en" else "Uzbek"
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi kurs ishi uchun ilmiy va tahliliy kirish qismini yozing.
DIQQAT: Umumiy va yuzaki gaplardan butunlay voz keching. Kirish qismi aynan "{topic}" mavzusining mohiyatini ochib berishi, uning bugungi kundagi dolzarbligini ilmiy asoslar bilan tushuntirishi kerak.

600-700 so'z yozing. Quyidagilarni chuqur tahlil qiling:
- Mavzuning dolzarbligi: Nima uchun bu mavzu bugungi kunda muhim? Qanday muammolarni hal qiladi?
- Tadqiqotning ilmiy va amaliy ahamiyati: Bu ish kimlar uchun foydali?
- Mavzuning qisqacha tarixi yoki nazariy asosi.

Professional akademik uslubda yozing. Faqat oddiy matn, markdown ishlatmang."""
            else:
                prompt = f"""Write a scientific and analytical introduction for a course work on the topic: "{topic}".
THE ENTIRE TEXT MUST BE IN {target_lang_name.upper()} LANGUAGE. 
ATTENTION: Completely avoid general and superficial phrases. The introduction must reveal the essence specifically of the topic, explaining its relevance in modern conditions with scientific justification.

600-700 words. Deeply analyze:
- Relevance of the topic: Why is this topic important today? What problems does it solve?
- Scientific and practical significance of the study: Who benefits from this work?
- Brief history or theoretical basis of the topic.

Professional academic style. Only plain text, no markdown."""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an academic writer specializing in course work introductions."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2500,
                temperature=0.7
            )
            
            return clean_text(response.strip())
            
        except Exception as e:
            logger.error(f"Error generating course intro: {e}")
            return ""

    async def _generate_course_conclusion(self, topic: str, language: str) -> str:
        """Generate course work conclusion (~400 words)"""
        try:
            target_lang_name = "Russian" if language == "ru" else "English" if language == "en" else "Uzbek"
            if language == "uz":
                prompt = f""""{topic}" mavzusidagi kurs ishi uchun xulosa yozing.

400-500 so'z. Quyidagilarni qamrab oling:
- Asosiy topilmalar va natijalar
- Tadqiqot xulosalari
- Amaliy tavsiyalar
- Kelajakda tadqiq qilish yo'nalishlari

Professional akademik uslubda yozing."""
            else:
                prompt = f"""Write a scientific conclusion for a course work on the topic: "{topic}".
THE ENTIRE TEXT MUST BE IN {target_lang_name.upper()} LANGUAGE. 

400-500 words. Cover:
- Main findings and results
- Research conclusions
- Practical recommendations
- Directions for future research

Professional academic style."""

            response = await self._make_request(
                messages=[
                    {"role": "system", "content": "You are an academic writer specializing in course work conclusions."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.7
            )
            
            return clean_text(response.strip())
            
        except Exception as e:
            logger.error(f"Error generating course conclusion: {e}")
            return ""

    async def _generate_footnote(self, topic: str, context: str, language: str) -> str:
        """Generate a footnote reference for a subsection"""
        try:
            if language == "uz":
                prompt = f""""{topic}" mavzusi, "{context}" konteksti uchun bitta akademik snoska (footnote) yarating.

Masalan:
Karimov I.A. "Yuksak ma'naviyat – yengilmas kuch". Toshkent: Ma'naviyat, 2008. 45-bet.

Faqat bitta manba yarating. Real ko'rinishda bo'lsin."""
            elif language == "ru":
                prompt = f"""Создайте одну академическую сноску для темы "{topic}", контекст "{context}".

Пример:
Иванов А.Б. "Современные технологии". Москва: Наука, 2020. С. 45.

Создайте только одну ссылку. Должна выглядеть реалистично."""
            else:
                prompt = f"""Create one academic footnote for topic "{topic}", context "{context}".

Example:
Smith, J. "Modern Technologies". New York: Academic Press, 2020. p. 45.

Create only one reference. Should look realistic."""

            response = await self._make_request(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.8
            )
            
            return clean_text(response.strip())
            
        except Exception as e:
            logger.error(f"Error generating footnote: {e}")
            return ""
