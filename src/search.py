"""키워드 기반 조문 검색."""

from __future__ import annotations

from dataclasses import dataclass

from src.parser import Article
from src.topics import expand_topic_query


@dataclass
class SearchHit:
    article: Article
    score: float
    matched_terms: list[str]


def score_article(article: Article, terms: list[str]) -> tuple[float, list[str]]:
    haystack = f"{article.article_no} {article.title} {article.body}".lower()
    matched: list[str] = []
    score = 0.0
    for term in terms:
        t = term.lower()
        if t not in haystack:
            continue
        matched.append(term)
        title_bonus = 3 if t in article.title.lower() or t in article.article_no.lower() else 0
        count = haystack.count(t)
        score += count + title_bonus
    return score, matched


def search_articles(articles: list[Article], query: str, limit: int = 10) -> list[SearchHit]:
    terms = expand_topic_query(query)
    hits: list[SearchHit] = []
    for article in articles:
        score, matched = score_article(article, terms)
        if score > 0:
            hits.append(SearchHit(article=article, score=score, matched_terms=matched))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def compare_by_topic(
    articles: list[Article], org_a: str, org_b: str, query: str
) -> tuple[list[SearchHit], list[SearchHit]]:
    hits_a = search_articles([a for a in articles if a.org == org_a], query, limit=3)
    hits_b = search_articles([a for a in articles if a.org == org_b], query, limit=3)
    return hits_a, hits_b


def find_missing_topics(
    articles: list[Article], target_org: str, query: str
) -> dict:
    """타 기관에는 있고 target_org에는 약한 조문 → 검토 권고."""
    by_org: dict[str, list[SearchHit]] = {}
    for org in sorted({a.org for a in articles}):
        org_articles = [a for a in articles if a.org == org]
        hits = search_articles(org_articles, query, limit=2)
        if hits:
            by_org[org] = hits

    target_score = max(
        (h.score for h in search_articles([a for a in articles if a.org == target_org], query, limit=1)),
        default=0,
    )

    others_have = {
        org: hits for org, hits in by_org.items() if org != target_org and hits[0].score > 0
    }
    target_weak = target_score < 2

    return {
        "target_org": target_org,
        "target_score": target_score,
        "target_weak": target_weak,
        "others": others_have,
        "review_needed": target_weak and len(others_have) >= 2,
    }
