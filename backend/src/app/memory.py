from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import asc, desc, func, select, update
from sqlalchemy.orm import Session

from .config import get_settings
from .db import utcnow
from .llm import summarize_progressively
from .models import ChatSession, ConversationSummary, EmbeddingRecord, Message, MessageRole


def get_or_create_session(
    db: Session,
    user_id: str,
    chat_id: str,
) -> ChatSession:
    """
    Возвращает активную сессию для (user_id, chat_id) или создаёт новую.
    """
    stmt = (
        select(ChatSession)
        .where(
            ChatSession.user_id == user_id,
            ChatSession.chat_id == chat_id,
            ChatSession.is_active.is_(True),
        )
        .limit(1)
    )
    row = db.execute(stmt).scalars().first()
    if row:
        return row

    session = ChatSession(user_id=user_id, chat_id=chat_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_recent_messages(
    db: Session,
    session_id,
    limit: int,
) -> List[Message]:
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(desc(Message.created_at))
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return list(reversed(rows))


def get_latest_summary(
    db: Session,
    session_id,
) -> Optional[ConversationSummary]:
    stmt = (
        select(ConversationSummary)
        .where(ConversationSummary.session_id == session_id)
        .order_by(desc(ConversationSummary.version))
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def count_messages(db: Session, session_id) -> int:
    stmt = select(func.count()).select_from(Message).where(Message.session_id == session_id)
    return db.execute(stmt).scalar_one()


def save_turn(
    db: Session,
    session: ChatSession,
    user_text: str,
    assistant_text: str,
    user_tokens: int | None = None,
    assistant_tokens: int | None = None,
) -> Tuple[Message, Message]:
    """
    Сохраняет пару сообщений (user + assistant) в журнал.
    """
    user_msg = Message(
        session_id=session.id,
        role=MessageRole.user,
        content=user_text,
        tokens=user_tokens,
    )
    assistant_msg = Message(
        session_id=session.id,
        role=MessageRole.assistant,
        content=assistant_text,
        tokens=assistant_tokens,
    )
    db.add_all([user_msg, assistant_msg])
    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant_msg)
    return user_msg, assistant_msg


def increment_messages_since_summary(
    db: Session, session: ChatSession, delta: int = 2
) -> None:
    """
    Увеличивает счётчик сообщений с последней сводки на delta (за один ход = 2 сообщения).
    Обновляет запись сессии в БД.
    """
    session.messages_since_summary = (session.messages_since_summary or 0) + delta
    db.commit()
    db.refresh(session)


def should_summarize_now(session: ChatSession) -> bool:
    """
    True, если счётчик сообщений с последней сводки достиг или превысил порог.
    После вызова summarize_session нужно сбросить счётчик через reset_messages_since_summary.
    """
    settings = get_settings()
    return (session.messages_since_summary or 0) >= settings.summary_threshold


def reset_messages_since_summary(db: Session, session: ChatSession) -> None:
    """Сбрасывает счётчик после создания сводки."""
    session.messages_since_summary = 0
    db.commit()
    db.refresh(session)


def get_messages_after_last_summary(
    db: Session,
    session_id,
    last_message_id,
    limit: int,
) -> List[Message]:
    """
    Сообщения, идущие после last_message_id по времени (created_at), не более limit.
    Фильтр по created_at сообщения last_message_id, чтобы не зависеть от порядка UUID.
    Если last_message_id None — все сообщения сессии (первая сводка), не более limit.
    """
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(asc(Message.created_at))
    )
    if last_message_id is not None:
        last_msg = db.get(Message, last_message_id)
        if last_msg and last_msg.created_at is not None:
            stmt = stmt.where(Message.created_at > last_msg.created_at)
        # иначе last_message_id не найден — берём все (страховка)
    stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


async def summarize_session(
    db: Session,
    session: ChatSession,
) -> ConversationSummary:
    """
    Строит/обновляет сводку прогрессивно: берутся только сообщения с id > last_message_id
    последней сводки (по ID, без гонок по времени), не более summary_new_messages_limit.
    В новую запись сохраняется last_message_id последнего включённого сообщения.
    """
    settings = get_settings()
    limit = settings.summary_new_messages_limit

    # 1. Предыдущая сводка — из неё берём last_message_id
    prev = get_latest_summary(db, session.id)
    prev_text = prev.content if prev else None
    last_msg_id = prev.last_message_id if prev else None

    # 2. Новая часть: сообщения с id > last_message_id, лимит
    new_messages_list = get_messages_after_last_summary(
        db, session.id, last_msg_id, limit=limit
    )
    if not new_messages_list:
        # Нечего суммаризировать — возвращаем предыдущую сводку или пустую запись
        if prev:
            return prev
        new_summary = ConversationSummary(
            session_id=session.id,
            version=1,
            content="",
            last_message_id=None,
        )
        db.add(new_summary)
        db.commit()
        db.refresh(new_summary)
        return new_summary

    new_lines = [f"{m.role.value}: {m.content}" for m in new_messages_list]
    new_messages_text = "\n".join(new_lines)
    last_included_message = new_messages_list[-1]

    # 3. Прогрессивная сводка
    summary_text = await summarize_progressively(prev_text, new_messages_text)

    version = (prev.version + 1) if prev else 1
    new_summary = ConversationSummary(
        session_id=session.id,
        version=version,
        content=summary_text,
        last_message_id=last_included_message.id,
    )
    db.add(new_summary)
    db.commit()
    db.refresh(new_summary)
    return new_summary


def build_prompt(
    summary: ConversationSummary | None,
    recent_messages: Iterable[Message],
    user_text: str,
    rag_chunks: Optional[Iterable[dict]] = None,
) -> list[dict]:
    """
    Собирает список сообщений для LLM:
    - системная инструкция приходит отдельно (в config.system_prompt)
    - сюда передаём сводку, последние N сообщений и, опционально, RAG-фрагменты.
    """
    messages: list[dict] = []

    if summary:
        messages.append(
            {
                "role": "system",
                "content": f"Сводка предыдущего диалога:\n{summary.content}",
            }
        )

    if rag_chunks:
        joined = "\n\n".join(
            f"- {chunk.get('content')}" for chunk in rag_chunks if chunk.get("content")
        )
        if joined:
            messages.append(
                {
                    "role": "system",
                    "content": "Полезные факты из семантической памяти:\n" + joined,
                }
            )

    for msg in recent_messages:
        messages.append(
            {
                "role": msg.role.value,
                "content": msg.content,
            }
        )

    # И наконец — текущее сообщение пользователя
    messages.append({"role": "user", "content": user_text})
    print(messages)
    return messages


def reset_session_by_id(db: Session, session_id) -> int:
    """
    Помечает сессию завершённой и тем самым "обнуляет" краткосрочную память.
    Возвращает количество изменённых записей.
    """
    stmt = (
        update(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.is_active.is_(True))
        .values(is_active=False, closed_at=utcnow())
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount or 0


def reset_active_session_by_chat(
    db: Session,
    chat_id: str,
) -> int:
    stmt = (
        update(ChatSession)
        .where(ChatSession.chat_id == chat_id, ChatSession.is_active.is_(True))
        .values(is_active=False, closed_at=utcnow())
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount or 0


