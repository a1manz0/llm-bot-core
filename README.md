# LLM Bot Core — backend для Telegram‑бота

Телеграм бот и бэкенд‑сервис на FastAPI с многоуровневой памятью. Использует PostgreSQL для хранения диалогов, Directus как админ‑панель и, опционально, Qdrant для семантического поиска (RAG).

## Архитектура 

![Диаграмма](diagram.png)

```
Telegram Bot  ──▶  Backend (FastAPI)
                       │
                       ├── PostgreSQL (chat_sessions, messages, conversation_summaries, embeddings)
                       ├── Directus (админ‑панель поверх той же БД)
                       └── Qdrant (опционально, семантическая память/RAG)
```

### Основные компоненты

| Сервис | Описание |
|--------|----------|
| **backend** | FastAPI‑приложение: хранение сессий, многоуровневая память, вызовы LLM, REST API для Telegram‑бота |
| **postgres_llm_bot** | PostgreSQL c таблицами `chat_sessions`, `messages`, `conversation_summaries`, `embeddings` |
| **directus** | Админ‑панель поверх той же базы: просмотр диалогов, сводок и семантических записей |
| **redis** | Брокер для Celery (очередь задач суммаризации) |
| **celery_worker** | Воркер Celery: выполняет суммаризацию в фоне, не блокируя API |
| **telegram_bot** | Telegram‑бот на aiogram: приём сообщений и команды `/start`, вызовы backend API |
| **qdrant** (опц.) | Векторная БД для RAG‑поиска по прошлым сообщениям и фактам |
| **bge_embeddings** (опц.) | Контейнер для локальных эмбеддингов (Infinity + BGE‑M3), может использоваться вместо внешнего API |

## Модель данных (PostgreSQL)

- **chat_sessions**: сессии диалога (`id`, `user_id`, `chat_id`, `is_active`, `created_at`, `closed_at`, `messages_since_summary` — счётчик сообщений с последней сводки, сбрасывается при суммаризации).
- **messages**: полный журнал сообщений (`id`, `session_id`, `role` = `user|assistant|system|tool`, `content`, `tokens`, `created_at`).
- **conversation_summaries**: сводки диалога (`id`, `session_id`, `version`, `content`, `created_at`, `last_message_id` — ID последнего сообщения, включённого в сводку; следующие сводки берут только сообщения после него, не более `SUMMARY_NEW_MESSAGES_LIMIT`).
- **embeddings**: метаданные семантической памяти (`id`, `session_id`, `message_id`, `role`, `content`, `importance`, `created_at`). Векторы хранятся в Qdrant.

Все таблицы создаются автоматически при старте backend‑сервиса (`SQLAlchemy.create_all`); Directus поверх них поднимает коллекции.

## Память агента

- **Краткосрочная память**: последние `N` сообщений сессии (по умолчанию `SHORT_HISTORY_LIMIT=8`).
- **Сводная память (summary)**: прогрессивная сводка. В сессии — счётчик сообщений с последней сводки; при достижении порога (`SUMMARY_THRESHOLD`) **задача ставится в очередь Celery** и выполняется в воркере (бэкенд не блокируется). В сводке сохраняется `last_message_id`; следующая сводка строится только по сообщениям после него (лимит 200, `SUMMARY_NEW_MESSAGES_LIMIT`).
- **Семантическая память (RAG)**: при включённом RAG новые сообщения индексируются в Qdrant; перед ответом выполняется поиск top‑K релевантных фрагментов.

В промпт LLM передаётся:

1. системная инструкция;
2. последняя сводка по диалогу;
3. последние N сообщений (role + content);
4. найденные RAG‑факты (если модуль включён).

## API

### `POST /v1/chat/handle`

Обработка сообщения от Telegram‑бота.

**Request (JSON):**

```json
{
  "user_id": "12345",
  "chat_id": "67890",
  "text": "Привет, расскажи, что ты умеешь?"
}
```

**Response (JSON):**

```json
{
  "text": "Привет! Я бэкенд-для Телеграм-бота с памятью и RAG.",
  "type": "message"
}
```

### `POST /v1/chat/reset`

Сброс текущей сессии (команда `/start` в Telegram).

**Request (JSON):**

```json
{
  "chat_id": "67890"
}
```

или

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (JSON):**

```json
{
  "status": "ok",
  "reset_sessions": 1
}
```

### `GET /health`

Проверка доступности backend‑сервиса.

## Запуск

### 1. Подготовка `.env`

В корне проекта создайте файл `.env` (минимальный пример):

```env
OPENROUTER_API_KEY=sk-or-...   # чат через OpenRouter (google/gemini-2.5-flash и др.)
OPENAI_API_KEY=sk-...          # эмбеддинги (нужен только при RAG_ENABLED=true)
BOT_TOKEN=123456:ABC-DEF...    # токен бота от @BotFather (обязателен для сервиса telegram_bot)

# Необязательные настройки:
# OPENROUTER_MODEL=google/gemini-2.5-flash  # или anthropic/claude-opus-4.5
# OPENAI_EMBEDDING_MODEL=text-embedding-3-small
# SHORT_HISTORY_LIMIT=8
# SUMMARY_THRESHOLD=24
# RAG_ENABLED=true
# BACKEND_URL=http://backend:8080  (для бота)
# USE_CELERY_FOR_SUMMARY=true   (суммаризация в воркере; false — выполнять в запросе)
# CELERY_BROKER_URL=redis://redis:6379/0
# SUMMARY_NEW_MESSAGES_LIMIT=200 (макс. сообщений в одном чанке суммаризации)
```

### 2. Базовый стек (Postgres + Backend + Directus)

```bash
docker compose up -d --build
```

- Backend: `http://localhost:8080`
- Directus: `http://localhost:8055`
- Telegram‑бот: работает в фоне (long polling), логи — `docker compose logs -f telegram_bot`

Для работы бота в `.env` должен быть указан `BOT_TOKEN` (токен от [@BotFather](https://t.me/BotFather)). После запуска напишите боту в Telegram — ответы формирует backend с учётом памяти и, при включённом RAG, семантического поиска. Команда `/start` сбрасывает сессию и начинает диалог заново.

### 3. Запуск с  RAG‑модулем (Qdrant + embeddings)

```bash
docker compose -f docker-compose.rag.yml up -d --build
```

В этом случае дополнительно поднимаются:

- Qdrant: `http://localhost:6333`
- Сервис эмбеддингов `bge_embeddings` на порту `7998` (может быть подключён в коде вместо OpenAI‑эмбеддингов).

## Directus — админ‑панель

**Directus** — это headless CMS и панель администратора поверх вашей PostgreSQL. Он не подменяет базу: подключается к той же БД, что и backend, автоматически подхватывает таблицы как «коллекции» и даёт веб‑интерфейс для просмотра и правки данных, REST/GraphQL API и гибкие права доступа.

### Что позволяет сделать Директус

- **Просмотр диалогов** — все сообщения (`messages`), сессии (`chat_sessions`), сводки (`conversation_summaries`) и метаданные эмбеддингов (`embeddings`) в одном месте.
- **Ручная правка** — можно поправить или удалить запись, пометить сессию завершённой и т.п.
- **Аналитика и экспорт** — фильтры, сортировки, экспорт в CSV/JSON.
- **Роли и доступ** — разграничение прав (админ, оператор, только просмотр) без отдельного бэкенда.

### Первый запуск

1. Запустите стек: `docker compose up -d`.
2. Откройте в браузере адрес Directus (например `http://localhost:8057` или порт из `docker-compose.yml`).
3. При первом заходе укажите учетные данные администратора `ADMIN_EMAIL` и `ADMIN_PASSWORD` из `environment` сервиса `directus`).
4. При первом заходе потребуется инициализировать коллекции. Перейдите в настройки и прокликайте по всем таблицам, Директус их подхватит.
5. В разделе «Коллекции» должны появиться таблицы: `chat_sessions`, `messages`, `conversation_summaries`, `embeddings` (если backend уже создал их при старте).

Документация: [directus.io](https://directus.io) / [docs.directus.io](https://docs.directus.io).

## Структура backend‑части

```text
backend/
  ├── Dockerfile
  ├── requirements.txt
  └── src/
      ├── api/
      │   └── main.py               # FastAPI, REST эндпоинты
      └── app/
          ├── config.py             # Settings (env → Settings dataclass)
          ├── db.py                 # SQLAlchemy engine, SessionLocal, Base
          ├── models.py             # ChatSession, Message, ConversationSummary, EmbeddingRecord
          ├── schemas.py            # Pydantic-схемы для API
          ├── llm.py                # Вызовы LLM, summarization, embed_texts
          ├── rag.py                # Qdrant-клиент, search_semantic_memory, index_messages
          └── memory.py             # Логика работы с памятью и сессиями

telegram_bot/
  ├── Dockerfile
  ├── requirements.txt             # aiogram, httpx, python-dotenv
  ├── config.py                    # BotConfig (BOT_TOKEN, BACKEND_URL)
  ├── api_client.py                # BackendClient: handle_chat, reset_chat
  ├── handlers.py                  # /start → reset, сообщения → handle
  └── main.py                      # Точка входа, polling
```
