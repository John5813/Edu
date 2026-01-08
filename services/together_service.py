import os
import logging
import aiohttp
import asyncio
import base64
from typing import Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class TogetherImageService:
    """Service for generating images using OpenRouter API"""
    
    def __init__(self):
        self.api_key = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY")
        self.base_url = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        
        if not self.api_key:
            raise ValueError("AI_INTEGRATIONS_OPENROUTER_API_KEY environment variable is required")
        
        self.ai_client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self.ai_model = "deepseek/deepseek-chat"
        self.image_model = "google/gemini-2.5-flash-image-preview"
    
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
        """Generate image using OpenRouter API with Gemini
        
        Args:
            prompt: English description of the image
            aspect_ratio: Image aspect ratio (ignored for now)
            steps: Ignored for OpenRouter
        
        Returns:
            Path to downloaded image or None if failed
        """
        try:
            logger.info(f"Generating image with OpenRouter, prompt: {prompt[:100]}...")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://replit.com",
                "X-Title": "EduBot"
            }
            
            payload = {
                "model": self.image_model,
                "modalities": ["image", "text"],
                "messages": [
                    {
                        "role": "user",
                        "content": f"Generate a high-quality professional image: {prompt}. No text, no letters, no words in the image."
                    }
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"OpenRouter API error: {response.status} - {error_text}")
                        return None
                    
                    result = await response.json()
                    
                    message = result.get('choices', [{}])[0].get('message', {})
                    
                    if 'images' in message and message['images']:
                        image_data = message['images'][0]
                        
                        if ',' in image_data:
                            image_data = image_data.split(',')[1]
                        
                        filename = f"openrouter_image_{hash(prompt) % 100000}.png"
                        filepath = os.path.join("temp", filename)
                        os.makedirs("temp", exist_ok=True)
                        
                        with open(filepath, "wb") as f:
                            f.write(base64.b64decode(image_data))
                        
                        logger.info(f"Image generated and saved: {filepath}")
                        return filepath
                    
                    content = message.get('content', '')
                    if 'data:image' in content:
                        import re
                        match = re.search(r'data:image/[^;]+;base64,([A-Za-z0-9+/=]+)', content)
                        if match:
                            image_data = match.group(1)
                            filename = f"openrouter_image_{hash(prompt) % 100000}.png"
                            filepath = os.path.join("temp", filename)
                            os.makedirs("temp", exist_ok=True)
                            
                            with open(filepath, "wb") as f:
                                f.write(base64.b64decode(image_data))
                            
                            logger.info(f"Image extracted from content: {filepath}")
                            return filepath
                    
                    logger.error(f"No image data in response: {result}")
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
