"""
Shared LLM factory for all LLM layers (L3, L5, L9, L10).

Usage:
    from src.llm.client import make_llm
    llm = make_llm()                         # uses provider + model from env
    llm = make_llm(provider="openai")        # explicit provider
    llm = make_llm(provider="gemini", model="gemini-2.5-flash")
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Walk up from this file to find .env (repo root), fallback silently if not found
_env_file = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_file)


def make_llm(
    provider: str = "openai",
    model: str | None = None,
    base_url: str | None = None,
):
    """Return a LangChain chat model for the given provider."""
    provider = provider.lower().strip()

    if provider == "openai":
        return ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-5-nano"),
            api_key=os.getenv("OPENAI_API_KEY_S_M_R") or os.getenv("OPENAI_API_KEY"),
        )

    if provider == "lmstudio":
        return ChatOpenAI(
            model=model or os.getenv("LMSTUDIO_MODEL", "qwen/qwen2.5-coder-14b"),
            api_key=os.getenv("LMSTUDIO_API_KEY", "lm-studio"),
            base_url=base_url or os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"),
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
            api_key=os.getenv("GOOGLE_API_KEY"),
        )

    raise ValueError(f"Unknown provider: {provider!r}. Use openai, lmstudio, or gemini.")
