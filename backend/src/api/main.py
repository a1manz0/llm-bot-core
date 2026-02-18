from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from src.app import memory
from src.app.config import get_settings
from src.app.db import Base, engine, get_db
from src.app.llm import generate_chat_completion
from src.app.models import ChatSession, EmbeddingRecord, MessageRole
from src.app.rag import index_messages, search_semantic_memory
from src.app.schemas import ChatRequest, ChatResponse, ResetRequest
from src.app.tasks import summarize_session_task


app = FastAPI(
    title="LLM Bot Core API",
    version="1.0.0",
    description="Backend-сервис для Telegram-бота с многоуровневой памятью и RAG (опционально).",
)


@app.on_event("startup")
def on_startup() -> None:
    """
    Инициализация схемы БД.

    В проде это лучше делать миграциями (Alembic), но для прототипа достаточно create_all.
    """
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    """Проверка доступности бэкенда."""
    return {"status": "ok"}


@app.post("/v1/chat/handle", response_model=ChatResponse)
async def handle_chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    """
    Основной эндпоинт для Telegram-бота.

    Процесс:
    - создаём/загружаем сессию
    - загружаем краткосрочную и сводную память
    - опционально запрашиваем семантическую память (RAG)
    - формируем промпт и вызываем LLM (асинхронно)
    - сохраняем полный журнал сообщений
    - обновляем summary и, при включённом RAG, семантическую память
    """
    settings = get_settings()

    # 1. Сессия
    session: ChatSession = memory.get_or_create_session(
        db=db,
        user_id=payload.user_id,
        chat_id=payload.chat_id,
    )

    # 2. Краткосрочная память
    recent_messages = memory.get_recent_messages(
        db=db,
        session_id=session.id,
        limit=settings.short_history_limit,
    )

    # 3. Сводная память
    summary = memory.get_latest_summary(db=db, session_id=session.id)

    # 4. Семантическая память (RAG)
    rag_chunks = None
    if settings.rag_enabled:
        rag_chunks = await search_semantic_memory(
            query_text=payload.text,
            top_k=settings.rag_top_k,
            session_id=str(session.id),
        )

    # 5. Формирование промпта
    messages_for_llm = memory.build_prompt(
        summary=summary,
        recent_messages=recent_messages,
        user_text=payload.text,
        rag_chunks=rag_chunks,
    )

    # 6. Запрос к LLM (асинхронно, OpenRouter)
    answer_text = await generate_chat_completion(
        system_prompt=settings.system_prompt,
        messages=messages_for_llm,
    )

    # 7. Сохранение сообщений
    user_msg, assistant_msg = memory.save_turn(
        db=db,
        session=session,
        user_text=payload.text,
        assistant_text=answer_text,
    )

    # 8. Счётчик сообщений с последней сводки: +2 за ход; при достижении порога — задача в Celery (или синхронно)
    memory.increment_messages_since_summary(db=db, session=session, delta=2)
    if memory.should_summarize_now(session):
        if settings.use_celery_for_summary:
            summarize_session_task.delay(str(session.id))
            memory.reset_messages_since_summary(db=db, session=session)
        else:
            await memory.summarize_session(db=db, session=session)
            memory.reset_messages_since_summary(db=db, session=session)

    # 9. Семантическая память (добавление векторов в Qdrant)
    if settings.rag_enabled:
        records = []
        texts = []
        for msg in (user_msg, assistant_msg):
            rec = EmbeddingRecord(
                session_id=session.id,
                message_id=msg.id,
                role=msg.role,
                content=msg.content,
                importance=0,
            )
            db.add(rec)
            records.append(rec)
            texts.append(msg.content)
        db.commit()
        for rec in records:
            db.refresh(rec)
        await index_messages(records=records, texts=texts)

    return ChatResponse(text=answer_text, type="message")


@app.post("/v1/chat/reset")
def reset_chat(
    payload: ResetRequest,
    db: Session = Depends(get_db),
) -> dict:
    """
    Сброс сессии: завершает текущую активную сессию по session_id или chat_id.
    """
    affected = 0
    if payload.session_id:
        affected += memory.reset_session_by_id(db=db, session_id=payload.session_id)
    if payload.chat_id:
        affected += memory.reset_active_session_by_chat(db=db, chat_id=payload.chat_id)

    if affected == 0:
        raise HTTPException(status_code=404, detail="Активная сессия не найдена")

    return {"status": "ok", "reset_sessions": affected}


