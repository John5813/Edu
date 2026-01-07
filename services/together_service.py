import os
import logging
import aiohttp
import asyncio
from typing import Optional, Dict
from together import Together

logger = logging.getLogger(__name__)

class TogetherImageService:
    """Service for generating images using Together AI FLUX models"""
    
    def __init__(self):
        self.api_key = os.getenv("TOGETHER_API_KEY")
        if not self.api_key:
            raise ValueError("TOGETHER_API_KEY environment variable is required")
        self.client = Together(api_key=self.api_key)
        self.model = "black-forest-labs/FLUX.1-schnell"
    
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
        """Generate image for presentation slide
        
        Args:
            topic: Main presentation topic
            slide_title: Title of current slide
            language: Language for any text in image (uz, ru, en)
            text_overlay: Text to appear in the image (in user's language)
        
        Returns:
            Path to generated image
        """
        prompt = self._create_detailed_prompt(topic, slide_title, language, text_overlay)
        return await self.generate_image(prompt, aspect_ratio="16:9")
    
    async def generate_cover_image(self, topic: str, language: str) -> Optional[str]:
        """Generate cover image for presentation (50% of slide, left side)
        
        Args:
            topic: Presentation topic
            language: Language for text overlay
        
        Returns:
            Path to generated image
        """
        prompt = self._create_cover_prompt(topic, language)
        return await self.generate_image(prompt, aspect_ratio="1:1")
    
    async def generate_panoramic_image(self, topic: str, slide_title: str, language: str) -> Optional[str]:
        """Generate panoramic image (21:9 aspect ratio) for horizontal slides
        
        Args:
            topic: Presentation topic
            slide_title: Slide title for context
            language: Language for text
        
        Returns:
            Path to generated image
        """
        prompt = self._create_panoramic_prompt(topic, slide_title, language)
        return await self.generate_image(prompt, aspect_ratio="16:9")
    
    def _create_detailed_prompt(self, topic: str, slide_title: str, language: str, text_overlay: str = None) -> str:
        """Create concise 20-25 word prompt for natural professional image"""
        
        return f"Professional natural photograph illustrating {slide_title}, related to {topic}. Clean modern aesthetic, soft lighting, high quality stock photo style, no text."
    
    def _get_topic_visual_context(self, topic: str, slide_title: str) -> str:
        """Generate concise visual context for slide"""
        return f"Natural professional photo of {slide_title} concept, {topic} theme. Realistic, clean composition, bright colors, no text or labels."
    
    def _create_cover_prompt(self, topic: str, language: str) -> str:
        """Create concise 20-25 word cover image prompt - natural, no text"""
        
        return f"Stunning professional photograph representing {topic}. Modern elegant aesthetic, natural lighting, vibrant colors, clean background, high quality, absolutely no text."

    def _create_panoramic_prompt(self, topic: str, slide_title: str, language: str) -> str:
        """Create concise panoramic image prompt - natural, no text"""
        
        return f"Wide panoramic natural photograph of {slide_title}, {topic} context. Professional quality, bright modern style, clean composition, no text or watermarks."

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
