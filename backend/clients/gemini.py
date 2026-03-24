"""
Centralized Google Gemini client configuration via LangChain.
Provides ChatModel and Embeddings instances.
"""
from functools import lru_cache

import google.auth
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
import structlog

from config import settings


_PLACEHOLDER_API_KEYS = {
    "",
    "your-google-api-key",
    "replace-with-your-google-api-key",
}
_FALLBACK_CHAT_MODEL = "gemini-2.5-flash"
logger = structlog.get_logger()


def _is_configured_api_key(value: str | None) -> bool:
    key = (value or "").strip()
    if not key:
        return False
    lowered = key.lower()
    if lowered in _PLACEHOLDER_API_KEYS:
        return False
    if "your-google-api-key" in lowered:
        return False
    return True


@lru_cache(maxsize=1)
def _resolve_genai_auth_kwargs() -> dict:
    mode = settings.GOOGLE_GENAI_AUTH_MODE.strip().lower()
    api_key = (settings.GOOGLE_API_KEY or "").strip()

    if mode not in {"auto", "api_key", "adc"}:
        raise ValueError("GOOGLE_GENAI_AUTH_MODE must be one of: auto, api_key, adc")

    if mode in {"auto", "api_key"} and _is_configured_api_key(api_key):
        return {"google_api_key": api_key}

    if mode == "api_key":
        raise RuntimeError("GOOGLE_API_KEY is not configured")

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/generative-language"]
    )
    return {"credentials": credentials}


def ensure_genai_auth_configured() -> None:
    """Raise an exception when Gemini auth is not configured correctly."""
    _resolve_genai_auth_kwargs()


def _normalize_chat_model(model: str) -> str:
    """
    Normalize configured chat model name.
    Falls back from known unsupported preview aliases.
    """
    configured = (model or "").strip()
    if not configured:
        return _FALLBACK_CHAT_MODEL

    # LangChain accepts plain model IDs; keep them normalized.
    normalized = configured.removeprefix("models/")

    # Defensive fallback for deprecated/unsupported preview aliases.
    if normalized == "gemini-3.0-flash-preview":
        logger.warning(
            "Unsupported Gemini chat model configured; using fallback",
            configured_model=configured,
            fallback_model=_FALLBACK_CHAT_MODEL,
        )
        return _FALLBACK_CHAT_MODEL

    return normalized


@lru_cache(maxsize=1)
def get_llm() -> ChatGoogleGenerativeAI:
    """Get the configured Gemini chat model (singleton)."""
    return ChatGoogleGenerativeAI(
        model=_normalize_chat_model(settings.GEMINI_MODEL),
        temperature=settings.TEMPERATURE,
        max_output_tokens=settings.MAX_OUTPUT_TOKENS,
        **_resolve_genai_auth_kwargs(),
    )


@lru_cache(maxsize=1)
def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Get the configured Gemini embeddings model (singleton)."""
    return GoogleGenerativeAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        **_resolve_genai_auth_kwargs(),
    )
