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
        """Create highly detailed English prompt for professional image generation"""
        
        base_prompt = f"""Professional presentation image about "{slide_title}".

MAIN SUBJECT: Create a visual that directly represents "{slide_title}" in the context of "{topic}".

REQUIREMENTS:
- The image must clearly illustrate the concept "{slide_title}"
- Show relevant objects, symbols, or scenes specific to this topic
- Viewer should understand the subject matter immediately
- Educational and informative visual style

VISUAL STYLE:
- Clean, professional business/academic aesthetic
- High-quality stock photo style
- Bright, welcoming colors appropriate for presentations
- Modern and contemporary look

COMPOSITION:
- 16:9 aspect ratio for presentations
- Clear focal point
- Some space for text overlay if needed
- Balanced and professional layout

TECHNICAL QUALITY:
- High resolution, sharp and clear
- Professional lighting
- Clean background or relevant context"""

        if text_overlay:
            lang_name = {"uz": "O'zbek", "ru": "Русский", "en": "English"}.get(language, "O'zbek")
            base_prompt += f"""

TEXT OVERLAY (IMPORTANT):
Include stylized text "{text_overlay}" in {lang_name} language.
The text should be:
- Prominently displayed with elegant typography
- Artistically integrated into the design
- Using complementary colors that stand out
- Positioned for maximum visual impact"""

        return base_prompt
    
    def _get_topic_visual_context(self, topic: str, slide_title: str) -> str:
        """Generate rich visual context specifically focused on the slide title"""
        return f"""Create a professional image that directly illustrates the concept of "{slide_title}".

PRIMARY FOCUS: The image must visually represent "{slide_title}" - not generic architecture or technology.

SPECIFIC REQUIREMENTS:
- Show objects, symbols, or scenes that directly relate to "{slide_title}"
- If the title mentions a specific concept, show that concept visually
- Include relevant icons, diagrams, or metaphorical representations
- The viewer should immediately understand this image is about "{slide_title}"

CONTEXT: This is for a presentation about "{topic}", but the image should primarily illustrate the specific slide topic "{slide_title}".

STYLE: Clean, professional, educational, suitable for academic presentations."""
    
    def _create_cover_prompt(self, topic: str, language: str) -> str:
        """Create stunning cover slide image prompt - always in English for Together AI"""
        lang_name = {"uz": "Uzbek", "ru": "Russian", "en": "English"}.get(language, "Uzbek")
        
        return f"""Breathtaking, award-winning cover image for academic presentation about "{topic}".

VISUAL CONCEPT:
- Modern glass skyscraper in Tashkent with traditional Islamic geometric patterns
- Silk "Atlas" fabric gracefully merging into digital fiber-optic cables
- Golden sunlight reflecting off contemporary architecture
- Symbolic representation of Uzbekistan's blend of heritage and innovation

STYLE:
- Cinematic, Hollywood-quality visual effects
- Professional advertising photography style
- Rich contrast between traditional warmth and modern coolness
- Depth and dimension with 3D elements

COLORS:
- Deep sapphire blue and royal gold as primary
- Accents of traditional Uzbek ikat patterns
- Clean whites and silvers for modern elements
- Warm amber highlights from sunlight

COMPOSITION:
- Left 50% contains main visual imagery
- Right 50% clean gradient for title text placement
- Subtle particle effects adding dynamism
- Professional presentation-ready layout

TEXT ELEMENT:
Include elegant, stylized title text "{topic}" in {lang_name} language.
Typography should be modern, bold, and perfectly integrated.

QUALITY: 4K, photorealistic, studio lighting, professional retouching."""

    def _create_panoramic_prompt(self, topic: str, slide_title: str, language: str) -> str:
        """Create panoramic/horizontal image prompt focused on slide content"""
        
        return f"""Professional wide panoramic image illustrating "{slide_title}".

MAIN SUBJECT: Visual representation of "{slide_title}" within the topic of "{topic}".

REQUIREMENTS:
- Show a wide scene that clearly represents "{slide_title}"
- Include relevant objects, people, or environments for this concept
- Educational and informative - viewer should understand the subject
- Suitable for academic/business presentations

STYLE:
- Wide cinematic panoramic view (21:9 ratio)
- Professional stock photography quality
- Bright, clean, modern aesthetic
- Upper portion clear for potential text overlay

TECHNICAL:
- High resolution
- Sharp focus throughout
- Professional lighting
- Clean, uncluttered composition"""

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
