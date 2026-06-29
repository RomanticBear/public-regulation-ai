"""키워드 + OpenAI Embedding 하이브리드 조문 검색."""

from __future__ import annotations

from dataclasses import dataclass

from src.parser import Article
from src.search import score_article
from src.topics import expand_topic_query
from src.vector_store import is_embedding_available, rebuild_vector_store, vector_search


class EmbeddingNotConfiguredError(RuntimeError):
    """OPENAI_API_KEY 미설정."""


@dataclass
class HybridHit:
    article: Article
    score: float
    keyword_score: float
    semantic_score: float
    matched_terms: list[str]
    search_backend: str = "embedding"


def get_search_backend() -> str:
    if not is_embedding_available():
        from backend.database import is_postgres

        if not is_postgres():
            raise EmbeddingNotConfiguredError(
                "DATABASE_URL이 .env에 설정되어 있지 않습니다."
            )
        raise EmbeddingNotConfiguredError(
            "OPENAI_API_KEY가 .env에 설정되어 있지 않습니다."
        )
    return "embedding"


def rebuild_index(articles: list[Article]) -> None:
    """조문 embedding 벡터스토어(Chroma) 재구축."""
    result = rebuild_vector_store(articles)
    if not result.get("ok"):
        raise RuntimeError(result.get("reason", "벡터스토어 구축 실패"))


def hybrid_search(
    articles: list[Article],
    query: str,
    *,
    org: str | None = None,
    limit: int = 10,
) -> list[HybridHit]:
    """키워드(동의어) + embedding 의미 검색 결합."""
    if not is_embedding_available():
        from backend.database import is_postgres

        if not is_postgres():
            raise EmbeddingNotConfiguredError(
                "DATABASE_URL이 .env에 설정되어 있지 않습니다."
            )
        raise EmbeddingNotConfiguredError(
            "OPENAI_API_KEY가 .env에 설정되어 있지 않습니다."
        )

    terms = expand_topic_query(query)
    kw_scores: dict[str, float] = {}
    kw_terms: dict[str, list[str]] = {}
    all_key_map = {_article_key(a, i): a for i, a in enumerate(articles)}

    for i, article in enumerate(articles):
        if org and article.org != org:
            continue
        score, matched = score_article(article, terms)
        if score > 0:
            key = _article_key(article, i)
            kw_scores[key] = score
            kw_terms[key] = matched

    sem_results = vector_search(query, articles, org=org, limit=limit * 3)
    sem_scores = {key: score for key, _, score in sem_results}

    max_kw = max(kw_scores.values(), default=1.0) or 1.0
    max_sem = max(sem_scores.values(), default=1.0) or 1.0

    merged: dict[str, HybridHit] = {}
    all_keys = set(kw_scores) | set(sem_scores)
    for key in all_keys:
        article = all_key_map.get(key)
        if article is None:
            continue
        if org and article.org != org:
            continue
        kw = kw_scores.get(key, 0.0) / max_kw
        sem = sem_scores.get(key, 0.0) / max_sem
        combined = 0.30 * kw + 0.70 * sem
        if combined <= 0.05:
            continue
        merged[key] = HybridHit(
            article=article,
            score=combined,
            keyword_score=kw,
            semantic_score=sem,
            matched_terms=kw_terms.get(key, []),
            search_backend="embedding",
        )

    hits = sorted(merged.values(), key=lambda h: h.score, reverse=True)
    return hits[:limit]


def similar_articles(
    articles: list[Article],
    query: str,
    *,
    limit: int = 15,
) -> list[HybridHit]:
    hits = hybrid_search(articles, query, limit=limit * 2)
    seen_orgs: set[str] = set()
    result: list[HybridHit] = []
    for hit in hits:
        if hit.article.org in seen_orgs:
            continue
        seen_orgs.add(hit.article.org)
        result.append(hit)
        if len(result) >= limit:
            break
    return result


def _article_key(article: Article, seq: int) -> str:
    return f"{article.org}|{article.source_file}|{article.article_no}|{seq}"
