"""
llm.py — Multi-LLM Robust Fallback Factory
Creates a chain of LLMs. If the primary fails (e.g. rate limit, bad API key), 
LangChain automatically retries with the next one in the fallback sequence.
"""

from functools import lru_cache
import logging
from langchain_core.language_models import BaseChatModel
from backend.core.config import settings

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """
    Returns a composite LLM instance that falls back gracefully across 
    Gemini -> OpenAI -> Groq -> DeepSeek.
    """
    
    models = []

    # 1. Gemini
    if settings.gemini_api_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        models.append(ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=0.3,
            max_retries=3,
        ))

    # 2. OpenAI
    if settings.openai_api_key:
        from langchain_openai import ChatOpenAI
        models.append(ChatOpenAI(
            model=settings.openai_model,
            openai_api_key=settings.openai_api_key,
            temperature=0.3,
            max_retries=3,
        ))

    # 3. Groq
    if settings.groq_api_key:
        from langchain_groq import ChatGroq
        models.append(ChatGroq(
            model=settings.groq_model,
            groq_api_key=settings.groq_api_key,
            temperature=0.3,
            max_retries=3,
        ))

    # 4. DeepSeek
    if settings.deepseek_api_key:
        from langchain_openai import ChatOpenAI
        models.append(ChatOpenAI(
            model=settings.deepseek_model,
            openai_api_key=settings.deepseek_api_key,
            openai_api_base="https://api.deepseek.com/v1",
            temperature=0.3,
            max_retries=3,
        ))

    if not models:
        raise ValueError("No API keys found. Please set at least one API key in .env")

    # Chain the models together using LangChain's fallback mechanism
    main_model = models[0]
    if len(models) > 1:
        # with_fallbacks intercepts errors from the primary model and tries the next ones
        main_model = main_model.with_fallbacks(models[1:])
        
    return main_model
