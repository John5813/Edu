# services/ai_coursework.py
import json
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# This module provides a helper to generate structured course work content from AI.
# It is intentionally standalone to avoid modifying the large existing AIService class.

async def generate_course_work_content(ai_client, topic: str, chapters: int, language: str) -> Dict:
    """
    Generate structured course work content using the provided ai_client helper.
    ai_client is expected to expose an async _make_request(messages, max_tokens, temperature) method
    that returns a text response (string). If you have an existing AIService instance, pass it.

    Returns a dict with keys: title, chapters (list), references (list), footnotes (list).
    """
    try:
        lang_name = "Uzbek" if language == "uz" else "Russian" if language == "ru" else "English"
        prompt = (
            f'Create a structured course work for the topic "{topic}".\n'
            f'Output MUST be valid JSON with keys: title, chapters (array), references (array), footnotes (array).\n'
            f'Each chapter must contain title and subsections (array). Each subsection must contain title, text, and optional footnotes (array of objects with id and text).\n'
            f'Inline citations inside subsection text should be in the form [1], [2], etc. The footnotes array should include corresponding entries.\n'
            f'Language: {lang_name}. Provide professional academic prose appropriate for course work.\n'
            f'Example fragment:\n{{"chapters": [{{"title":"...","subsections":[{{"title":"...","text":"... [1] ...","footnotes":[{{"id":1,"text":"..."}}]}}]}}]}}\n'
        )

        response = await ai_client._make_request(messages=[{"role":"user","content":prompt}], max_tokens=4000, temperature=0.7)
        content_str = response.strip()
        # strip common code fences
        if content_str.startswith("```json"):
            content_str = content_str[7:]
        if content_str.startswith("```"):
            content_str = content_str[3:]
        if content_str.endswith("```"):
            content_str = content_str[:-3]

        parsed = json.loads(content_str.strip())

        # Normalise
        parsed.setdefault("title", topic)
        parsed.setdefault("chapters", [])
        parsed.setdefault("references", [])
        parsed.setdefault("footnotes", [])

        for ch in parsed["chapters"]:
            ch.setdefault("title", "")
            ch.setdefault("subsections", [])
            for sub in ch["subsections"]:
                sub.setdefault("title", "")
                sub.setdefault("text", "")
                sub.setdefault("footnotes", [])

        return parsed

    except Exception as e:
        logger.exception("Failed to generate structured course work: %s", e)
        # Fallback minimal structure
        return {
            "title": topic,
            "chapters": [
                {"title": f"Chapter {i+1}", "subsections": [{"title": "Subsection 1", "text": "", "footnotes": []}]} for i in range(max(1, chapters))
            ],
            "references": [],
            "footnotes": []
        }