import os
import logging
import aiohttp
import asyncio
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
        self.model = "black-forest-labs/FLUX.1-schnell"
        
        self.ai_client = AsyncOpenAI(
            api_key=os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY"),
            base_url=os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL")
        )
        # openrouter/auto - OpenRouter avtomatik eng yaxshi modelni tanlaydi
        self.ai_model = "openrouter/auto"
    
    async def _generate_image_prompt(self, slide_title: str) -> str:
        """Ask DeepSeek to create a creative image prompt from slide title"""
        try:
            prompt_request = f"""Menga "{slide_title}" bo'yicha rasm yaratish uchun qisqa va kreativ inglizcha prompt yozib ber.
Qoidalar:
1. prompt 20 ta so'zdan oshmasin.
2. Takrorlanadigan gaplar bo'lmasin.
3. Faqat 'Subject + Action + Style Professional + Lighting' formulasidan foydalan.
4. Rasmda hech qanday matn, yozuv yoki harf bo'lmasin.

Faqat promptni yoz, boshqa hech narsa yozma."""

            response = await self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt_request}],
                max_tokens=100,
                temperature=0.8
            )
            
            generated_prompt = response.choices[0].message.content.strip()
            generated_prompt = generated_prompt.strip('"').strip("'")
            
            logger.info(f"DeepSeek generated prompt: {generated_prompt}")
            return generated_prompt
            
        except Exception as e:
            logger.error(f"Error generating prompt from DeepSeek: {e}")
            return f"Professional photograph of {slide_title}, modern style, soft natural lighting, no text"
    
    async def generate_image(self, prompt: str, aspect_ratio: str = "16:9", steps: int = 4) -> Optional[str]:
        """Generate image using Together AI FLUX model
        
        Args:
            prompt: English description of the image (detailed, high quality)
            aspect_ratio: Image aspect ratio (16:9 for slides, 21:9 for panoramic)
            steps: Number of generation steps (4 for fast, more for quality)
        
        Returns:
            Path to downloaded image or None if failed
        """
        try:
            logger.info(f"Generating image with prompt: {prompt[:100]}...")
            
            response = await asyncio.to_thread(
                self.client.images.generate,
                prompt=prompt,
                model=self.model,
                steps=steps,
                n=1
            )
            
            if response.data and len(response.data) > 0:
                image_url = response.data[0].url
                if image_url:
                    filename = f"together_image_{hash(prompt) % 100000}.png"
                    image_path = await self._download_image(image_url, filename)
                    if image_path:
                        logger.info(f"Image generated and saved: {image_path}")
                        return image_path
                    
                if response.data[0].b64_json:
                    import base64
                    filename = f"together_image_{hash(prompt) % 100000}.png"
                    filepath = os.path.join("temp", filename)
                    os.makedirs("temp", exist_ok=True)
                    
                    with open(filepath, "wb") as f:
                        f.write(base64.b64decode(response.data[0].b64_json))
                    
                    logger.info(f"Image generated from base64: {filepath}")
                    return filepath
            
            logger.error("No image data in response")
            return None
            
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return None
    
    async def generate_slide_image(self, topic: str, slide_title: str, language: str, text_overlay: str = None) -> Optional[str]:
        """Generate image for presentation slide using DeepSeek-generated prompt
        
        Args:
            topic: Main presentation topic
            slide_title: Title of current slide
            language: Language (uz, ru, en)
            text_overlay: Ignored - no text in images
        
        Returns:
            Path to generated image
        """
        prompt = await self._generate_image_prompt(slide_title)
        return await self.generate_image(prompt, aspect_ratio="16:9")
    
    async def generate_cover_image(self, topic: str, language: str) -> Optional[str]:
        """Generate cover image using DeepSeek-generated prompt
        
        Args:
            topic: Presentation topic
            language: Language (ignored - no text)
        
        Returns:
            Path to generated image
        """
        prompt = await self._generate_image_prompt(topic)
        return await self.generate_image(prompt, aspect_ratio="1:1")
    
    async def generate_panoramic_image(self, topic: str, slide_title: str, language: str) -> Optional[str]:
        """Generate panoramic image using DeepSeek-generated prompt
        
        Args:
            topic: Presentation topic
            slide_title: Slide title for context
            language: Language (ignored - no text)
        
        Returns:
            Path to generated image
        """
        prompt = await self._generate_image_prompt(slide_title)
        return await self.generate_image(prompt, aspect_ratio="16:9")
    
    async def _download_image(self, image_url: str, filename: str) -> Optional[str]:
        """Download image from URL"""
        try:
            os.makedirs("temp", exist_ok=True)
            filepath = os.path.join("temp", filename)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(filepath, "wb") as f:
                            f.write(content)
                        return filepath
                    else:
                        logger.error(f"Failed to download image: HTTP {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None
