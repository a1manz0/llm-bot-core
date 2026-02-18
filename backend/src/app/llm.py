from __future__ import annotations

from typing import Iterable, List

from openai import AsyncOpenAI

from .config import Settings, get_settings

# OpenRouter для чата (singleton)
_openrouter_client: AsyncOpenAI | None = None
# OpenAI для эмбеддингов (singleton)
_openai_client: AsyncOpenAI | None = None


def get_openrouter_client(settings: Settings | None = None) -> AsyncOpenAI:
    """Получить или создать AsyncOpenAI клиент для OpenRouter (singleton)."""
    global _openrouter_client
    if _openrouter_client is None:
        s = settings or get_settings()
        if not s.openrouter_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY не задан. Укажите переменную окружения."
            )
        _openrouter_client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=s.openrouter_api_key,
        )
    return _openrouter_client


def get_openai_client(settings: Settings | None = None) -> AsyncOpenAI:
    """Получить или создать AsyncOpenAI клиент для OpenAI API (эмбеддинги)."""
    global _openai_client
    if _openai_client is None:
        s = settings or get_settings()
        if not s.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY не задан (нужен для эмбеддингов)."
            )
        _openai_client = AsyncOpenAI(api_key=s.openai_api_key)
    return _openai_client


async def generate_chat_completion(
    system_prompt: str,
    messages: list[dict],
) -> str:
    """
    Асинхронный вызов чат-модели через OpenRouter.

    messages — список вида [{"role": "user"|"assistant"|"system", "content": "..."}]
    """
    settings = get_settings()
    client = get_openrouter_client(settings)
    completion = await client.chat.completions.create(
        model=settings.openrouter_model,
        messages=[{"role": "system", "content": system_prompt}, *messages],
        temperature=0.3,
    )
    content = completion.choices[0].message.content
    return content or ""


async def summarize_progressively(
    previous_summary: str | None, new_messages: str
) -> str:
    """
    Progressive summarization по аналогии с ConversationSummaryMemory.

    - previous_summary: предыдущая сводка (может быть None)
    - new_messages: новая часть диалога в текстовом виде
    """
    system_prompt = (
        "Ты — ассистент, который делает краткие сводки диалогов.\n"
        "Твоя задача — обновлять существующую сводку с учётом новых сообщений.\n"
        "Отвечай только обновлённой сводкой, без пояснений."
    )

    if previous_summary:
        user_content = (
            "Текущая сводка диалога:\n"
            f"{previous_summary}\n\n"
            "Новые сообщения диалога:\n"
            f"{new_messages}\n\n"
            "Обнови сводку так, чтобы она кратко описывала ВСЮ историю."
        )
    else:
        user_content = (
            "Сделай краткую сводку следующего диалога:\n\n"
            f"{new_messages}\n\n"
            "Сосредоточься на намерениях пользователя и ключевых фактах."
        )

    return await generate_chat_completion(
        system_prompt, [{"role": "user", "content": user_content}]
    )


async def embed_texts(texts: Iterable[str]) -> List[List[float]]:
    """
    Асинхронное получение эмбеддингов через OpenAI API.
    """
    settings = get_settings()
    client = get_openai_client(settings)
    response = await client.embeddings.create(
        model=settings.openai_embedding_model,
        input=list(texts),
    )
    return [item.embedding for item in response.data]

import os
import requests

INFINITY_URL = os.environ.get("EMBEDDINGS_URL", "http://bge_embeddings:7998")
MODEL_ID = "BAAI/bge-m3"

async def embed_texts_bge(texts: list[str]) -> List[list[float]]:
    """
    Отправляем список строк на Infinity и получаем список векторов (dense).
    """
    payload = {
        "input": texts,
        "model": MODEL_ID,
        "encoding_format": "float"  # Infinity возвращает float32 по умолчанию
    }
    resp = requests.post(f"{INFINITY_URL}/embeddings", json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in data["data"]]
