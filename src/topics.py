"""벤치마킹 체크리스트(사실 확인형) 및 검색 동의어."""

from __future__ import annotations

# 벤치마킹·Gap·리포트 히트맵 — 전 기관 동일 기준
BENCHMARK_CHECKLIST: dict[str, dict] = {
    "대외 입안예고": {
        "description": "규정안 대외 입안·사전예고 절차",
        "keywords": ["입안예고", "입안 예고", "사전예고", "규정안 예고"],
        "anchor_keywords": ["입안예고", "입안 예고", "사전예고", "규정안 예고"],
    },
    "사내 제·개정 예고": {
        "description": "내부 제·개정 예고·의견수렴",
        "keywords": ["제·개정 예고", "제개정 예고", "의견수렴", "의견 수렴"],
        "anchor_keywords": ["제·개정 예고", "제개정 예고", "의견수렴", "의견 수렴"],
    },
    "부패영향평가": {
        "description": "부패영향평가 전용 조문·절차",
        "keywords": ["부패영향평가", "부패 영향", "부패유발"],
        "anchor_keywords": ["부패영향평가"],
    },
    "사규심의위원회": {
        "description": "별도 사규심의위원회 설치·운영",
        "keywords": ["사규심의위원회", "사규 심의위원회"],
        "anchor_keywords": ["사규심의위원회", "사규 심의위원회"],
    },
    "직권 개정": {
        "description": "관리부서 직권 개정·정비",
        "keywords": ["직권", "직권 개정", "직권개정", "정비"],
        "anchor_groups": [["직권"], ["개정", "정비"]],
    },
    "사규 공개": {
        "description": "사규 공개 원칙·방법",
        "keywords": ["사규의 공개", "사규 공개", "공개"],
        "anchor_keywords": ["사규의 공개", "사규 공개", "사규를 공개"],
    },
    "비공개 사유": {
        "description": "비공개 대상·사유 규정",
        "keywords": ["비공개", "공개하지 아니", "비공개대상"],
        "anchor_keywords": ["비공개", "공개하지 아니", "비공개대상"],
    },
    "부분공개 규정": {
        "description": "사규 일부공개·부분공개",
        "keywords": ["부분공개", "일부공개", "부분 공개"],
        "anchor_keywords": ["부분공개", "일부공개", "부분 공개"],
    },
    "별지·서식 체계": {
        "description": "별지·별표 서식 규정",
        "keywords": ["별지 제", "별표", "별지"],
        "anchor_keywords": ["별지 제", "별표"],
    },
    "신·구조문 대비표": {
        "description": "개정 시 신·구조문 대비표",
        "keywords": ["신·구조문", "신구조문", "대비표"],
        "anchor_keywords": ["신·구조문", "신구조문", "대비표"],
    },
    "사규 해석": {
        "description": "사규 해석 주체·절차",
        "keywords": ["해석"],
        "anchor_keywords": ["(해석)", "해석에 관", "해석) ", "해석 및"],
    },
    "사규 적정화": {
        "description": "사규 정기·수시 적정화",
        "keywords": ["적정화"],
        "anchor_keywords": ["적정화"],
    },
}

# 하위 호환
TOPIC_TAXONOMY = BENCHMARK_CHECKLIST


def get_checklist_meta(topic: str) -> dict:
    return BENCHMARK_CHECKLIST[topic]


def all_topics() -> list[str]:
    return list(BENCHMARK_CHECKLIST.keys())


def checklist_count() -> int:
    return len(BENCHMARK_CHECKLIST)


def expand_topic_query(topic: str) -> list[str]:
    """주제명 또는 키워드 → 검색어 목록 (Q&A·유사조문용)."""
    q = topic.strip()
    terms = [q]

    for name, meta in BENCHMARK_CHECKLIST.items():
        keywords = meta.get("keywords", [])
        anchors = meta.get("anchor_keywords", [])
        all_kw = keywords + anchors
        for group in meta.get("anchor_groups", []):
            all_kw.extend(group)

        if q == name:
            terms.extend(all_kw)
            terms.append(name)
            break

        matched = False
        for kw in all_kw:
            if q == kw or (len(q) >= 2 and (q in kw or kw in q)):
                terms.extend(all_kw)
                terms.append(name)
                matched = True
                break
        if matched:
            break

    terms.extend({t.replace(" ", "") for t in terms})
    return list(dict.fromkeys(t for t in terms if t))
