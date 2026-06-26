"""data/ 재색인 + OpenAI Embedding 벡터스토어 빌드."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database import init_db
from backend.services.ai_service import run_search
from backend.services.regulation_service import ingest_data_folder, stats
from src.retriever import get_search_backend
from src.vector_store import is_embedding_available, vector_store_stats


def main() -> None:
    if not is_embedding_available():
        print("[오류] .env에 OPENAI_API_KEY를 설정하세요.")
        sys.exit(1)

    init_db()
    results = ingest_data_folder(fresh=True)
    print("=== ingest ===")
    for r in results:
        print(r)

    print("\n=== stats ===")
    print(stats())
    print("\n=== vector store ===")
    print(vector_store_stats())
    print("search_backend:", get_search_backend())

    sample = run_search("입안예고 기간은 어떻게 되나요?")
    print("\n=== sample Q&A ===")
    print("backend:", sample.get("search_backend"))
    print("citations:", len(sample.get("citations", [])))
    print("summary:", (sample.get("summary") or "")[:300])


if __name__ == "__main__":
    main()
