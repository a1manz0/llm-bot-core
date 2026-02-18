"""
Celery app для фоновых задач (суммаризация и т.д.).
Воркер: celery -A src.app.celery_app worker --loglevel=info
"""
from celery import Celery

from .config import get_settings

_settings = get_settings()

app = Celery(
    "llm_bot",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_broker_url,
    include=["src.app.tasks"],
)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_time_limit=300,
)
