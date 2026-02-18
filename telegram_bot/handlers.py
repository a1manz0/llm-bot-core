from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from api_client import BackendClient

logger = logging.getLogger(__name__)

router = Router()


NEW_QUERY_TEXT = "Новый запрос"


def main_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.button(text=NEW_QUERY_TEXT)
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=False)


HELP_TEXT = (
    "Доступные команды:\n"
    "• /start — сбросить контекст и начать заново\n"
    "• /help — помощь\n\n"
    f"Также можно нажать кнопку «{NEW_QUERY_TEXT}», чтобы сбросить контекст."
)


def setup_handlers(api: BackendClient) -> Router:
    """Регистрирует обработчики и возвращает router."""

    async def reset_context(message: Message) -> None:
        """Общий метод сброса контекста по chat_id."""
        if not message.chat:
            return
        chat_id = str(message.chat.id)
        try:
            await api.reset_chat(chat_id=chat_id)
        except Exception as e:
            logger.exception("Ошибка сброса сессии для chat_id=%s: %s", chat_id, e)

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        if not message.from_user or not message.chat:
            return

        await reset_context(message)

        await message.answer(
            "Начинаем с чистого листа — напишите что-нибудь.",
            reply_markup=main_keyboard(),
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            HELP_TEXT,
            reply_markup=main_keyboard(),
        )

    # Кнопка "Новый запрос" (сброс контекста)
    @router.message(lambda m: bool(m.text) and m.text.strip() == NEW_QUERY_TEXT)
    async def new_query(message: Message) -> None:
        if not message.from_user or not message.chat:
            return

        await reset_context(message)

        await message.answer(
            "Контекст сброшен. Отправьте новый запрос.",
            reply_markup=main_keyboard(),
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
            await message.answer(answer, reply_markup=main_keyboard())
        except Exception as e:
            logger.exception("Ошибка при обработке сообщения: %s", e)
            await message.answer(
                "Произошла ошибка при формировании ответа. Попробуйте позже.",
                reply_markup=main_keyboard(),
            )

    return router
