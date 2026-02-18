import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .db import Base, utcnow


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


class ChatSession(Base):
    """
    Сессия диалога Telegram-пользователя с ботом.

    ВАЖНО: отдельная сущность, чтобы удобно связывать сообщения, summary и эмбеддинги.
    """

    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)
    chat_id = Column(String, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    # Сколько сообщений накоплено с момента последней сводки; при достижении порога — суммаризация и сброс в 0
    messages_since_summary = Column(Integer, default=0, nullable=False)

    messages = relationship("Message", back_populates="session", lazy="selectin")
    summaries = relationship(
        "ConversationSummary", back_populates="session", lazy="selectin"
    )


class Message(Base):
    """Полный журнал сообщений, как описано в ТЗ."""

    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(Enum(MessageRole, name="message_role"), nullable=False)
    content = Column(Text, nullable=False)
    tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")


class ConversationSummary(Base):
    """Сводная память по диалогу (progressive summarization)."""

    __tablename__ = "conversation_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    # ID последнего сообщения, включённого в эту сводку; следующие сводки берут сообщения с id > last_message_id
    last_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    session = relationship("ChatSession", back_populates="summaries")


class EmbeddingRecord(Base):
    """
    Метаданные семантической памяти.

    Сами вектора живут в Qdrant, здесь только описание:
    content, принадлежность сессии, связанное сообщение и важность.
    """

    __tablename__ = "embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role = Column(Enum(MessageRole, name="embedding_role"), nullable=True)
    content = Column(Text, nullable=False)
    importance = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


