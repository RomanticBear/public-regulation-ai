"""조문 단위 OpenAI Embedding + Chroma 벡터스토어."""

from __future__ import annotations

import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv

from src.parser import Article

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
CHROMA_PATH = ROOT / "processed" / "chroma"
COLLECTION_NAME = "articles"
BATCH_SIZE = 64


def article_key(article: Article, seq: int) -> str:
    return f"{article.org}|{article.source_file}|{article.article_no}|{seq}"


def article_embed_text(article: Article) -> str:
    """임베딩용 텍스트 — 조문 번호·제목·본문."""
    header = f"{article.org} {article.regulation} {article.article_no}"
    if article.title:
        header += f"({article.title})"
    return f"{header}\n{article.body}"


def is_embedding_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def get_embedding_model() -> str:
    return os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def embed_texts(texts: list[str]) -> list[list[float]]:
    from src.openai_client import get_openai_client

    client = get_openai_client()
    response = client.embeddings.create(model=get_embedding_model(), input=texts)
    return [item.embedding for item in response.data]


def _get_client() -> chromadb.PersistentClient:
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


def rebuild_vector_store(articles: list[Article]) -> dict:
    """모든 조문을 embedding 후 Chroma에 저장."""
    import shutil

    if not is_embedding_available():
        return {"ok": False, "reason": "OPENAI_API_KEY가 .env에 설정되어 있지 않습니다."}

    if not articles:
        return {"ok": False, "reason": "조문 없음"}

    if CHROMA_PATH.exists():
        shutil.rmtree(CHROMA_PATH, ignore_errors=True)

    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    texts = [article_embed_text(a) for a in articles]
    all_embeddings: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        all_embeddings.extend(embed_texts(batch))

    collection.add(
        ids=[article_key(a, i) for i, a in enumerate(articles)],
        embeddings=all_embeddings,
        documents=texts,
        metadatas=[
            {
                "org": a.org,
                "regulation": a.regulation,
                "article_no": a.article_no,
                "title": a.title or "",
                "source_file": a.source_file,
            }
            for a in articles
        ],
    )

    return {
        "ok": True,
        "count": len(articles),
        "model": get_embedding_model(),
        "store": "chroma",
    }


def vector_search(
    query: str,
    articles: list[Article],
    *,
    org: str | None = None,
    limit: int = 10,
) -> list[tuple[str, Article, float]]:
    """질문 embedding → Chroma 유사 조문 검색. (key, article, score)"""
    if not is_embedding_available():
        return []

    client = _get_client()
    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        return []

    if collection.count() == 0:
        return []

    query_embedding = embed_texts([query])[0]
    where: dict | None = {"org": org} if org else None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(limit, collection.count()),
        where=where,
        include=["distances"],
    )

    if not results["ids"] or not results["ids"][0]:
        return []

    article_map = {article_key(a, i): a for i, a in enumerate(articles)}
    hits: list[tuple[str, Article, float]] = []
    for doc_id, distance in zip(results["ids"][0], results["distances"][0]):
        article = article_map.get(doc_id)
        if article is None:
            continue
        similarity = max(0.0, 1.0 - float(distance))
        hits.append((doc_id, article, similarity))
    return hits


def vector_store_stats() -> dict:
    if not is_embedding_available():
        return {"embedding_enabled": False, "vector_count": 0}
    try:
        collection = _get_client().get_collection(COLLECTION_NAME)
        return {
            "embedding_enabled": True,
            "vector_count": collection.count(),
            "model": get_embedding_model(),
            "store": "chroma",
        }
    except Exception:
        return {"embedding_enabled": True, "vector_count": 0, "model": get_embedding_model()}
