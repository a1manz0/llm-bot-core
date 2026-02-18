from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from api_client import BackendClient

logger = logging.getLogger(__name__)

router = Router()


def setup_handlers(api: BackendClient) -> Router:
    """Регистрирует обработчики и возвращает router."""

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        if not message.from_user or not message.chat:
            return
        user_id = str(message.from_user.id)
        chat_id = str(message.chat.id)
        try:
            await api.reset_chat(chat_id=chat_id)
        except Exception as e:
            logger.exception("Ошибка сброса сессии для chat_id=%s: %s", chat_id, e)
        await message.answer(
            "Начинаем с чистого листа — напишите что-нибудь."
        )

    @router.message()
    async def handle_message(message: Message) -> None:
        if not message.from_user or not message.chat or not message.text or not message.text.strip():
            return
        user_id = str(message.from_user.id)
        chat_id = str(message.chat.id)
        text = message.text.strip()
        try:
            data = await api.handle_chat(user_id=user_id, chat_id=chat_id, text=text)
            answer = data.get("text", "Нет ответа.")
            await message.answer(answer)
        except Exception as e:
            logger.exception("Ошибка при обработке сообщения: %s", e)
            await message.answer(
                "Произошла ошибка при формировании ответа. Попробуйте позже."
            )

    return router
