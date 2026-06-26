"""사규관리규정 주제 분류 및 동의어."""

from __future__ import annotations

TOPIC_TAXONOMY: dict[str, dict] = {
    "목적 및 정의": {
        "keywords": ["목적", "정의", "용어", "사규", "세칙", "관리부서", "운용부서"],
        "description": "규정의 목적, 용어 정의, 조직 역할",
    },
    "입안예고": {
        "keywords": ["입안예고", "입안 예고", "규정안 예고", "의견수렴", "의견 제출"],
        "description": "대외 입안예고 절차 및 기간",
    },
    "제개정 예고": {
        "keywords": ["제·개정 예고", "제개정 예고", "개정 예고", "내부 예고"],
        "description": "내부 제·개정 예고 절차",
    },
    "입안 및 심의": {
        "keywords": ["입안", "심의", "심의요청", "사규심의위원회"],
        "description": "입안·심의 절차",
    },
    "확정 및 시행": {
        "keywords": ["확정", "결재", "의결", "시행", "효력"],
        "description": "사규 확정·시행 절차",
    },
    "사규 공개": {
        "keywords": ["공개", "비공개", "게시", "공개심의"],
        "description": "사규 공개·비공개 기준",
    },
    "작성형식": {
        "keywords": ["작성형식", "장", "절", "조", "항", "별표", "별지"],
        "description": "사규 작성 형식·체계",
    },
    "직권 개정": {
        "keywords": ["직권", "직권 개정", "정비"],
        "description": "관리부서 직권 개정",
    },
    "사규 관리": {
        "keywords": ["적정화", "개정", "관리", "사규관리시스템", "기록", "보존"],
        "description": "사규 유지·관리·적정화",
    },
    "담당자 지정": {
        "keywords": ["담당자", "운용사규별", "담당", "지정"],
        "description": "운용부서 사규 담당자",
    },
    "부패영향평가": {
        "keywords": ["부패영향평가", "부패 영향", "부패유발"],
        "description": "사규 심의 시 부패영향평가",
    },
    "규제입증책임": {
        "keywords": ["규제입증", "규제입증책임", "규제"],
        "description": "규제입증책임위원회·규제 심의",
    },
    "기준 운용": {
        "keywords": ["기준", "절차서", "지침", "요령", "편람"],
        "description": "사규 외 기준·지침 운용",
    },
    "심의위원회": {
        "keywords": ["위원회", "위원", "소집", "의결", "간사"],
        "description": "사규심의위원회 구성·운영",
    },
    "해석 및 효력": {
        "keywords": ["해석", "효력", "법령", "상위", "하위"],
        "description": "사규 해석·효력·상하위 관계",
    },
}


def expand_topic_query(topic: str) -> list[str]:
    """주제명 또는 키워드 → 검색어 목록."""
    terms = [topic.strip()]
    for name, meta in TOPIC_TAXONOMY.items():
        if topic in name or name in topic:
            terms.append(name)
            terms.extend(meta["keywords"])
        for kw in meta["keywords"]:
            if kw in topic or topic in kw:
                terms.extend(meta["keywords"])
                terms.append(name)
                break
    terms.extend({t.replace(" ", "") for t in terms})
    return list(dict.fromkeys(t for t in terms if t))


def all_topics() -> list[str]:
    return list(TOPIC_TAXONOMY.keys())
