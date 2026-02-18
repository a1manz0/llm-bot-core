import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """
    Глобальные настройки backend-сервиса.

    Часть параметров может дублироваться/переезжать в Directus (таблица settings),
    но для простоты на первом этапе всё берём из переменных окружения.
    """

    # --- База данных ---
    database_url: str

    # --- Память диалога ---
    short_history_limit: int  # N последних сообщений в краткосрочной памяти
    summary_threshold: int  # порог длины диалога (в сообщениях) для пересчёта summary
    summary_new_messages_limit: int  # макс. сообщений для одной суммаризации (предохранитель)

    # --- RAG / семантическая память ---
    rag_enabled: bool
    rag_top_k: int
    qdrant_url: str
    qdrant_collection: str

    # --- LLM (OpenRouter для чата) / эмбеддинги (OpenAI) ---
    openrouter_api_key: str | None
    openrouter_model: str  # например google/gemini-2.5-flash, anthropic/claude-opus-4.5
    openai_api_key: str | None  # для эмбеддингов
    openai_embedding_model: str

    # --- Celery (суммаризация в фоне) ---
    use_celery_for_summary: bool
    celery_broker_url: str

    # --- Прочее ---
    system_prompt: str


@lru_cache
def get_settings() -> Settings:
    """Читает конфиг из env-переменных один раз за жизнь процесса."""

    def _bool(name: str, default: str = "false") -> bool:
        return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            # Уникальное имя хоста Postgres внутри compose
            "postgresql+psycopg2://llm_bot:llm_bot@postgres_llm_bot:5432/llm_bot",
        ),
        short_history_limit=int(os.getenv("SHORT_HISTORY_LIMIT", "8")),
        summary_threshold=int(os.getenv("SUMMARY_THRESHOLD", "8")),
        summary_new_messages_limit=int(os.getenv("SUMMARY_NEW_MESSAGES_LIMIT", "200")),
        rag_enabled=_bool("RAG_ENABLED", "false"),
        rag_top_k=int(os.getenv("RAG_TOP_K", "5")),
        qdrant_url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "chat_embeddings"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openai/gpt-5-mini"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_embedding_model=os.getenv(
            "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
        ),
        use_celery_for_summary=_bool("USE_CELERY_FOR_SUMMARY", "true"),
        celery_broker_url=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
        system_prompt=os.getenv(
            "SYSTEM_PROMPT",
            "You are a helpful Telegram bot assistant. "
            "Answer concisely and politely. If you are not sure, say that you are not sure.",
        ),
    )


