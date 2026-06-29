"""비교표·Gap 매트릭스·벤치마킹 리포트 생성."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.parser import Article
from src.retriever import HybridHit
from src.topics import BENCHMARK_CHECKLIST, all_topics, checklist_count


def _article_haystack(article: Article) -> str:
    return f"{article.article_no} {article.title} {article.body}"


def _article_title_haystack(article: Article) -> str:
    return f"{article.article_no} {article.title}"


def _matches_anchors(article: Article, meta: dict) -> tuple[bool, list[str]]:
    haystack = _article_haystack(article)
    matched: list[str] = []

    groups = meta.get("anchor_groups")
    if groups:
        for group in groups:
            found = [kw for kw in group if kw in haystack]
            if not found:
                return False, []
            matched.extend(found)
        return True, matched

    for kw in meta.get("anchor_keywords", []):
        if kw in haystack:
            matched.append(kw)
    return bool(matched), matched


def _score_anchor_match(article: Article, matched_terms: list[str]) -> float:
    if not matched_terms:
        return 0.0
    title = _article_title_haystack(article)
    if any(term in title for term in matched_terms):
        return 1.0
    return 0.85


def _best_article_per_org(
    articles: list[Article], meta: dict
) -> dict[str, tuple[Article | None, float, list[str]]]:
    by_org: dict[str, tuple[Article | None, float, list[str]]] = {}
    for org in sorted({a.org for a in articles}):
        org_articles = [a for a in articles if a.org == org]
        best: Article | None = None
        best_score = 0.0
        best_terms: list[str] = []
        for article in org_articles:
            ok, terms = _matches_anchors(article, meta)
            if not ok:
                continue
            score = _score_anchor_match(article, terms)
            if score > best_score:
                best = article
                best_score = score
                best_terms = terms
        by_org[org] = (best, best_score, best_terms)
    return by_org


def _coverage_status(has_match: bool) -> str:
    return "있음" if has_match else "없음"


def _article_summary(article: Article | None, matched_terms: list[str]) -> dict[str, str] | None:
    if not article:
        return None
    return {
        "org": article.org,
        "label": article.label,
        "excerpt": article.body[:200],
        "matched_terms": matched_terms,
    }


def build_coverage_matrix(articles: list[Article], target_org: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for topic in all_topics():
        meta = BENCHMARK_CHECKLIST[topic]
        by_org = _best_article_per_org(articles, meta)

        target_article, target_score, target_terms = by_org.get(target_org, (None, 0.0, []))
        target_status = _coverage_status(target_article is not None)

        others_have = sum(
            1
            for org, (art, _, _) in by_org.items()
            if org != target_org and art is not None
        )
        review_needed = target_status == "없음" and others_have >= 2

        rows.append(
            {
                "topic": topic,
                "description": meta["description"],
                "target_status": target_status,
                "target_score": round(target_score, 3),
                "target_article": _article_summary(target_article, target_terms),
                "others_have_count": others_have,
                "review_needed": review_needed,
                "by_org": {
                    org: {
                        "status": _coverage_status(art is not None),
                        "score": round(score, 3),
                        "article": _article_summary(art, terms),
                    }
                    for org, (art, score, terms) in by_org.items()
                },
            }
        )
    return rows


def _hit_summary(hit: HybridHit | None) -> dict[str, str] | None:
    if not hit:
        return None
    return {
        "org": hit.article.org,
        "label": hit.article.label,
        "excerpt": hit.article.body[:200],
    }


def build_compare_result(
    hits_a: list[HybridHit],
    hits_b: list[HybridHit],
    org_a: str,
    org_b: str,
    topic: str,
) -> dict[str, Any]:
    a = hits_a[0] if hits_a else None
    b = hits_b[0] if hits_b else None

    comparison_table = [
        {
            "항목": "관련 조문",
            org_a: a.article.label if a else "해당 없음",
            org_b: b.article.label if b else "해당 없음",
        },
        {
            "항목": "조문 제목",
            org_a: a.article.title if a else "-",
            org_b: b.article.title if b else "-",
        },
        {
            "항목": "주요 내용 (발췌)",
            org_a: (a.article.body[:300] + "...") if a else "-",
            org_b: (b.article.body[:300] + "...") if b else "-",
        },
    ]

    common_points: list[str] = []
    differences: list[str] = []

    if a and b:
        if a.article.title and b.article.title:
            if any(k in a.article.title for k in topic.split()) or any(
                k in b.article.title for k in topic.split()
            ):
                common_points.append(f"두 기관 모두 '{topic}' 관련 조문을 두고 있습니다.")
        if a.article.title != b.article.title:
            differences.append(
                f"조문명 차이: {org_a} '{a.article.title or a.article.article_no}' "
                f"vs {org_b} '{b.article.title or b.article.article_no}'"
            )
        len_a, len_b = len(a.article.body), len(b.article.body)
        if abs(len_a - len_b) > 200:
            differences.append(
                f"조문 분량 차이: {org_a} {len_a}자 vs {org_b} {len_b}자"
            )
    elif a and not b:
        differences.append(f"{org_b}에서는 '{topic}' 관련 조문을 찾지 못했습니다.")
    elif b and not a:
        differences.append(f"{org_a}에서는 '{topic}' 관련 조문을 찾지 못했습니다.")

    return {
        "comparison_table": comparison_table,
        "common_points": common_points or ["자동 추출된 공통점이 없습니다. AI 요약을 참고하세요."],
        "differences": differences or ["자동 추출된 차이점이 없습니다. AI 요약을 참고하세요."],
    }


def build_benchmark_report(
    articles: list[Article],
    target_org: str,
) -> dict[str, Any]:
    matrix = build_coverage_matrix(articles, target_org)
    review_items = [row for row in matrix if row["review_needed"]]
    ok_count = sum(1 for r in matrix if r["target_status"] == "있음")
    missing_count = sum(1 for r in matrix if r["target_status"] == "없음")
    n = checklist_count()

    orgs = sorted({a.org for a in articles})
    summary_lines = [
        f"# 사규관리규정 벤치마킹 보고서",
        f"",
        f"**기준 기관:** {target_org}",
        f"**비교 기관:** {', '.join(o for o in orgs if o != target_org)}",
        f"**생성 일시:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"",
        f"## 1. 개요",
        f"- 분석 체크리스트: {n}개 (전 기관 동일 기준·앵커 키워드)",
        f"- 기준 기관: 있음 {ok_count} / 없음 {missing_count}",
        f"- 검토 권고 항목: {len(review_items)}개",
        f"",
        f"## 2. 검토 권고 항목",
    ]
    if review_items:
        for item in review_items:
            summary_lines.append(
                f"- **{item['topic']}**: {item['description']} "
                f"(타 기관 {item['others_have_count']}곳 보유)"
            )
    else:
        summary_lines.append("- 검토 권고 항목이 없습니다.")

    summary_lines.extend(["", "## 3. 체크리스트별 현황"])
    for row in matrix:
        icon = "✅" if row["target_status"] == "있음" else "❌"
        summary_lines.append(
            f"- {icon} **{row['topic']}** ({row['target_status']}) — {row['description']}"
        )

    summary_lines.extend(
        [
            "",
            "## 4. 활용 안내",
            "본 보고서는 조문 내 앵커 키워드 매칭 결과이며, 최종 판단은 조문 원문 및 담당자 검토가 필요합니다.",
        ]
    )

    return {
        "target_org": target_org,
        "orgs": orgs,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_matrix": matrix,
        "review_items": review_items,
        "stats": {
            "total_topics": n,
            "ok": ok_count,
            "weak": 0,
            "missing": missing_count,
            "review_count": len(review_items),
        },
        "report_markdown": "\n".join(summary_lines),
    }
