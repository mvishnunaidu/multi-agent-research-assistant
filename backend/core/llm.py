"""
llm.py — Multi-LLM Robust Fallback Factory

Creates a chain of LLMs using LangChain's fallback mechanism.
If the primary model fails (e.g., rate limit 429, API downtime, bad key),
LangChain automatically retries with the next available provider in the sequence.

Supported zero-cost / high-performance providers:
- Google Gemini (Gemini 2.5 Flash / Gemini 2.0 Flash) — 100% Free on AI Studio
- Groq Cloud (Llama 3.3 70B / Llama 3.1 8B) — 100% Free on Groq Console (~300 tok/s)
- OpenAI (GPT-4o-mini)
- DeepSeek (DeepSeek-V3 / DeepSeek-Chat)
"""

from functools import lru_cache
import logging
from typing import List, Dict
from langchain_core.language_models import BaseChatModel
from backend.core.config import settings

logger = logging.getLogger(__name__)


def get_configured_providers() -> List[str]:
    """
    Returns a list of LLM providers that currently have non-empty API keys configured.
    Evaluated dynamically so changes to settings are accurately reflected.
    """
    providers = []
    preferred = settings.llm_provider.lower().strip()

    all_active = []
    if settings.gemini_api_key.strip():
        all_active.append("gemini")
    if settings.groq_api_key.strip():
        all_active.append("groq")
    if settings.openai_api_key.strip():
        all_active.append("openai")
    if settings.deepseek_api_key.strip():
        all_active.append("deepseek")

    if preferred in all_active:
        providers.append(preferred)
        for p in all_active:
            if p != preferred:
                providers.append(p)
    else:
        providers = all_active

    return providers


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """
    Returns a composite LLM instance that prioritizes the configured primary provider
    and falls back gracefully across all other available providers.
    """
    provider_instances: Dict[str, BaseChatModel] = {}

    # 1. Google Gemini (100% Free Tier on Google AI Studio)
    if settings.gemini_api_key.strip():
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            provider_instances["gemini"] = ChatGoogleGenerativeAI(
                model=settings.gemini_model,
                google_api_key=settings.gemini_api_key,
                api_version="v1beta",
                convert_system_message_to_human=True,
                temperature=0.3,
                max_retries=1,
            )
            logger.info("Initialized Gemini LLM (%s with v1beta)", settings.gemini_model)
        except Exception as e:
            logger.warning("Could not initialize Gemini LLM: %s", e)

    # 2. Groq Cloud (100% Free Tier on Groq Console — Ultra-Fast LPU)
    if settings.groq_api_key.strip():
        try:
            from langchain_groq import ChatGroq
            provider_instances["groq"] = ChatGroq(
                model=settings.groq_model,
                groq_api_key=settings.groq_api_key,
                temperature=0.3,
                max_retries=2,
            )
            logger.info("Initialized Groq LLM (%s)", settings.groq_model)
        except Exception as e:
            logger.warning("Could not initialize Groq LLM: %s", e)

    # 3. OpenAI (GPT-4o-mini)
    if settings.openai_api_key.strip():
        try:
            from langchain_openai import ChatOpenAI
            provider_instances["openai"] = ChatOpenAI(
                model=settings.openai_model,
                openai_api_key=settings.openai_api_key,
                temperature=0.3,
                max_retries=2,
            )
            logger.info("Initialized OpenAI LLM (%s)", settings.openai_model)
        except Exception as e:
            logger.warning("Could not initialize OpenAI LLM: %s", e)

    # 4. DeepSeek (DeepSeek-Chat)
    if settings.deepseek_api_key.strip():
        try:
            from langchain_openai import ChatOpenAI
            provider_instances["deepseek"] = ChatOpenAI(
                model=settings.deepseek_model,
                openai_api_key=settings.deepseek_api_key,
                openai_api_base="https://api.deepseek.com/v1",
                temperature=0.3,
                max_retries=2,
            )
            logger.info("Initialized DeepSeek LLM (%s)", settings.deepseek_model)
        except Exception as e:
            logger.warning("Could not initialize DeepSeek LLM: %s", e)

    if not provider_instances:
        raise ValueError(
            "No LLM provider configured. Please provide at least one valid API key "
            "(GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or DEEPSEEK_API_KEY) in your .env file."
        )

    # Order models: put user's preferred provider first if configured, then the others
    ordered_models: List[BaseChatModel] = []
    preferred = settings.llm_provider.lower().strip()

    if preferred in provider_instances:
        ordered_models.append(provider_instances[preferred])

    for name, instance in provider_instances.items():
        if name != preferred:
            ordered_models.append(instance)

    # Chain models together using LangChain's fallback mechanism
    primary_model = ordered_models[0]
    if len(ordered_models) > 1:
        logger.info("Chaining primary LLM with %d fallback model(s)", len(ordered_models) - 1)
        return primary_model.with_fallbacks(ordered_models[1:], exceptions_to_handle=(Exception,))

    return primary_model
