"""
Celery-задачи. Суммаризация выполняется в воркере, чтобы не блокировать API.
"""
import asyncio
import logging
import uuid

from sqlalchemy.orm import Session

from .celery_app import app
from .db import SessionLocal
from .memory import summarize_session
from .models import ChatSession

logger = logging.getLogger(__name__)


@app.task(bind=True, name="summarize_session_task")
def summarize_session_task(self, session_id: str) -> None:
    """
    Строит сводку для сессии в фоне. Вызывается из API через .delay(str(session.id)).
    """
    try:
        session_uuid = uuid.UUID(session_id)
    except (ValueError, TypeError):
        logger.warning("summarize_session_task: invalid session_id=%s", session_id)
        return

    db: Session = SessionLocal()
    try:
        session = db.get(ChatSession, session_uuid)
        if not session:
            logger.warning("summarize_session_task: session %s not found", session_id)
            return
        asyncio.run(summarize_session(db, session))
        logger.info("summarize_session_task: done for session %s", session_id)
    except Exception as e:
        logger.exception("summarize_session_task failed: %s", e)
        raise
    finally:
        db.close()
