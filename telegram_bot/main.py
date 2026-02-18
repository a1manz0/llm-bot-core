"""
Telegram-бот на aiogram. Тонкий транспорт: все запросы уходят в backend API.
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties


from config import BotConfig
from api_client import BackendClient
from handlers import setup_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = BotConfig.from_env()
    bot = Bot(
    token=config.token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)   
    api = BackendClient(base_url=config.backend_url)
    dp = Dispatcher()
    router = setup_handlers(api)
    dp.include_router(router)

    logger.info("Бот запущен, backend: %s", config.backend_url)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
