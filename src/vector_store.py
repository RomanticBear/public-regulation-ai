"""조문 단위 OpenAI Embedding + Supabase pgvector 저장."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import delete, func, select, text

from backend.database import ArticleEmbedding, get_session, is_postgres
from src.parser import Article

load_dotenv()

BATCH_SIZE = 64


def article_key(article: Article, seq: int) -> str:
    return f"{article.org}|{article.source_file}|{article.article_no}|{seq}"


def article_embed_text(article: Article) -> str:
    header = f"{article.org} {article.regulation} {article.article_no}"
    if article.title:
        header += f"({article.title})"
    return f"{header}\n{article.body}"


def is_embedding_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY")) and is_postgres()


def get_embedding_model() -> str:
    return os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def embed_texts(texts: list[str]) -> list[list[float]]:
    from src.openai_client import get_openai_client

    client = get_openai_client()
    response = client.embeddings.create(model=get_embedding_model(), input=texts)
    return [item.embedding for item in response.data]


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


def delete_all_embeddings() -> None:
    if not is_postgres():
        return
    with get_session() as session:
        session.execute(delete(ArticleEmbedding))
        session.commit()


def delete_embeddings_for_file(source_file: str) -> None:
    if not is_postgres():
        return
    with get_session() as session:
        session.execute(
            delete(ArticleEmbedding).where(ArticleEmbedding.source_file == source_file)
        )
        session.commit()


def rebuild_vector_store(articles: list[Article]) -> dict:
    if not is_embedding_available():
        if not is_postgres():
            return {"ok": False, "reason": "DATABASE_URL이 .env에 설정되어 있지 않습니다."}
        return {"ok": False, "reason": "OPENAI_API_KEY가 .env에 설정되어 있지 않습니다."}

    if not articles:
        return {"ok": False, "reason": "조문 없음"}

    delete_all_embeddings()
    model = get_embedding_model()
    texts = [article_embed_text(a) for a in articles]
    keys = [article_key(a, i) for i, a in enumerate(articles)]

    all_embeddings: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        all_embeddings.extend(embed_texts(batch))

    with get_session() as session:
        for key, article, embedding in zip(keys, articles, all_embeddings):
            session.add(
                ArticleEmbedding(
                    article_key=key,
                    org=article.org,
                    source_file=article.source_file,
                    article_no=article.article_no,
                    model=model,
                    embedding=embedding,
                )
            )
        session.commit()

    return {
        "ok": True,
        "count": len(articles),
        "model": model,
        "store": "pgvector",
    }


def vector_search(
    query: str,
    articles: list[Article],
    *,
    org: str | None = None,
    limit: int = 10,
) -> list[tuple[str, Article, float]]:
    if not is_embedding_available():
        return []

    with get_session() as session:
        count = session.scalar(select(func.count()).select_from(ArticleEmbedding)) or 0
        if count == 0:
            return []

    query_embedding = embed_texts([query])[0]
    query_vec = _vector_literal(query_embedding)
    article_map = {article_key(a, i): a for i, a in enumerate(articles)}

    sql = text(
        """
        SELECT article_key, 1 - (embedding <=> CAST(:query_vec AS vector)) AS similarity
        FROM article_embeddings
        WHERE (:org IS NULL OR org = :org)
        ORDER BY embedding <=> CAST(:query_vec AS vector)
        LIMIT :lim
        """
    )

    with get_session() as session:
        rows = session.execute(
            sql,
            {"query_vec": query_vec, "org": org, "lim": min(limit, count)},
        ).all()

    hits: list[tuple[str, Article, float]] = []
    for row in rows:
        article = article_map.get(row.article_key)
        if article is None:
            continue
        hits.append((row.article_key, article, max(0.0, float(row.similarity))))
    return hits


def vector_store_stats() -> dict:
    if not is_postgres():
        return {
            "embedding_enabled": False,
            "vector_count": 0,
            "store": "none",
            "database": "sqlite",
        }
    if not os.getenv("OPENAI_API_KEY"):
        return {"embedding_enabled": False, "vector_count": 0, "store": "pgvector"}
    try:
        with get_session() as session:
            count = session.scalar(select(func.count()).select_from(ArticleEmbedding)) or 0
        return {
            "embedding_enabled": True,
            "vector_count": count,
            "model": get_embedding_model(),
            "store": "pgvector",
            "database": "postgres",
        }
    except Exception:
        return {
            "embedding_enabled": True,
            "vector_count": 0,
            "model": get_embedding_model(),
            "store": "pgvector",
            "database": "postgres",
        }
