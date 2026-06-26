from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from src.analysis import build_benchmark_report, build_compare_result, build_coverage_matrix
from src.retriever import HybridHit, get_search_backend, hybrid_search, similar_articles
from src.search import SearchHit
from src.vector_store import is_embedding_available

load_dotenv()

# 규정 Q&A는 소속 기관(한국수자원공사) 조문만 대상
QA_TARGET_ORG = "한국수자원공사"


def _format_hybrid_citations(hits: list[HybridHit], limit: int = 5) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for hit in hits[:limit]:
        citations.append(
            {
                "org": hit.article.org,
                "article_no": hit.article.article_no,
                "title": hit.article.title,
                "label": hit.article.label,
                "source_file": hit.article.source_file,
                "excerpt": hit.article.body[:500],
                "score": round(hit.score, 3),
                "keyword_score": round(hit.keyword_score, 3),
                "semantic_score": round(hit.semantic_score, 3),
                "matched_terms": hit.matched_terms,
            }
        )
    return citations


def _format_citations(hits: list[SearchHit], limit: int = 5) -> list[dict[str, Any]]:
    return _format_hybrid_citations(
        [
            HybridHit(
                article=h.article,
                score=h.score,
                keyword_score=h.score,
                semantic_score=0.0,
                matched_terms=h.matched_terms,
            )
            for h in hits
        ],
        limit=limit,
    )


def _fallback_summary(
    query: str, hits: list[HybridHit], *, org: str | None = None
) -> str:
    if not hits:
        scope = f"{org} " if org else ""
        return (
            f"{scope}사규관리규정에서 '{query}'와 관련된 조문을 찾지 못했습니다. "
            "다른 키워드로 시도해 보세요."
        )

    scope = f"**{org}** " if org else ""
    lines = [f"{scope}**'{query}'** 관련 조문 {len(hits)}건", ""]
    for hit in hits[:5]:
        lines.append(f"- {hit.article.label} (유사도 {hit.score:.0%})")
        snippet = hit.article.body[:180].replace("\n", " ")
        lines.append(f"  {snippet}...")
    lines.append("")
    lines.append("_검색: OpenAI Embedding + Chroma 벡터스토어_")
    if _openai_available():
        lines.append("_AI 요약: OpenAI LLM 사용 중_")
    else:
        lines.append("_AI 요약: OPENAI_API_KEY 설정 시 활성화됩니다._")
    return "\n".join(lines)


def _openai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def summarize_with_llm(
    query: str,
    hits: list[HybridHit],
    mode: str = "qa",
    *,
    org: str | None = None,
) -> str:
    if not hits:
        return _fallback_summary(query, hits, org=org)
    if not _openai_available():
        return _fallback_summary(query, hits, org=org)

    from src.openai_client import get_openai_client

    client = get_openai_client()
    context_parts = []
    for i, hit in enumerate(hits[:8], start=1):
        context_parts.append(
            f"[{i}] {hit.article.org} | {hit.article.label}\n{hit.article.body[:1200]}"
        )
    context = "\n\n".join(context_parts)

    qa_extra = (
        f" 답변은 {org} 사규관리규정만을 근거로 작성하세요."
        if org
        else ""
    )
    prompts = {
        "qa": f"질문에 대해 근거 조문만 사용해 답변하세요.{qa_extra}",
        "compare": "두 기관의 차이점과 공통점을 항목별로 정리하세요.",
        "gap": "기준 기관 대비 검토가 필요한 항목을 설명하세요.",
        "similar": "기관별 유사 조문의 공통점과 표현 차이를 요약하세요.",
        "report": "벤치마킹 보고서 형식으로 개요·검토권고·결론을 작성하세요.",
    }
    system = (
        "당신은 공공기관 사규관리규정 분석 보조 AI입니다. "
        "제공된 조문만 근거로 답하고, 없는 내용은 추측하지 마세요. "
        + prompts.get(mode, prompts["qa"])
    )
    user = f"질문/요청: {query}\n\n근거 조문:\n{context}"

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content or _fallback_summary(query, hits, org=org)


def _load_articles():
    from backend.services.regulation_service import load_all_articles, rebuild_search_index

    articles = load_all_articles()
    rebuild_search_index(articles)
    return articles


def run_search(query: str) -> dict[str, Any]:
    articles = _load_articles()
    has_org = any(a.org == QA_TARGET_ORG for a in articles)
    if not has_org:
        return {
            "query": query,
            "target_org": QA_TARGET_ORG,
            "search_mode": "hybrid",
            "summary": (
                f"**{QA_TARGET_ORG}** 사규관리규정 데이터가 없습니다. "
                "규정 관리 탭에서 파일을 업로드하거나 data/ 폴더를 재색인해 주세요."
            ),
            "citations": [],
            "ai_enabled": _openai_available(),
        }

    hits = hybrid_search(articles, query, org=QA_TARGET_ORG, limit=10)
    backend = hits[0].search_backend if hits else get_search_backend()
    return {
        "query": query,
        "target_org": QA_TARGET_ORG,
        "search_mode": "hybrid",
        "search_backend": backend,
        "summary": summarize_with_llm(query, hits, mode="qa", org=QA_TARGET_ORG),
        "citations": _format_hybrid_citations(hits),
        "ai_enabled": _openai_available(),
        "embedding_enabled": is_embedding_available(),
    }


def run_similar_search(query: str) -> dict[str, Any]:
    articles = _load_articles()
    hits = similar_articles(articles, query, limit=15)
    by_org: dict[str, dict] = {}
    for hit in hits:
        by_org[hit.article.org] = _format_hybrid_citations([hit])[0]

    return {
        "query": query,
        "search_mode": "hybrid_similar",
        "summary": summarize_with_llm(query, hits, mode="similar"),
        "by_org": by_org,
        "citations": _format_hybrid_citations(hits),
        "ai_enabled": _openai_available(),
    }


def run_compare(org_a: str, org_b: str, topic: str) -> dict[str, Any]:
    articles = _load_articles()
    hits_a = hybrid_search(articles, topic, org=org_a, limit=3)
    hits_b = hybrid_search(articles, topic, org=org_b, limit=3)
    structured = build_compare_result(hits_a, hits_b, org_a, org_b, topic)
    all_hits = hits_a + hits_b
    summary = summarize_with_llm(f"{org_a} vs {org_b} — {topic} 비교", all_hits, mode="compare")

    return {
        "org_a": org_a,
        "org_b": org_b,
        "topic": topic,
        "summary": summary,
        "comparison_table": structured["comparison_table"],
        "common_points": structured["common_points"],
        "differences": structured["differences"],
        "org_a_citations": _format_hybrid_citations(hits_a, limit=3),
        "org_b_citations": _format_hybrid_citations(hits_b, limit=3),
        "ai_enabled": _openai_available(),
    }


def run_gap_detection(target_org: str, topic: str) -> dict[str, Any]:
    articles = _load_articles()
    matrix = build_coverage_matrix(articles, target_org)
    row = next((r for r in matrix if topic in r["topic"] or topic in r["description"]), None)

    if row:
        review_needed = row["review_needed"]
        hits = hybrid_search(articles, topic, limit=20)
        others = {
            h.article.org: _format_hybrid_citations([h])[0]
            for h in hits
            if h.article.org != target_org
        }
    else:
        from src.search import find_missing_topics

        legacy = find_missing_topics(articles, target_org, topic)
        review_needed = legacy.get("review_needed", False)
        hits = hybrid_search(articles, topic, limit=20)
        others = {
            org: _format_hybrid_citations([h for h in hits if h.article.org == org][:1])[0]
            for org in {h.article.org for h in hits}
            if org != target_org
        }
        row = None

    flat_hits = [h for h in hybrid_search(articles, topic, limit=20) if h.article.org != target_org]
    summary = summarize_with_llm(f"{target_org} 기준 '{topic}' 검토 권고", flat_hits[:8], mode="gap")
    if review_needed:
        summary = f"**검토 권고:** {target_org}에서 '{topic}' 관련 조문이 타 기관 대비 약합니다.\n\n{summary}"

    return {
        "target_org": target_org,
        "topic": topic,
        "review_needed": review_needed,
        "topic_row": row,
        "summary": summary,
        "other_orgs": others,
        "ai_enabled": _openai_available(),
    }


def run_gap_scan(target_org: str) -> dict[str, Any]:
    articles = _load_articles()
    matrix = build_coverage_matrix(articles, target_org)
    review_items = [r for r in matrix if r["review_needed"]]
    return {
        "target_org": target_org,
        "coverage_matrix": matrix,
        "review_items": review_items,
        "review_count": len(review_items),
    }


def run_benchmark_report(target_org: str) -> dict[str, Any]:
    articles = _load_articles()
    report = build_benchmark_report(articles, target_org)
    review_hits = []
    for item in report["review_items"][:5]:
        hits = hybrid_search(articles, item["topic"], limit=3)
        review_hits.extend(hits)

    ai_summary = summarize_with_llm(
        f"{target_org} 사규관리규정 벤치마킹",
        review_hits,
        mode="report",
    )
    report["ai_summary"] = ai_summary
    report["ai_enabled"] = _openai_available()
    return report
