import aiohttp
import asyncio
import os
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class PexelsService:
    """Service for working with Pexels API to get images for presentations"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.pexels.com/v1"
        self.headers = {
            "Authorization": api_key
        }
    
    async def search_images(self, query: str, per_page: int = 5) -> List[Dict]:
        """Search for images on Pexels"""
        try:
            url = f"{self.base_url}/search"
            params = {
                "query": query,
                "per_page": min(per_page, 80),  # Pexels max is 80
                "orientation": "landscape"  # Better for presentations
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("photos", [])
                    else:
                        logger.error(f"Pexels API error: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error searching images: {e}")
            return []
    
    async def download_image(self, image_url: str, filename: str) -> Optional[str]:
        """Download image and save to file"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        content = await response.read()
                        
                        # Ensure temp directory exists
                        os.makedirs("temp", exist_ok=True)
                        filepath = f"temp/{filename}"
                        
                        with open(filepath, "wb") as f:
                            f.write(content)
                        
                        return filepath
                    else:
                        logger.error(f"Failed to download image: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None
    
    def get_image_url(self, photo: Dict, size: str = "medium") -> str:
        """Get image URL in specified size"""
        sizes = photo.get("src", {})
        
        # Priority order for sizes
        size_priority = {
            "small": ["small", "tiny", "medium", "large"],
            "medium": ["medium", "small", "large", "large2x"],
            "large": ["large", "large2x", "medium", "original"]
        }
        
        for preferred_size in size_priority.get(size, ["medium"]):
            if preferred_size in sizes:
                return sizes[preferred_size]
        
        # Fallback to any available size
        return list(sizes.values())[0] if sizes else ""
    
    async def get_smart_images_for_slides(self, slide_topics: List[str], images_per_topic: int = 1) -> Dict[str, List[str]]:
        """Get relevant images for each slide topic"""
        results = {}
        
        for topic in slide_topics:
            # Use the topic as search query
            images = await self.search_images(topic, images_per_topic)
            
            image_urls = []
            for photo in images[:images_per_topic]:
                url = self.get_image_url(photo, "medium")
                if url:
                    image_urls.append(url)
            
            results[topic] = image_urls
            
            # Small delay to respect rate limits
            await asyncio.sleep(0.1)
        
        return results
    
    def get_attribution_text(self, photo: Dict) -> str:
        """Get proper attribution text for the photo"""
        photographer = photo.get("photographer", "Unknown")
        photo_url = photo.get("url", "")
        return f"Photo by {photographer} on Pexels"