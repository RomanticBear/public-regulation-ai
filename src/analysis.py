"""비교표·Gap 매트릭스·벤치마킹 리포트 생성."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from src.parser import Article
from src.retriever import HybridHit, hybrid_search
from src.topics import BENCHMARK_CHECKLIST, all_topics, checklist_count

# hybrid 모드: 의미 검색 점수 기준
SEMANTIC_OK = 0.40
SEMANTIC_WEAK = 0.22

MatchSource = Literal["anchor", "semantic"] | None
MatchMode = Literal["strict", "hybrid"]


@dataclass
class OrgMatch:
    article: Article | None
    score: float
    matched_terms: list[str]
    source: MatchSource
    status: str


def _article_haystack(article: Article) -> str:
    return f"{article.article_no} {article.title} {article.body}"


def _article_title_haystack(article: Article) -> str:
    return f"{article.article_no} {article.title}"


def _matches_anchors(article: Article, meta: dict) -> tuple[bool, list[str]]:
    haystack = _article_haystack(article)

    kw_matched = [kw for kw in meta.get("anchor_keywords", []) if kw in haystack]
    if kw_matched:
        return True, kw_matched

    groups = meta.get("anchor_groups")
    if groups:
        group_matched: list[str] = []
        for group in groups:
            found = [kw for kw in group if kw in haystack]
            if not found:
                break
            group_matched.extend(found)
        else:
            return True, group_matched

    return False, []


def _score_anchor_match(article: Article, matched_terms: list[str]) -> float:
    if not matched_terms:
        return 0.0
    title = _article_title_haystack(article)
    if any(term in title for term in matched_terms):
        return 1.0
    return 0.85


def _best_anchor_match(
    org_articles: list[Article], meta: dict
) -> tuple[Article | None, float, list[str]]:
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
    return best, best_score, best_terms


def _best_semantic_hit(articles: list[Article], topic: str, org: str) -> HybridHit | None:
    hits = hybrid_search(articles, topic, org=org, limit=3)
    return hits[0] if hits else None


def _resolve_org_match(
    articles: list[Article], topic: str, meta: dict, org: str
) -> OrgMatch:
    mode: MatchMode = meta.get("match_mode", "hybrid")
    org_articles = [a for a in articles if a.org == org]

    anchor_art, anchor_score, anchor_terms = _best_anchor_match(org_articles, meta)
    if anchor_art:
        return OrgMatch(anchor_art, anchor_score, anchor_terms, "anchor", "있음")

    sem = _best_semantic_hit(articles, topic, org)
    if not sem or sem.score < SEMANTIC_WEAK:
        return OrgMatch(None, 0.0, [], None, "없음")

    terms = list(dict.fromkeys([*sem.matched_terms, "AI유사도"]))
    if mode == "strict":
        return OrgMatch(sem.article, sem.score, terms, "semantic", "약함")

    if sem.score >= SEMANTIC_OK:
        return OrgMatch(sem.article, sem.score, terms, "semantic", "있음")
    return OrgMatch(sem.article, sem.score, terms, "semantic", "약함")


def _best_article_per_org(
    articles: list[Article], topic: str, meta: dict
) -> dict[str, OrgMatch]:
    return {
        org: _resolve_org_match(articles, topic, meta, org)
        for org in sorted({a.org for a in articles})
    }


def _article_summary(match: OrgMatch) -> dict[str, str] | None:
    if not match.article:
        return None
    summary: dict[str, str] = {
        "org": match.article.org,
        "label": match.article.label,
        "excerpt": match.article.body[:200],
        "matched_terms": match.matched_terms,
    }
    if match.source:
        summary["match_source"] = match.source
    return summary


def build_coverage_matrix(articles: list[Article], target_org: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for topic in all_topics():
        meta = BENCHMARK_CHECKLIST[topic]
        by_org = _best_article_per_org(articles, topic, meta)

        target = by_org.get(target_org, OrgMatch(None, 0.0, [], None, "없음"))
        target_status = target.status

        others_have = sum(
            1
            for org, match in by_org.items()
            if org != target_org and match.status == "있음"
        )
        review_needed = target_status in {"없음", "약함"} and others_have >= 2

        rows.append(
            {
                "topic": topic,
                "description": meta["description"],
                "target_status": target_status,
                "target_score": round(target.score, 3),
                "target_article": _article_summary(target),
                "others_have_count": others_have,
                "review_needed": review_needed,
                "by_org": {
                    org: {
                        "status": match.status,
                        "score": round(match.score, 3),
                        "article": _article_summary(match),
                    }
                    for org, match in by_org.items()
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


# 규정 내용 비교 — 절차·의무 등 실질 항목
_COMPARE_ASPECTS: list[tuple[str, str]] = [
    ("실시", "실시 의무·절차"),
    ("생략", "생략·면제 조건"),
    ("통보", "결과 통보·제출"),
    ("반영", "심의·의사결정 반영"),
    ("체크리스트", "체크리스트·점검표"),
    ("의견", "의견 수렴·조정"),
    ("심의", "심의·심의위원회"),
    ("공개", "공개·게시"),
    ("예고", "예고·고시"),
    ("직권", "직권 개정"),
    ("적정화", "적정화·폐지"),
    ("해석", "해석 주체·절차"),
    ("대상", "적용 대상·범위"),
    ("요청", "요청·의뢰 절차"),
]


def _snippet_around(text: str, keyword: str, *, width: int = 72) -> str:
    idx = text.find(keyword)
    if idx < 0:
        return ""
    start = max(0, idx - 18)
    end = min(len(text), idx + width)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"
    return snippet


def _extract_numbered_items(body: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", item).strip()
        for item in re.findall(r"(?:^|\n)\s*\d+\.\s*([^\n]+)", body)
        if item.strip()
    ]


def _item_keywords(item: str) -> set[str]:
    tokens = re.findall(r"[가-힣]{2,}", item)
    stop = {"하여야", "한다", "하는", "있는", "경우", "대하여", "따라", "수", "등"}
    return {t for t in tokens if t not in stop and len(t) >= 2}


def _items_overlap(item: str, other_body: str) -> bool:
    keywords = _item_keywords(item)
    if not keywords:
        return False
    hits = sum(1 for kw in keywords if kw in other_body)
    return hits >= max(1, len(keywords) // 2)


def build_compare_insights(
    hits_a: list[HybridHit],
    hits_b: list[HybridHit],
    org_a: str,
    org_b: str,
    topic: str,
) -> tuple[list[str], list[str]]:
    """조문 내용 기준 공통점·차이점 (규칙 기반)."""
    a = hits_a[0] if hits_a else None
    b = hits_b[0] if hits_b else None
    common: list[str] = []
    diffs: list[str] = []

    if not a and b:
        diffs.append(
            f"**{org_a}**에는 '{topic}' 관련 전용 조문이 확인되지 않습니다. "
            f"**{org_b}** {b.article.label}에 관련 규정이 있습니다."
        )
        return common, diffs
    if a and not b:
        diffs.append(
            f"**{org_b}**에는 '{topic}' 관련 전용 조문이 확인되지 않습니다. "
            f"**{org_a}** {a.article.label}에 관련 규정이 있습니다."
        )
        return common, diffs
    if not a or not b:
        diffs.append(f"두 기관 모두 '{topic}' 관련 조문을 찾지 못했습니다.")
        return common, diffs

    body_a, body_b = a.article.body, b.article.body

    for keyword, label in _COMPARE_ASPECTS:
        in_a, in_b = keyword in body_a, keyword in body_b
        if in_a and in_b:
            common.append(f"**{label}**: 두 기관 모두 규정")
        elif in_a and not in_b:
            snippet = _snippet_around(body_a, keyword)
            detail = f" — {snippet}" if snippet else ""
            diffs.append(f"**{org_a}**만 **{label}** 명시{detail}")
        elif in_b and not in_a:
            snippet = _snippet_around(body_b, keyword)
            detail = f" — {snippet}" if snippet else ""
            diffs.append(f"**{org_b}**만 **{label}** 명시{detail}")

    items_a = _extract_numbered_items(body_a)
    items_b = _extract_numbered_items(body_b)
    if items_a and items_b:
        only_a = [it for it in items_a if not _items_overlap(it, body_b)][:3]
        only_b = [it for it in items_b if not _items_overlap(it, body_a)][:3]
        for item in only_a:
            diffs.append(f"**{org_a}** 세부 항목: {item[:90]}{'…' if len(item) > 90 else ''}")
        for item in only_b:
            diffs.append(f"**{org_b}** 세부 항목: {item[:90]}{'…' if len(item) > 90 else ''}")

    if not common and not diffs:
        diffs.append(
            f"두 기관 모두 '{topic}' 관련 조문({a.article.label}, {b.article.label})을 "
            "두고 있으나, 자동 추출 가능한 세부 차이가 제한적입니다. AI 요약을 참고하세요."
        )

    return common[:6], diffs[:8]


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

    common_points, differences = build_compare_insights(
        hits_a, hits_b, org_a, org_b, topic
    )

    return {
        "comparison_table": comparison_table,
        "common_points": common_points,
        "differences": differences,
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
        f"- 분석 체크리스트: {n}개 (앵커 키워드 + AI 의미 검색)",
        f"- 기준 기관: 있음 {ok_count} / 약함 {weak_count} / 없음 {missing_count}",
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
        icon = {"있음": "✅", "약함": "⚠️", "없음": "❌"}[row["target_status"]]
        summary_lines.append(
            f"- {icon} **{row['topic']}** ({row['target_status']}) — {row['description']}"
        )

    summary_lines.extend(
        [
            "",
            "## 4. 활용 안내",
            "- **있음**: 조문에 체크 키워드가 확인되었거나 AI 유사도가 충분히 높음",
            "- **약함**: 관련 조문이 유사하게 검색됨 — 원문 확인 권장",
            "- **없음**: 관련 조문을 찾지 못함",
            "최종 판단은 조문 원문 및 담당자 검토가 필요합니다.",
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
            "weak": weak_count,
            "missing": missing_count,
            "review_count": len(review_items),
        },
        "report_markdown": "\n".join(summary_lines),
    }
