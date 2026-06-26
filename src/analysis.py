"""비교표·Gap 매트릭스·벤치마킹 리포트 생성."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.parser import Article
from src.retriever import HybridHit, hybrid_search
from src.topics import TOPIC_TAXONOMY, all_topics


def _best_hit_per_org(articles: list[Article], topic: str) -> dict[str, HybridHit | None]:
    hits = hybrid_search(articles, topic, limit=50)
    by_org: dict[str, HybridHit | None] = {}
    for org in sorted({a.org for a in articles}):
        org_hit = next((h for h in hits if h.article.org == org), None)
        by_org[org] = org_hit
    return by_org


def _coverage_status(score: float) -> str:
    if score >= 0.35:
        return "있음"
    if score >= 0.12:
        return "약함"
    return "없음"


def build_coverage_matrix(articles: list[Article], target_org: str) -> list[dict[str, Any]]:
    orgs = sorted({a.org for a in articles})
    rows: list[dict[str, Any]] = []

    for topic in all_topics():
        by_org = _best_hit_per_org(articles, topic)
        target_hit = by_org.get(target_org)
        target_score = target_hit.score if target_hit else 0.0
        target_status = _coverage_status(target_score)

        other_scores = [
            h.score for org, h in by_org.items() if org != target_org and h
        ]
        others_have = sum(1 for s in other_scores if s >= 0.35)
        review_needed = target_status in {"없음", "약함"} and others_have >= 2

        rows.append(
            {
                "topic": topic,
                "description": TOPIC_TAXONOMY[topic]["description"],
                "target_status": target_status,
                "target_score": round(target_score, 3),
                "target_article": _hit_summary(target_hit),
                "others_have_count": others_have,
                "review_needed": review_needed,
                "by_org": {
                    org: {
                        "status": _coverage_status(h.score if h else 0.0),
                        "score": round(h.score, 3) if h else 0.0,
                        "article": _hit_summary(h),
                    }
                    for org, h in by_org.items()
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
    weak_count = sum(1 for r in matrix if r["target_status"] == "약함")
    missing_count = sum(1 for r in matrix if r["target_status"] == "없음")

    orgs = sorted({a.org for a in articles})
    summary_lines = [
        f"# 사규관리규정 벤치마킹 보고서",
        f"",
        f"**기준 기관:** {target_org}",
        f"**비교 기관:** {', '.join(o for o in orgs if o != target_org)}",
        f"**생성 일시:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"",
        f"## 1. 개요",
        f"- 분석 주제: {len(matrix)}개",
        f"- 기준 기관 커버리지: 있음 {ok_count} / 약함 {weak_count} / 없음 {missing_count}",
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

    summary_lines.extend(["", "## 3. 주제별 현황"])
    for row in matrix:
        icon = {"있음": "✅", "약함": "⚠️", "없음": "❌"}[row["target_status"]]
        summary_lines.append(
            f"- {icon} **{row['topic']}** ({row['target_status']}) — {row['description']}"
        )

    summary_lines.extend(
        [
            "",
            "## 4. 활용 안내",
            "본 보고서는 AI·키워드 분석 결과이며, 최종 판단은 조문 원문 및 담당자 검토가 필요합니다.",
        ]
    )

    return {
        "target_org": target_org,
        "orgs": orgs,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_matrix": matrix,
        "review_items": review_items,
        "stats": {
            "total_topics": len(matrix),
            "ok": ok_count,
            "weak": weak_count,
            "missing": missing_count,
            "review_count": len(review_items),
        },
        "report_markdown": "\n".join(summary_lines),
    }
