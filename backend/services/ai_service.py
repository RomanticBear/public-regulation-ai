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
    from backend.services.regulation_service import load_all_articles

    return load_all_articles()


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


def extract_compare_insights_with_llm(
    org_a: str,
    org_b: str,
    topic: str,
    hits_a: list[HybridHit],
    hits_b: list[HybridHit],
) -> tuple[list[str], list[str]] | None:
    if not hits_a or not hits_b or not _openai_available():
        return None

    import json

    from src.openai_client import get_openai_client

    client = get_openai_client()
    parts = []
    for hit in hits_a[:2]:
        parts.append(
            f"## {org_a} | {hit.article.label}\n{hit.article.body[:2000]}"
        )
    for hit in hits_b[:2]:
        parts.append(
            f"## {org_b} | {hit.article.label}\n{hit.article.body[:2000]}"
        )
    context = "\n\n".join(parts)

    system = (
        "당신은 공공기관 사규관리규정 비교 분석 AI입니다. "
        "두 기관 조문의 실질적 내용(절차, 의무, 예외, 주체, 적용범위)만 비교하세요. "
        "조문번호·글자수·조문명 형식 차이는 제외하세요. "
        'JSON으로 {"common_points": [...], "differences": [...]} 형식만 반환하세요. '
        "common_points 2~4개, differences 3~6개, 각 항목은 한 문장 bullet."
    )
    user = f"주제: {topic}\n\n{context}"

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        common = [str(x).strip() for x in data.get("common_points", []) if str(x).strip()]
        diffs = [str(x).strip() for x in data.get("differences", []) if str(x).strip()]
        if common or diffs:
            return common[:6], diffs[:8]
    except Exception:
        pass
    return None


def run_compare(org_a: str, org_b: str, topic: str) -> dict[str, Any]:
    articles = _load_articles()
    hits_a = hybrid_search(articles, topic, org=org_a, limit=3)
    hits_b = hybrid_search(articles, topic, org=org_b, limit=3)
    structured = build_compare_result(hits_a, hits_b, org_a, org_b, topic)
    llm_insights = extract_compare_insights_with_llm(
        org_a, org_b, topic, hits_a, hits_b
    )
    if llm_insights:
        structured["common_points"], structured["differences"] = llm_insights
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


def _fallback_gap_ok_summary(
    target_org: str, topic: str, row: dict[str, Any] | None
) -> str:
    """검토 권고 조건 미충족 시 — 체크리스트 판정 근거만 설명."""
    if row:
        checklist_topic = row.get("topic", topic)
        status = row["target_status"]
        others = row.get("others_have_count", 0)
        art = row.get("target_article") or {}
        label = art.get("label") or ""
        excerpt = (art.get("excerpt") or "").replace("\n", " ")[:220]

        lines = [
            f"**{target_org}**는 체크리스트 **「{checklist_topic}」** 항목을 "
            f"**{status}**으로 판정했습니다.",
            "",
            f"타 기관 **{others}곳**이 해당 주제를 보유하고 있으나, "
            "기준 기관에도 관련 조문이 확인되어 **검토 권고 대상이 아닙니다**.",
        ]
        if label and label != "-":
            lines.extend(["", f"**근거 조문:** {label}"])
            if excerpt:
                lines.append(f"> {excerpt}…")
        lines.extend(
            [
                "",
                "_세부 표현·절차 비교는 **기관 비교** 탭을 이용하세요._",
            ]
        )
        return "\n".join(lines)

    return (
        f"**{target_org}**에서 **「{topic}」** 주제에 대한 "
        "명확한 누락 신호가 확인되지 않았습니다.\n\n"
        "_체크리스트에 없는 자유 주제인 경우, **기관 비교** 또는 **규정 검색**을 이용하세요._"
    )


def _fallback_gap_review_summary(
    target_org: str, topic: str, row: dict[str, Any] | None
) -> str:
    """검토 권고 시 LLM 미사용 fallback."""
    checklist_topic = (row or {}).get("topic", topic)
    status = (row or {}).get("target_status", "없음")
    others = (row or {}).get("others_have_count", 0)
    art = (row or {}).get("target_article") or {}
    label = art.get("label") or "관련 조문 미확인"

    lines = [
        f"**검토 권고:** **{target_org}**의 **「{checklist_topic}」** 항목이 "
        f"**{status}**으로, 타 기관 **{others}곳** 대비 상대적으로 미흡합니다.",
        "",
        f"**기준 기관 현황:** {label}",
    ]
    if art.get("excerpt"):
        snippet = art["excerpt"].replace("\n", " ")[:220]
        lines.append(f"> {snippet}…")
    lines.append("")
    lines.append("_아래 타 기관 조문을 참고하여 보완 검토를 진행하세요._")
    return "\n".join(lines)


def _summarize_gap_review_with_llm(
    target_org: str,
    topic: str,
    row: dict[str, Any] | None,
    target_hits: list[HybridHit],
    other_hits: list[HybridHit],
) -> str:
    if not _openai_available():
        return _fallback_gap_review_summary(target_org, topic, row)

    from src.openai_client import get_openai_client

    checklist_topic = (row or {}).get("topic", topic)
    status = (row or {}).get("target_status", "없음")
    others = (row or {}).get("others_have_count", 0)

    context_parts = [
        f"기준 기관: {target_org}",
        f"주제: {checklist_topic}",
        f"체크리스트 판정: {status} (타 기관 {others}곳 보유 → 검토 권고)",
        "",
        "## 기준 기관 조문",
    ]
    if target_hits:
        for i, hit in enumerate(target_hits[:3], start=1):
            context_parts.append(
                f"[{i}] {hit.article.label}\n{hit.article.body[:1200]}"
            )
    else:
        context_parts.append("(관련 조문 없음 또는 매우 약함)")

    context_parts.extend(["", "## 타 기관 조문 (참고)"])
    for i, hit in enumerate(other_hits[:5], start=1):
        context_parts.append(
            f"[{i}] {hit.article.org} | {hit.article.label}\n{hit.article.body[:1200]}"
        )

    context = "\n\n".join(context_parts)
    client = get_openai_client()
    system = (
        "당신은 공공기관 사규관리규정 벤치마킹 분석 AI입니다. "
        "기준 기관은 체크리스트상 해당 주제가 없거나 약한 상태입니다. "
        "제공된 조문만 근거로, 기준 기관에서 보완·검토가 필요한 구체적 차이를 "
        "3~5개 bullet로 설명하세요. 타 기관 조문에 있으나 기준 기관 조문에서 "
        "확인되지 않는 내용만 제시하고, 추측하지 마세요."
    )
    user = f"분석 요청:\n{context}"

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        return _fallback_gap_review_summary(target_org, topic, row)
    return (
        f"**검토 권고:** **{target_org}**의 **「{checklist_topic}」** 항목이 "
        f"타 기관 대비 **{status}**합니다.\n\n{content}"
    )


def _article_dict_to_citation(art: dict[str, Any], org: str) -> dict[str, Any] | None:
    if not art or not art.get("label"):
        return None
    return {
        "org": org,
        "article_no": "",
        "title": "",
        "label": art.get("label", ""),
        "source_file": "",
        "excerpt": art.get("excerpt", ""),
        "matched_terms": art.get("matched_terms", []),
    }


def _find_article_by_label(articles, org: str, label: str):
    for article in articles:
        if article.org == org and article.label == label:
            return article
    return None


def _hits_from_matrix_row(
    row: dict[str, Any], articles, target_org: str
) -> tuple[list[HybridHit], list[HybridHit], dict[str, dict[str, Any]]]:
    """체크리스트 매트릭스에서 기준·타 기관 조문을 추출."""
    target_hits: list[HybridHit] = []
    other_hits: list[HybridHit] = []
    others: dict[str, dict[str, Any]] = {}

    for org, info in row.get("by_org", {}).items():
        art_dict = info.get("article")
        if not art_dict or not art_dict.get("label"):
            continue
        article = _find_article_by_label(articles, org, art_dict["label"])
        if not article:
            continue
        hit = HybridHit(
            article=article,
            score=info.get("score", 0.0),
            keyword_score=info.get("score", 0.0),
            semantic_score=0.0,
            matched_terms=art_dict.get("matched_terms", []),
        )
        if org == target_org:
            target_hits.append(hit)
        elif info.get("status") == "있음":
            other_hits.append(hit)
            others[org] = _article_dict_to_citation(art_dict, org)

    return target_hits, other_hits, others


def run_gap_detection(target_org: str, topic: str) -> dict[str, Any]:
    articles = _load_articles()
    matrix = build_coverage_matrix(articles, target_org)
    row = next((r for r in matrix if topic in r["topic"] or topic in r["description"]), None)
    search_topic = row["topic"] if row else topic

    if row:
        review_needed = row["review_needed"]
        target_hits, other_hits, others = _hits_from_matrix_row(row, articles, target_org)
        if not other_hits:
            hits = hybrid_search(articles, search_topic, limit=20)
            target_hits = [h for h in hits if h.article.org == target_org]
            other_hits = [h for h in hits if h.article.org != target_org]
            others = {
                h.article.org: _format_hybrid_citations([h])[0] for h in other_hits
            }
    else:
        from src.search import find_missing_topics

        legacy = find_missing_topics(articles, target_org, topic)
        review_needed = legacy.get("review_needed", False)
        hits = hybrid_search(articles, search_topic, limit=20)
        target_hits = [h for h in hits if h.article.org == target_org]
        other_hits = [h for h in hits if h.article.org != target_org]
        others = {
            h.article.org: _format_hybrid_citations([h])[0] for h in other_hits
        }

    if review_needed:
        summary = _summarize_gap_review_with_llm(
            target_org, topic, row, target_hits, other_hits
        )
    else:
        summary = _fallback_gap_ok_summary(target_org, topic, row)

    target_citation = None
    if row:
        target_citation = _article_dict_to_citation(
            row.get("target_article") or {}, target_org
        )

    reference_orgs: dict[str, dict[str, Any]] = {}
    if row and not review_needed:
        for org, info in row.get("by_org", {}).items():
            if org == target_org or info.get("status") != "있음":
                continue
            cit = _article_dict_to_citation(info.get("article") or {}, org)
            if cit:
                reference_orgs[org] = cit

    return {
        "target_org": target_org,
        "topic": topic,
        "review_needed": review_needed,
        "topic_row": row,
        "summary": summary,
        "target_citation": target_citation,
        "other_orgs": others if review_needed else {},
        "reference_orgs": reference_orgs,
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


def _fallback_report_summary(report: dict[str, Any]) -> str:
    target = report["target_org"]
    stats = report["stats"]
    lines = [
        f"**{target}** 사규관리규정 벤치마킹 결과입니다.",
        "",
        f"- 체크리스트 **{stats['total_topics']}**개 중 "
        f"**있음 {stats['ok']}** · **약함 {stats['weak']}** · **없음 {stats['missing']}**",
    ]
    review_items = report.get("review_items") or []
    if review_items:
        lines.append(f"- **검토 권고 {len(review_items)}건** — 타 기관 대비 보완 검토가 필요합니다.")
        lines.append("")
        for item in review_items[:6]:
            lines.append(
                f"  · **{item['topic']}**: {item['description']} "
                f"(타 기관 {item['others_have_count']}곳 보유)"
            )
    else:
        lines.append("- **검토 권고 항목 없음** — 전반적 커버리지가 양호합니다.")
    lines.append("")
    lines.append("_상세 현황은 아래 체크리스트·히트맵을 참고하세요._")
    return "\n".join(lines)


def _build_report_llm_context(report: dict[str, Any]) -> str:
    target = report["target_org"]
    stats = report["stats"]
    others = [o for o in report.get("orgs", []) if o != target]
    lines = [
        f"기준 기관: {target}",
        f"비교 기관: {', '.join(others)}",
        f"체크리스트: 있음 {stats['ok']} / 약함 {stats['weak']} / 없음 {stats['missing']}",
        "",
        "## 검토 권고 항목",
    ]
    review_items = report.get("review_items") or []
    if review_items:
        for item in review_items:
            art = item.get("target_article") or {}
            lines.append(
                f"- {item['topic']} ({item['description']}): "
                f"기준 기관 {item['target_status']}, "
                f"타 기관 {item['others_have_count']}곳 보유"
            )
            if art.get("label"):
                lines.append(f"  참고(타 기관): {art.get('label', '')}")
    else:
        lines.append("- 없음")

    lines.extend(["", "## 기준 기관 체크리스트 현황"])
    for row in report.get("coverage_matrix", []):
        art = row.get("target_article") or {}
        label = art.get("label") or "-"
        lines.append(f"- {row['topic']}: {row['target_status']} | {label}")
    return "\n".join(lines)


def summarize_report_with_llm(report: dict[str, Any]) -> str:
    if not _openai_available():
        return _fallback_report_summary(report)

    from src.openai_client import get_openai_client

    target = report["target_org"]
    context = _build_report_llm_context(report)
    client = get_openai_client()
    system = (
        "당신은 공공기관 사규관리규정 벤치마킹 보고서 작성 보조 AI입니다. "
        "제공된 체크리스트 분석 결과만 근거로 3~5문단 요약을 작성하세요. "
        "개요, 검토 권고 항목(있을 경우), 전반적 평가 순으로 작성하고 "
        "없는 내용은 추측하지 마세요."
    )
    user = f"기준 기관: {target}\n\n분석 결과:\n{context}"

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content
    return content or _fallback_report_summary(report)


def run_benchmark_report(target_org: str) -> dict[str, Any]:
    articles = _load_articles()
    report = build_benchmark_report(articles, target_org)
    report["ai_summary"] = summarize_report_with_llm(report)
    report["ai_enabled"] = _openai_available()
    return report
