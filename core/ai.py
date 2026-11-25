"""Thin wrapper around the LLM provider (Google Gemini).

Every AI call in the project goes through :func:`generate_text`, so switching
provider or mocking in tests only touches this module.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class AIError(Exception):
    """Raised when the AI provider is not configured or the call fails."""


def generate_text(prompt: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise AIError("GEMINI_API_KEY não configurada. Defina a variável de ambiente para usar a IA.")
    try:
        from google import genai

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(model=settings.GEMINI_MODEL, contents=prompt)
    except Exception as exc:  # network / quota / auth errors from the SDK
        logger.exception("AI generation failed")
        raise AIError(f"Falha ao consultar a IA: {exc}") from exc
    text = (response.text or "").strip()
    if not text:
        raise AIError("A IA retornou uma resposta vazia.")
    return text
