"""Loyiha ishi — soha spetsifikatsiyasi bo'yicha quriladigan hujjat turi."""

import logging

from .builder import ProjectWorkBuilder
from .content import ProjectContent, ProjectContentBuilder, SectionContent
from .specs import FIELDS, GENERIC_FIELD_KEY, GENERIC_LABEL, field_label

logger = logging.getLogger(__name__)

_content_builder = None
_document_builder = None


def get_content_builder() -> ProjectContentBuilder:
    global _content_builder
    if _content_builder is None:
        from services.ai_service import get_ai_service

        _content_builder = ProjectContentBuilder(get_ai_service())
    return _content_builder


def get_document_builder() -> ProjectWorkBuilder:
    global _document_builder
    if _document_builder is None:
        from services.document_service import get_document_service
        from services.together_service import get_together_service

        try:
            together = get_together_service()
        except Exception as e:
            logger.warning("Together yo'q, loyiha ishida sxema chizilmaydi: %s", e)
            together = None

        _document_builder = ProjectWorkBuilder(get_document_service(), together)
    return _document_builder


__all__ = [
    "FIELDS",
    "GENERIC_FIELD_KEY",
    "GENERIC_LABEL",
    "ProjectContent",
    "ProjectContentBuilder",
    "ProjectWorkBuilder",
    "SectionContent",
    "field_label",
    "get_content_builder",
    "get_document_builder",
]
