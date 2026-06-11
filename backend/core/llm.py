"""
llm.py — LLM factory supporting Gemini, OpenAI, and Groq.
Swap providers by changing LLM_PROVIDER in your .env file.
"""
from functools import lru_cache
from langchain_core.language_models import BaseChatModel
from backend.core.config import settings


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Return a cached LLM instance based on LLM_PROVIDER in .env"""
    provider = settings.llm_provider.lower()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set in your .env file.")
        return ChatGoogleGenerativeAI(
            model=settings.llm_model or "gemini-1.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.3,
            convert_system_message_to_human=True,
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set in your .env file.")
        return ChatOpenAI(
            model=settings.llm_model or "gpt-4o-mini",
            openai_api_key=settings.openai_api_key,
            temperature=0.3,
        )

    elif provider == "groq":
        from langchain_groq import ChatGroq
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set in your .env file.")
        return ChatGroq(
            model=settings.llm_model or "llama-3.1-8b-instant",
            groq_api_key=settings.groq_api_key,
            temperature=0.3,
        )

    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: '{provider}'. "
            "Set LLM_PROVIDER to one of: gemini | openai | groq"
        )
