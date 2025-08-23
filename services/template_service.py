"""
Template Service for Presentation Backgrounds
Manages background template selection and application
"""

import os
import logging
from typing import Dict, List, Optional
from pptx import Presentation
from pptx.util import Inches as PptxInches, Pt as PptxPt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

logger = logging.getLogger(__name__)

class TemplateService:
    """Manages presentation background templates"""
    
    def __init__(self):
        self.templates = {
            # Group 1 - Educational/Academic
            'template_1': {
                'name': 'Ta\'lim Anjumani',
                'file': 'word-image-3281-1-13_1755920914578.png',
                'colors': {'title': RGBColor(0, 51, 102), 'text': RGBColor(51, 51, 51)}
            },
            'template_2': {
                'name': 'Ko\'k Geometrik',
                'file': 'sinie-tonirovannye-nabor-treugol-nyh-listov-bumagi-s-kopiei-prostranstva_1755920914625.jpg',
                'colors': {'title': RGBColor(0, 102, 204), 'text': RGBColor(0, 51, 102)}
            },
            'template_3': {
                'name': 'Texnologiya',
                'file': 'fd5e01cf1a9b881f0d16f2c875affac0_1755920914733.jpg',
                'colors': {'title': RGBColor(0, 153, 255), 'text': RGBColor(0, 102, 153)}
            },
            'template_4': {
                'name': 'Lola Gullari',
                'file': 'e7d2d0af98b5e8a58374d63335615b86_1755920914800.jpg',
                'colors': {'title': RGBColor(153, 0, 51), 'text': RGBColor(102, 51, 51)}
            },
            'template_5': {
                'name': 'Gul Naqshli',
                'file': 'e2cc2f46ec22c6a2455670d6f4d57cab_1755920914878.jpg',
                'colors': {'title': RGBColor(153, 51, 153), 'text': RGBColor(102, 51, 102)}
            },
            
            # Group 2 - Modern/Business
            'template_6': {
                'name': 'Rangli Olti Burchak',
                'file': 'b9b1f45236e32dec0cc8a9c27af3ec28_1755920914951.jpg',
                'colors': {'title': RGBColor(255, 102, 0), 'text': RGBColor(51, 51, 51)}
            },
            'template_7': {
                'name': 'Minimalist',
                'file': 'b67624d21e2e68a3433ef46cf7dcbb90_1755920915023.jpg',
                'colors': {'title': RGBColor(0, 102, 153), 'text': RGBColor(51, 51, 51)}
            },
            'template_8': {
                'name': 'Yashil Gradient',
                'file': 'abstraktnoe-bumaznoe-ponatie-fona_1755920915096.jpg',
                'colors': {'title': RGBColor(0, 153, 51), 'text': RGBColor(0, 102, 51)}
            },
            'template_9': {
                'name': 'Ko\'k To\'lqin',
                'file': 'abstract-blue-background-poster-with-wave-curve-dynamic-blue-white-business-presentation-background-with-modern-technology-network-concept-vector-illustration_181182-19573_1755920915171.jpg',
                'colors': {'title': RGBColor(0, 102, 204), 'text': RGBColor(0, 51, 102)}
            },
            'template_10': {
                'name': 'Biznes Professional',
                'file': 'abstract-blue-background-poster-with-dynamic-triangle-frame-border-blue-white-business-presentation-background-with-modern-technology-network-concept-vector-illustration_181182-19578_1755920915250.jpg',
                'colors': {'title': RGBColor(0, 51, 153), 'text': RGBColor(0, 51, 102)}
            },
            
            # Group 3 - Clean/Modern
            'template_11': {
                'name': 'Zamonaviy Ko\'k',
                'file': 'abstract-background-blue-white-gradient-modern-blue-abstract-geometric-rectangle-box-lines-background-presentation-design-banner-brochure-business-card_181182-30704_1755920915330.jpg',
                'colors': {'title': RGBColor(0, 102, 255), 'text': RGBColor(0, 51, 153)}
            },
            'template_12': {
                'name': 'Piksel Ko\'k',
                'file': 'a8aadcfffbbdac4e0269a15bb82dc6af_1755920915411.jpg',
                'colors': {'title': RGBColor(51, 153, 255), 'text': RGBColor(0, 102, 204)}
            },
            'template_13': {
                'name': 'Klassik Vintage',
                'file': '62379448511baea4b1ab68cd7a4654c3_1755920915493.jpg',
                'colors': {'title': RGBColor(102, 51, 0), 'text': RGBColor(51, 51, 51)}
            },
            'template_14': {
                'name': 'Yashil-Sariq',
                'file': '5700bf8cf3ba5273e88d43e954d8c0db_1755920915574.jpg',
                'colors': {'title': RGBColor(0, 102, 102), 'text': RGBColor(0, 51, 51)}
            },
            'template_15': {
                'name': 'Ish Stoli',
                'file': '534c62010f51fee8cb5f14028280f9c0_1755920915649.jpg',
                'colors': {'title': RGBColor(51, 51, 51), 'text': RGBColor(102, 102, 102)}
            },
            
            # Group 4 - Creative/Educational
            'template_16': {
                'name': 'Ta\'lim Elementlari',
                'file': '29_1755920915725.png',
                'colors': {'title': RGBColor(0, 153, 255), 'text': RGBColor(0, 102, 153)}
            },
            'template_17': {
                'name': 'Texno Ko\'k',
                'file': '23ecdb398882fb138389e9ecf8676363_1755920915811.jpg',
                'colors': {'title': RGBColor(0, 102, 255), 'text': RGBColor(0, 51, 153)}
            },
            'template_18': {
                'name': 'Yashil To\'lqin',
                'file': '200a00e49abe4c831ac600002b1e1dcd_1755920915881.jpg',
                'colors': {'title': RGBColor(0, 153, 102), 'text': RGBColor(0, 102, 51)}
            },
            'template_19': {
                'name': 'Bahor Ranglar',
                'file': '184c6f428e31410bd29e2abe04a6582c_1755920915948.jpg',
                'colors': {'title': RGBColor(255, 51, 102), 'text': RGBColor(102, 51, 51)}
            },
            'template_20': {
                'name': 'Klassik Oq',
                'file': None,  # Default white background
                'colors': {'title': RGBColor(0, 51, 102), 'text': RGBColor(51, 51, 51)}
            }
        }
    
    def get_template_groups(self) -> List[List[Dict]]:
        """Get templates grouped by 5"""
        templates_list = list(self.templates.items())
        groups = []
        
        for i in range(0, len(templates_list), 5):
            group = []
            for j in range(i, min(i + 5, len(templates_list))):
                template_id, template_data = templates_list[j]
                group.append({
                    'id': template_id,
                    'name': template_data['name'],
                    'file': template_data['file']
                })
            groups.append(group)
        
        return groups
    
    def apply_template_to_slide(self, slide, template_id: str):
        """Apply template background to a slide"""
        try:
            if template_id not in self.templates:
                template_id = 'template_20'  # Default
                
            template = self.templates[template_id]
            
            # Add background image if specified
            if template['file']:
                bg_path = os.path.join('attached_assets', template['file'])
                if os.path.exists(bg_path):
                    self._set_slide_background(slide, bg_path)
                else:
                    logger.warning(f"Background image not found: {bg_path}")
            
            return template
            
        except Exception as e:
            logger.error(f"Error applying template: {e}")
            return self.templates['template_20']  # Default
    
    def _set_slide_background(self, slide, image_path: str):
        """Set background image for a slide"""
        try:
            # Get slide dimensions
            prs = slide.part.presentation
            slide_width = prs.slide_width
            slide_height = prs.slide_height
            
            # Add image as background
            pic = slide.shapes.add_picture(
                image_path,
                0, 0,
                width=slide_width,
                height=slide_height
            )
            
            # Send picture to back
            slide.shapes._spTree.remove(pic._element)
            slide.shapes._spTree.insert(2, pic._element)
            
        except Exception as e:
            logger.error(f"Error setting slide background: {e}")
    
    def get_template_colors(self, template_id: str) -> Dict:
        """Get color scheme for a template"""
        template = self.templates.get(template_id, self.templates['template_20'])
        return template['colors']