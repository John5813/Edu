import functools
import logging
import os
import aiohttp
import asyncio
import base64
import httpx
import time
import uuid
from typing import Optional, Dict
from together import Together
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class TogetherImageService:
    """Service for generating images using Together AI FLUX models"""
    
    def __init__(self):
        self.api_key = os.getenv("TOGETHER_API_KEY")
        if not self.api_key:
            raise ValueError("TOGETHER_API_KEY environment variable is required")
        self.client = Together(api_key=self.api_key)
        # Rasm modeli har xizmat uchun alohida tanlanadi (admin panel) —
        # qarang: `chosen_image_model`.
        
        self.ai_client = AsyncOpenAI(
            api_key=os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY") or "dummy-key",
            base_url=os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL")
        )
        # GPT-4o - rasm promptlari uchun (kuchliroq versiya)
        self.ai_model = "openai/gpt-4o"
    
    async def _generate_image_prompt(self, topic: str, slide_title: str) -> str:
        """Generate a context-aware English image prompt using topic + slide title."""
        try:
            prompt_request = (
                f"Generate a short, specific English image prompt for a presentation slide.\n\n"
                f"Presentation topic: \"{topic}\"\n"
                f"Slide section: \"{slide_title}\"\n\n"
                f"Rules:\n"
                f"1. The image MUST visually represent BOTH the main topic AND the slide section together.\n"
                f"2. Be very specific — mention real objects, places, or scenes directly related to \"{topic}\".\n"
                f"3. Maximum 25 words.\n"
                f"4. NO text, letters, numbers, or signs in the image.\n"
                f"5. Professional photography or realistic illustration style.\n\n"
                f"Output ONLY the prompt, nothing else."
            )

            response = await self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt_request}],
                max_tokens=120,
                temperature=0.7
            )

            generated_prompt = response.choices[0].message.content.strip()
            generated_prompt = generated_prompt.strip('"').strip("'")

            logger.info(f"Image prompt generated: {generated_prompt}")
            return generated_prompt

        except Exception as e:
            logger.error(f"Error generating image prompt: {e}")
            return f"Professional photograph related to {topic}, {slide_title}, realistic style, no text"
    
    async def _render(self, prompt: str, target: str, stem: str) -> Optional[str]:
        """Promptni rasmga aylantiradi va fayl yo'lini qaytaradi.

        Avval `target` xizmati uchun tanlangan model, u ishlamasa zaxira
        modellar sinaladi — mijoz to'lagan ishda rasmsiz qolmaslik muhimroq.
        """
        for model in await image_model_chain(target):
            response = await self._call_model(prompt, model)
            if response is None:
                continue
            path = await self._save_response(response, stem)
            if path:
                logger.info(f"Image generated with {model} ({target}): {path}")
                return path
            logger.error(f"No image data from {model}")
        return None

    async def _call_model(self, prompt: str, model: str):
        """Bitta modelga so'rov. Vaqtinchalik xatoda (429/5xx) qayta uradi,
        boshqa xatoda None qaytaradi — shunda keyingi modelga o'tiladi."""
        extra = {}
        steps = _model_steps(model)
        if steps:
            extra["steps"] = steps

        # Wrap the SDK call with a hard timeout (Together can hang on transient
        # backend issues) and a small retry loop for 429/5xx-style errors.
        async def _call():
            return await asyncio.to_thread(
                functools.partial(
                    self.client.images.generate,
                    prompt=prompt,
                    model=model,
                    n=1,
                    **extra,
                )
            )

        for attempt in range(3):
            try:
                return await asyncio.wait_for(_call(), timeout=60)
            except (asyncio.TimeoutError, Exception) as ex:
                msg = str(ex).lower()
                transient = isinstance(ex, asyncio.TimeoutError) or any(
                    s in msg for s in ("429", "rate", "timeout", "503", "502", "504", "temporar")
                )
                if not transient:
                    logger.error(f"Together image model {model} failed: {ex}")
                    _mark_unavailable(model, msg)
                    return None
                if attempt == 2:
                    logger.error(f"Together image model {model} kept failing: {ex}")
                    return None
                backoff = 1.5 * (2 ** attempt)
                logger.warning(f"Together image transient error ({model}, attempt {attempt+1}): {ex}; retrying in {backoff}s")
                await asyncio.sleep(backoff)
        return None

    async def _save_response(self, response, stem: str) -> Optional[str]:
        if not response.data:
            return None
        filename = f"{stem}_{uuid.uuid4().hex[:12]}.png"
        item = response.data[0]
        if getattr(item, "url", None):
            path = await self._download_image(item.url, filename)
            if path:
                return path
        if getattr(item, "b64_json", None):
            filepath = os.path.join("temp", filename)
            os.makedirs("temp", exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(item.b64_json))
            return filepath
        return None

    async def generate_image(self, prompt: str, aspect_ratio: str = "16:9", steps: int = 4,
                             target: str = "docs") -> Optional[str]:
        """Generate image using the Together AI model chosen for `target`.

        Args:
            prompt: English description of the image (detailed, high quality)
            aspect_ratio: Image aspect ratio (16:9 for slides, 21:9 for panoramic)
            steps: kept for compatibility; each model's own step count is used
            target: "docs", "presentation" or "premium" — whose model to use

        Returns:
            Path to downloaded image or None if failed
        """
        try:
            # Defence in depth: block NSFW / extremist prompts before they
            # reach Together's billable API.
            try:
                from utils.security import sanitize_image_prompt, strip_text_requests
                cleaned = sanitize_image_prompt(prompt)
                if cleaned is None:
                    logger.warning("Image prompt rejected by sanitizer; skipping generation")
                    return None
                # Arzon modellar harflarni buzib chizadi, shuning uchun promptdan
                # matn so'rovlari olib tashlanadi va taqiq qo'shiladi.
                prompt = strip_text_requests(cleaned)
            except Exception as _ex:
                logger.warning(f"Image prompt sanitizer unavailable: {_ex}")

            logger.info(f"Generating image ({target}) with prompt: {prompt[:100]}...")
            return await self._render(prompt, target, "together_image")

        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return None
    
    async def generate_slide_image(self, topic: str, slide_title: str, language: str, text_overlay: str = None) -> Optional[str]:
        """Oddiy taqdimot slaydi uchun rasm (rasmda matn bo'lmaydi)."""
        prompt = await self._generate_image_prompt(topic, slide_title)
        return await self.generate_image(prompt, aspect_ratio="16:9", target="presentation")
    
    async def generate_cover_image(self, topic: str, language: str) -> Optional[str]:
        """Oddiy taqdimot muqovasi uchun mavzuga mos rasm (rasmda matn yo'q)."""
        try:
            # Create prompt for beautiful topic-related image WITHOUT any text
            prompt = f"""Stunning professional photograph related to "{topic}".
Beautiful high-quality image with perfect lighting and composition.
Modern, clean aesthetic suitable for professional presentation cover.
Vibrant colors, sharp focus, professional photography style.
NO TEXT, NO WORDS, NO LETTERS in the image - purely visual.
The image should clearly represent the theme of {topic}.
Corporate presentation quality, inspiring and engaging visual."""

            logger.info("Generating cover image for presentation...")
            path = await self._render(prompt, "presentation", "cover_image")
            if path:
                return path
        except Exception as e:
            logger.error(f"Error generating cover image: {e}")
        # Fallback to regular image generation
        prompt = await self._generate_image_prompt(topic, topic)
        return await self.generate_image(prompt, aspect_ratio="1:1", target="presentation")
    
    async def generate_panoramic_image(self, topic: str, slide_title: str, language: str) -> Optional[str]:
        """Oddiy taqdimotning keng (panorama) slaydi uchun rasm."""
        prompt = await self._generate_image_prompt(topic, slide_title)
        return await self.generate_image(prompt, aspect_ratio="16:9", target="presentation")
    
    async def _download_image(self, image_url: str, filename: str) -> Optional[str]:
        """Download image from URL with timeout + small retry loop."""
        os.makedirs("temp", exist_ok=True)
        filepath = os.path.join("temp", filename)
        timeout = aiohttp.ClientTimeout(total=45, connect=10)
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(image_url) as response:
                        if response.status == 200:
                            content = await response.read()
                            with open(filepath, "wb") as f:
                                f.write(content)
                            return filepath
                        logger.error(f"Image download HTTP {response.status} (attempt {attempt+1})")
                        if response.status < 500:
                            return None
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                logger.warning(f"Image download error attempt {attempt+1}: {e}")
            except Exception as e:
                logger.error(f"Image download fatal: {e}")
                return None
            if attempt < 2:
                await asyncio.sleep(1.5 * (2 ** attempt))
        return None
    
    async def generate_flux_pro_image(
        self,
        topic: str,
        subsection_title: str,
        language: str = 'uz',
        image_type: str = 'infographic',
    ) -> tuple:
        """Hujjat (kurs ishi, referat va h.k.) uchun rasm — hujjatlar modeli bilan.

        Args:
            topic: Main course work topic
            subsection_title: Title of subsection
            language: Language (uz, ru, en)
            image_type: 'infographic' (technical diagrams, formulas, mechanisms)
                        or 'scene' (people applying the concepts)

        Returns:
            Tuple of (image_path, image_prompt) or (None, None) if failed
        """
        try:
            image_prompt = await self._generate_course_work_image_prompt(
                topic, subsection_title, language, image_type=image_type
            )

            logger.info(f"Generating {image_type} image for a document...")
            image_path = await self._render(image_prompt, "docs", f"course_work_{image_type}")
            if image_path:
                return image_path, image_prompt

            logger.error("No image data in Together AI response")
            return None, None

        except Exception as e:
            logger.error(f"Error generating course work {image_type} image: {e}")
            return None, None
    
    async def generate_infographic_prompt(
        self,
        topic: str,
        subsection_title: str,
        language: str = 'uz',
        image_type: str = 'infographic',
    ) -> str:
        """Generate a focused English image prompt for FLUX.2-pro.

        Ikkala tur ham REALISTIK fotosurat: infografika, vektor chizma yoki
        diagramma so'ralmaydi — diagrammalar hujjatga matplotlib bilan alohida
        qo'yiladi, rasm esa jonli suratdek ko'rinishi kerak.

        image_type='infographic': mavzuga oid real muhit/jihoz/obyekt fotosurati
            (odamsiz) — dokumental kadr.
        image_type='scene': mavzu bilan ishlayotgan odamlar fotosurati.
        """
        if image_type == 'infographic':
            style_instruction = (
                f"TYPE: Realistic documentary photograph — objects and environment, no people.\n"
                f"- Photograph the real equipment, materials, workplace or objects used in "
                f"'{subsection_title}' within the field of '{topic}'\n"
                f"- Style: photorealistic DSLR photo, 50mm lens, natural light, shallow depth of field\n"
                f"- NOT an infographic, NOT a diagram, NOT a chart, NOT vector art, NOT a 3D render, "
                f"NOT an illustration — a real photograph only\n"
                f"- NO people, NO faces\n"
                f"- NO text, NO letters, NO numbers, NO labels, NO watermarks\n"
                f"- Authentic colours, real textures, professional composition"
            )
            fallback = (
                f"Realistic documentary photograph of the real equipment and workplace used in "
                f"'{subsection_title}' related to '{topic}', photorealistic DSLR photo, natural light, "
                f"no people, no text, no letters, no diagram, no infographic, high quality"
            )
        else:
            style_instruction = (
                f"TYPE: Realistic documentary photograph with people.\n"
                f"- Show professionals or students actively working with or applying the concepts of '{subsection_title}'\n"
                f"- Examples: scientists in a lab, economists at a market, engineers at a factory, "
                f"programmers at computers, doctors with patients — choose what fits the topic\n"
                f"- Style: photorealistic DSLR photo, natural light, candid and authentic\n"
                f"- NOT an illustration, NOT vector art, NOT a 3D render, NOT an infographic\n"
                f"- Scene must feel authentic and directly relevant to '{topic}'\n"
                f"- NO text, NO letters, NO watermarks, NO written formulas\n"
                f"- Bright, well-lit, professional environment"
            )
            fallback = (
                f"Realistic photograph of professionals working with '{subsection_title}' concepts related to '{topic}', "
                f"people in a professional environment, photorealistic DSLR photo, natural light, "
                f"no text, no watermarks, no illustration, high quality"
            )

        prompt_request = (
            f"You are an expert at writing image prompts for AI image generators.\n"
            f"Academic document topic: \"{topic}\"\n"
            f"Section title: \"{subsection_title}\"\n\n"
            f"Write a single English image prompt (50-70 words) for this specific image:\n\n"
            f"{style_instruction}\n\n"
            f"Output ONLY the English prompt. No explanations, no quotes."
        )

        try:
            response = await self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt_request}],
                max_tokens=150,
                temperature=0.7
            )
            generated_prompt = response.choices[0].message.content.strip()
            generated_prompt = generated_prompt.strip('"').strip("'")
            logger.info(f"{image_type} prompt for '{subsection_title}': {generated_prompt}")
            return generated_prompt
        except Exception as e:
            logger.error(f"Error generating {image_type} prompt: {e}")
            return fallback

    async def _generate_course_work_image_prompt(
        self,
        topic: str,
        subsection_title: str,
        language: str = 'uz',
        image_type: str = 'infographic',
    ) -> str:
        """Generate image prompt for course work (delegates to generate_infographic_prompt)."""
        return await self.generate_infographic_prompt(topic, subsection_title, language, image_type=image_type)
    
    async def generate_image_description(self, topic: str, subsection_title: str, language: str = 'uz', image_path: str = None) -> str:
        """Generate detailed description text by analyzing the actual generated image with vision AI"""
        try:
            # If we have an image path, use vision to analyze it
            if image_path and os.path.exists(image_path):
                return await self._analyze_image_with_vision(image_path, topic, subsection_title, language)
            
            # Fallback to text-based description
            if language == 'uz':
                prompt = f"""{topic} mavzusidagi {subsection_title} bo'limi uchun rasm tavsifini yozing.
6-8 ta gap yozing (120-150 so'z). Ilmiy uslubda, akademik til."""
            elif language == 'ru':
                prompt = f"""Напишите описание изображения для раздела "{subsection_title}" по теме "{topic}".
6-8 предложений (120-150 слов). Научный стиль."""
            else:
                prompt = f"""Write an image description for "{subsection_title}" on topic "{topic}".
6-8 sentences (120-150 words). Scientific style."""
            
            response = await self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.7
            )
            
            description = response.choices[0].message.content.strip()
            
            # Remove last 2 sentences
            sentences = description.split('.')
            sentences = [s.strip() for s in sentences if s.strip()]
            if len(sentences) > 2:
                sentences = sentences[:-2]
            description = '. '.join(sentences) + '.'
            
            logger.info(f"Generated image description: {description[:50]}...")
            return description
            
        except Exception as e:
            logger.error(f"Error generating image description: {e}")
            if language == 'uz':
                return f"Ushbu rasmda {subsection_title} mavzusining asosiy elementlari ko'rsatilgan."
            elif language == 'ru':
                return f"На данном изображении представлены основные элементы темы {subsection_title}."
            else:
                return f"This image illustrates the main elements of {subsection_title}."
    
    async def _analyze_image_with_vision(self, image_path: str, topic: str, subsection_title: str, language: str) -> str:
        """Analyze actual image using vision AI and generate accurate description"""
        try:
            import base64
            
            # Read and encode the image
            with open(image_path, "rb") as img_file:
                image_data = base64.b64encode(img_file.read()).decode('utf-8')
            
            # Determine image type
            if image_path.endswith('.png'):
                mime_type = "image/png"
            else:
                mime_type = "image/jpeg"
            
            # Create vision prompt based on language
            if language == 'uz':
                vision_prompt = f"""Ushbu rasmni ko'rib chiqing va "{topic}" mavzusi bo'yicha tavsif yozing.

Qoidalar:
1. 6-8 ta gap yozing (120-150 so'z)
2. Rasmda ANIQ nima tasvirlanganini yozing
3. Ko'rgan narsalaringizni batafsil tavsiflang
4. Ilmiy uslubda, akademik til
5. Faqat tavsif matnini yozing

"Ushbu rasmda..." bilan boshlang."""
            elif language == 'ru':
                vision_prompt = f"""Проанализируйте это изображение и напишите описание по теме "{topic}".

Правила:
1. 6-8 предложений (120-150 слов)
2. Опишите ТОЧНО что изображено на картинке
3. Подробно опишите все что видите
4. Научный стиль, академический язык
5. Только текст описания

Начните с "На данном изображении..."."""
            else:
                vision_prompt = f"""Analyze this image and write a description for the topic "{topic}".

Rules:
1. 6-8 sentences (120-150 words)
2. Describe EXACTLY what is shown in the image
3. Describe everything you see in detail
4. Scientific style, academic language
5. Only description text

Start with "This image shows..."."""
            
            # Use vision-capable model (GPT-4o mini has vision)
            response = await self.ai_client.chat.completions.create(
                model="openai/gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vision_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}}
                    ]
                }],
                max_tokens=400,
                temperature=0.7
            )
            
            description = response.choices[0].message.content.strip()
            
            # Remove last 2 sentences
            sentences = description.split('.')
            sentences = [s.strip() for s in sentences if s.strip()]
            if len(sentences) > 2:
                sentences = sentences[:-2]
            description = '. '.join(sentences) + '.'
            
            logger.info(f"Vision analysis completed for image: {image_path[:30]}...")
            return description
            
        except Exception as e:
            logger.error(f"Error in vision analysis: {e}")
            # Fallback to basic description
            if language == 'uz':
                return f"Ushbu rasmda {subsection_title} mavzusining asosiy elementlari ko'rsatilgan."
            elif language == 'ru':
                return f"На данном изображении представлены основные элементы темы {subsection_title}."
            else:
                return f"This image illustrates the main elements of {subsection_title}."


# ── Har xizmat uchun tanlangan rasm modeli
#
# Tanlov bazada saqlanadi (admin panel), bu yerda qisqa muddat eslab
# qolinadi: har rasm uchun bazaga borilmasin, lekin admin almashtirgach
# bir daqiqa ichida hamma jarayonga yetib borsin.
IMAGE_TARGETS = ("docs", "presentation", "premium")
_CHOICE_TTL = 60.0
_choice_cache: Dict[str, tuple] = {}
# Hisobda ochiq bo'lmagan / nomi o'zgargan model har rasmda qayta
# sinalmasin — bir muddat chetlab o'tiladi.
_UNAVAILABLE_TTL = 600.0
_unavailable: Dict[str, float] = {}


def _catalog_entry(model_id: str) -> dict:
    from config import IMAGE_MODELS

    for info in IMAGE_MODELS.values():
        if info["id"].lower() == (model_id or "").lower():
            return info
    return {}


def _model_steps(model_id: str) -> Optional[int]:
    """Faqat `steps` ni qabul qiladigan modellarga qiymat qaytaradi."""
    steps = _catalog_entry(model_id).get("steps")
    if steps:
        return int(steps)
    if "schnell" in (model_id or "").lower():
        return 4
    return None


def _mark_unavailable(model_id: str, message: str) -> None:
    if any(s in message for s in ("model", "not found", "404", "not available",
                                  "unavailable", "access", "permission")):
        _unavailable[model_id] = time.monotonic() + _UNAVAILABLE_TTL


def _env_default(target: str) -> str:
    from config import IMAGE_MODELS, DEFAULT_IMAGE_MODEL

    if target == "premium" and os.getenv("PREMIUM_TOGETHER_IMAGE_MODEL"):
        return os.environ["PREMIUM_TOGETHER_IMAGE_MODEL"]
    return os.getenv("TOGETHER_IMAGE_MODEL") or IMAGE_MODELS[DEFAULT_IMAGE_MODEL]["id"]


async def chosen_image_model(target: str) -> str:
    """`target` xizmati uchun tanlangan model ID'si (bazadan, keshlab)."""
    from config import IMAGE_MODELS

    cached = _choice_cache.get(target)
    if cached and cached[1] > time.monotonic():
        return cached[0]
    model_id = _env_default(target)
    try:
        from database.database import Database

        key = await Database.get_image_model(target)
        if key in IMAGE_MODELS:
            model_id = IMAGE_MODELS[key]["id"]
    except Exception as e:
        logger.warning(f"Image model choice unavailable ({target}): {e}")
    _choice_cache[target] = (model_id, time.monotonic() + _CHOICE_TTL)
    return model_id


def forget_image_model_choice(target: Optional[str] = None) -> None:
    """Admin modelni almashtirgach keshni tozalaydi."""
    if target is None:
        _choice_cache.clear()
        _unavailable.clear()
    else:
        model = _choice_cache.pop(target, (None,))[0]
        _unavailable.pop(model, None)


async def image_model_chain(target: str) -> list:
    """Tanlangan model, keyin zaxiralar; yaqinda ishlamaganlar oxiriga."""
    from config import IMAGE_MODEL_FALLBACKS

    chain = []
    for model in [await chosen_image_model(target), *IMAGE_MODEL_FALLBACKS]:
        if model and model not in chain:
            chain.append(model)
    now = time.monotonic()
    alive = [m for m in chain if _unavailable.get(m, 0) <= now]
    return alive + [m for m in chain if m not in alive]


def list_account_image_models() -> Optional[set]:
    """Together hisobida ochiq rasm modellari (ID'lar, kichik harfda).

    Ro'yxatni olib bo'lmasa None — shunda chaqiruvchi tekshiruvsiz davom
    etadi. Bu so'rov bepul: rasm chizilmaydi.
    """
    api_key = os.getenv("TOGETHER_API_KEY")
    if not api_key:
        return None
    try:
        models = Together(api_key=api_key).models.list()
    except Exception as e:
        logger.warning(f"Together model list unavailable: {e}")
        return None
    ids = set()
    for model in models:
        kind = str(getattr(model, "type", "") or "").lower()
        if not kind or "image" in kind:
            ids.add(str(getattr(model, "id", "")).lower())
    return ids


_together_service_instance: "TogetherImageService | None" = None


def get_together_service() -> "TogetherImageService":
    """Return the shared TogetherImageService singleton."""
    global _together_service_instance
    if _together_service_instance is None:
        _together_service_instance = TogetherImageService()
        logger.info("TogetherImageService singleton created")
    return _together_service_instance


async def close_together_service() -> None:
    """Close the singleton's HTTP clients on bot shutdown."""
    global _together_service_instance
    if _together_service_instance is not None:
        try:
            await _together_service_instance.ai_client.close()
        except Exception:
            pass
        _together_service_instance = None
        logger.info("TogetherImageService singleton closed")
