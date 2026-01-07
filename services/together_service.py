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
        
        topic_context = self._get_topic_visual_context(topic, slide_title)
        
        base_prompt = f"""Stunning, ultra-professional presentation image.

MAIN SUBJECT: {topic_context}

VISUAL STYLE:
- Modern glass architecture with sleek lines, representing innovation and progress
- Blend of traditional and digital elements (e.g., silk fabric transitioning into fiber-optic cables)
- Professional photography style with cinematic lighting
- Rich, deep color palette: dark blues, golds, and whites
- Sunlight reflecting off surfaces creating dynamic highlights
- Symbols of growth, stability, and advancement

COMPOSITION:
- 16:9 aspect ratio optimized for presentations
- Clear focal point with balanced negative space for text overlay
- Depth of field creating professional bokeh effect
- Leading lines guiding viewer's eye

TECHNICAL QUALITY:
- 4K ultra high definition
- Sharp focus on main subject
- Professional color grading
- Studio-quality lighting with soft shadows"""

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
        """Generate rich visual context based on topic"""
        return f"""Create a compelling visual representation of "{slide_title}" within the context of "{topic}".

Key visual elements should include:
- Modern architectural elements (glass skyscrapers, digital infrastructure)
- Traditional cultural symbols blending with technology
- Abstract representations of data, growth, and innovation
- Professional business/educational environment
- Dynamic lighting showcasing advancement and modernity

The image should evoke: professionalism, innovation, cultural heritage meeting modern progress, and academic excellence."""
    
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
        """Create stunning panoramic/horizontal image prompt - always in English"""
        lang_name = {"uz": "Uzbek", "ru": "Russian", "en": "English"}.get(language, "Uzbek")
        
        return f"""Cinematic ultra-wide panoramic image for professional presentation.

SUBJECT: "{slide_title}" in context of "{topic}"

VISUAL ELEMENTS:
- Sweeping landscape view of modern Tashkent skyline
- Traditional architecture seamlessly blending with glass towers
- Flowing water features or fountain elements
- Green parks transitioning to urban development
- Symbolic representation of progress and tradition

PANORAMIC STYLE:
- 21:9 ultra-wide cinematic ratio
- Hollywood film-quality color grading
- Dramatic golden hour lighting
- Deep depth of field showing entire scene in focus
- Subtle motion blur suggesting dynamism

COMPOSITION:
- Horizontal flow from traditional (left) to modern (right)
- Upper 30% reserved for text overlay
- Leading lines drawing eye across entire width
- Balanced visual weight across the frame

TEXT INTEGRATION:
Elegant overlay text "{slide_title}" in {lang_name} language.
Positioned in clean upper area with subtle shadow for readability.

TECHNICAL:
- 4K resolution optimized for widescreen
- Professional color grading (teal and orange tones)
- Sharp focus with cinematic lens effects
- Studio-quality post-processing."""

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
