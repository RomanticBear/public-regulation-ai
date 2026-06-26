# 사규관리규정 AI 벤치마킹 — v0.3

## DB 구조

| 저장소 | 역할 | 위치 |
|--------|------|------|
| **SQLite** | 조문 원문·메타데이터 | `processed/regulation.db` |
| **Chroma** | OpenAI Embedding 벡터 | `processed/chroma/` |

## 필수: API Key

`.env`에 `OPENAI_API_KEY` **필수** (검색 embedding + AI 요약)

```powershell
copy .env.example .env
```

| 용도 | 환경변수 |
|------|----------|
| Embedding (조문 벡터) | `OPENAI_EMBEDDING_MODEL=text-embedding-3-small` |
| LLM (답변 요약) | `OPENAI_MODEL=gpt-4o-mini` |
| 회사망 SSL | `OPENAI_SSL_VERIFY=false` |

## 실행

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
py -m uvicorn backend.main:app --reload --port 8000
```

## 재색인

```powershell
py scripts/rebuild_embeddings.py
```

## 검색

```
질문 → OpenAI Embedding → Chroma 유사 조문
     + 키워드(동의어) 보조
     → LLM 요약 + 조문 근거
```

청크 단위: **조문(Article)**
