from __future__ import annotations

from typing import Iterable, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from .config import get_settings
from .llm import embed_texts, embed_texts_bge
from .models import EmbeddingRecord

_qdrant: QdrantClient | None = None


def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        s = get_settings()
        _qdrant = QdrantClient(url=s.qdrant_url)
    return _qdrant


def ensure_collection(vector_size: int) -> None:
    """
    Проверяет наличие коллекции в Qdrant и создаёт её при отсутствии.
    Используется косинусная метрика, как рекомендовано в ТЗ.
    """
    s = get_settings()
    client = _get_qdrant()

    existing = client.get_collections()
    names = {c.name for c in existing.collections}
    if s.qdrant_collection in names:
        return

    client.create_collection(
        collection_name=s.qdrant_collection,
        vectors_config=qmodels.VectorParams(
            size=vector_size,
            distance=qmodels.Distance.COSINE,
        ),
    )


async def index_messages(
    records: Iterable[EmbeddingRecord],
    texts: Iterable[str],
) -> None:
    """
    Добавляет новые вектора в Qdrant (асинхронно).

    records и texts должны быть согласованы по длине/порядку.
    """
    s = get_settings()
    client = _get_qdrant()
    vectors = await embed_texts_bge(texts)

    if not vectors:
        return

    ensure_collection(vector_size=len(vectors[0]))

    points: List[qmodels.PointStruct] = []
    for rec, vec in zip(records, vectors):
        payload = {
            "embedding_id": str(rec.id),
            "session_id": str(rec.session_id) if rec.session_id else None,
            "message_id": str(rec.message_id) if rec.message_id else None,
            "role": rec.role.value if rec.role else None,
            "importance": rec.importance,
            "content": rec.content,
        }
        points.append(
            qmodels.PointStruct(
                id=str(rec.id),
                vector=vec,
                payload=payload,
            )
        )

    client.upsert(
        collection_name=s.qdrant_collection,
        points=points,
        wait=True,
    )


async def search_semantic_memory(
    query_text: str,
    top_k: int,
    session_id: Optional[str] = None,
) -> list[dict]:
    """
    Выполняет семантический поиск по Qdrant и возвращает найденные фрагменты
    вместе с payload (асинхронно).
    """
    s = get_settings()
    client = _get_qdrant()
    query_vec = await embed_texts_bge([query_text])

    ensure_collection(vector_size=len(query_vec[0]))

    search_filter: Optional[qmodels.Filter] = None
    if session_id:
        search_filter = qmodels.Filter(
            must=[qmodels.FieldCondition(key="session_id", match=qmodels.MatchValue(value=session_id))]
        )

    result = client.query_points(
        collection_name=s.qdrant_collection,
        query=query_vec[0],
        limit=top_k,
        query_filter=search_filter,
        with_payload=True,
    )

    chunks: list[dict] = []
    for point in result.points:
        payload = point.payload or {}
        chunks.append(
            {
                "id": payload.get("embedding_id") or str(point.id),
                "session_id": payload.get("session_id"),
                "message_id": payload.get("message_id"),
                "content": payload.get("content"),
                "importance": payload.get("importance"),
                "score": point.score,
            }
        )
    return chunks


async def perform_research_query(
    client: QdrantClient,
    collection: str,
    query: str,
    limit: int = 5,
) -> str:
    """
    Выполнить поисковый запрос в векторном хранилище.

    Args:
        client: Qdrant клиент
        collection: Имя коллекции
        query: Поисковый запрос
        embed_func: Функция для получения эмбеддинга запроса
        limit: Количество результатов

    Returns:
        Контекст из найденных текстов
    """
    q_vec = await embed_texts_bge([query])

    resp = client.query_points(
        collection_name=collection,
        query=q_vec[0],
        limit=limit,
        with_payload=True,
    )

    results = resp.points

    chunks_texts = []
    for r in results:
        payload = r.payload or {}
        chunks_texts.append(payload.get("text", ""))

    return chunks_texts