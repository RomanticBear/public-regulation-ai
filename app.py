"""사규관리규정 벤치마킹 데모 (Streamlit)."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.parser import Article
from src.search import compare_by_topic, find_missing_topics, search_articles

ROOT = Path(__file__).parent
INDEX_FILE = ROOT / "processed" / "articles.json"


@st.cache_data
def load_articles() -> list[Article]:
    if not INDEX_FILE.exists():
        return []
    data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return [Article(**item) for item in data["articles"]]


def render_article(article: Article) -> None:
    st.markdown(f"**{article.org}** · `{article.label}`")
    st.caption(f"출처: {article.source_file}")
    st.text(article.body[:2000] + ("..." if len(article.body) > 2000 else ""))


st.set_page_config(
    page_title="사규관리규정 AI 벤치마킹 (데모)",
    page_icon="📋",
    layout="wide",
)

st.title("📋 사규관리규정 벤치마킹 데모")
st.caption("공공기관 사규관리규정 검색·비교 보조 도구 (PoC)")

articles = load_articles()

if not articles:
    st.warning(
        "아직 규정 데이터가 없습니다. 터미널에서 아래 명령을 실행해 주세요.\n\n"
        "```\n"
        "python -m venv .venv\n"
        ".venv\\Scripts\\activate\n"
        "pip install -r requirements.txt\n"
        "python scripts/build_index.py\n"
        "streamlit run app.py\n"
        "```"
    )
    st.stop()

orgs = sorted({a.org for a in articles})
meta_cols = st.columns(4)
meta_cols[0].metric("기관 수", len(orgs))
meta_cols[1].metric("조문 수", len(articles))
meta_cols[2].metric("규정", articles[0].regulation if articles else "-")
meta_cols[3].metric("모드", "키워드 검색 (데모)")

st.divider()

tab_search, tab_compare, tab_missing = st.tabs(
    ["🔍 조문 검색", "⚖️ 기관 비교", "📌 검토 권고 항목"]
)

with tab_search:
    st.subheader("자연어 질의 (키워드 기반)")
    query = st.text_input(
        "질문",
        placeholder="예: 입안예고 기간은 어떻게 되나요?",
        key="search_query",
    )
    if st.button("검색", type="primary") and query:
        hits = search_articles(articles, query, limit=15)
        if not hits:
            st.info("관련 조문을 찾지 못했습니다. 다른 키워드로 시도해 보세요.")
        else:
            st.success(f"{len(hits)}건 관련 조문")
            for hit in hits:
                with st.expander(
                    f"{hit.article.org} · {hit.article.label} (점수 {hit.score:.0f})"
                ):
                    st.caption(f"매칭: {', '.join(hit.matched_terms)}")
                    render_article(hit.article)

with tab_compare:
    st.subheader("두 기관 비교")
    c1, c2, c3 = st.columns([1, 1, 2])
    org_a = c1.selectbox("기관 A", orgs, index=0)
    org_b = c2.selectbox("기관 B", orgs, index=min(1, len(orgs) - 1))
    topic = c3.text_input("비교 주제", placeholder="예: 입안예고", key="compare_topic")

    if st.button("비교하기", type="primary") and topic:
        hits_a, hits_b = compare_by_topic(articles, org_a, org_b, topic)
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"### {org_a}")
            if hits_a:
                for hit in hits_a:
                    render_article(hit.article)
                    st.divider()
            else:
                st.info("관련 조문 없음")
        with col_b:
            st.markdown(f"### {org_b}")
            if hits_b:
                for hit in hits_b:
                    render_article(hit.article)
                    st.divider()
            else:
                st.info("관련 조문 없음")

with tab_missing:
    st.subheader("검토 권고 항목 탐지 (데모)")
    st.caption(
        "타 기관에는 관련 조문이 있으나, 지정 기관에서 약하게 매칭되는 주제를 표시합니다. "
        "최종 판단은 담당자가 원문을 확인해야 합니다."
    )
    target = st.selectbox("기준 기관", orgs, index=orgs.index("한국수자원공사") if "한국수자원공사" in orgs else 0)
    topic_m = st.text_input("주제", placeholder="예: 사후평가, 규제입증", key="missing_topic")

    if st.button("검토 항목 찾기", type="primary") and topic_m:
        result = find_missing_topics(articles, target, topic_m)
        if result["review_needed"]:
            st.warning(
                f"**{target}** 에서 '{topic_m}' 관련 조문이 다른 기관 대비 약합니다. 검토를 권고합니다."
            )
        else:
            st.info("명확한 누락 신호는 없습니다. 아래 결과를 참고해 주세요.")

        for org, hits in result["others"].items():
            if org == target:
                continue
            with st.expander(f"{org} — {hits[0].article.label}"):
                render_article(hits[0].article)

st.divider()
st.caption(
    "⚠️ 본 화면은 데모입니다. AI/키워드 분석 결과이며, "
    "법적 효력 및 최종 판단은 조문 원문과 담당자 검토가 필요합니다."
)
