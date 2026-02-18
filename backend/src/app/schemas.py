from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Идентификатор пользователя Telegram")
    chat_id: str = Field(..., description="Идентификатор чата Telegram")
    text: str = Field(..., min_length=1, description="Текст сообщения пользователя")


class ChatResponse(BaseModel):
    text: str = Field(..., description="Ответ ассистента")
    type: Literal["message"] | str = Field(
        default="message",
        description="Тип ответа (сообщение, изображение и т.п.)",
    )


class ResetRequest(BaseModel):
    session_id: Optional[str] = Field(
        default=None,
        description="UUID сессии, если известен клиенту",
    )
    chat_id: Optional[str] = Field(
        default=None,
        description="chat_id для сброса активной сессии",
    )

    @model_validator(mode="after")
    def validate_any_identifier(self) -> "ResetRequest":
        if not self.session_id and not self.chat_id:
            raise ValueError("Нужно указать хотя бы session_id или chat_id")
        return self


