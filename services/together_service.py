import os
import aiohttp
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class TogetherService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.together.xyz/v1/images/generations"

    async def generate_image(self, prompt: str, filename: str, aspect_ratio: str = "1:1") -> Optional[str]:
        """Generate image using Together AI (Flux model)"""
        try:
            payload = {
                "model": "black-forest-labs/FLUX.1-schnell-Free",
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "steps": 4,
                "n": 1,
                "response_format": "b64_json"
            }
            
            # Handle aspect ratio for specific layouts
            if aspect_ratio == "21:9":
                payload["width"] = 1024
                payload["height"] = 448

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        import base64
                        image_data = base64.b64decode(data['data'][0]['b64_json'])
                        
                        temp_dir = "temp"
                        os.makedirs(temp_dir, exist_ok=True)
                        file_path = os.path.join(temp_dir, filename)
                        
                        with open(file_path, "wb") as f:
                            f.write(image_data)
                        return file_path
                    else:
                        logger.error(f"Together AI error: {resp.status} - {await resp.text()}")
                        return None
        except Exception as e:
            logger.error(f"Error in TogetherService: {e}")
            return None
