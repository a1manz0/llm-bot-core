import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class BotConfig:
    token: str
    backend_url: str

    @classmethod
    def from_env(cls) -> "BotConfig":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ValueError(
                "BOT_TOKEN не задан. Укажите токен бота в переменной окружения."
            )
        backend_url = os.getenv("BACKEND_URL", "http://backend:8080").rstrip("/")
        return cls(token=token, backend_url=backend_url)
