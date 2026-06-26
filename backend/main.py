from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.database import init_db
from backend.services.ai_service import (
    run_benchmark_report,
    run_compare,
    run_gap_detection,
    run_gap_scan,
    run_search,
    run_similar_search,
)
from backend.services.regulation_service import (
    ingest_data_folder,
    ingest_file,
    list_regulations,
    rebuild_search_index,
    stats,
)
from src.retriever import get_search_backend
from src.vector_store import vector_store_stats

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "frontend" / "static"

app = FastAPI(
    title="Public Regulation AI",
    description="공공기관 사규관리규정 벤치마킹 플랫폼",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, examples=["입안예고 기간은?"])


class CompareRequest(BaseModel):
    org_a: str
    org_b: str
    topic: str = Field(min_length=1, examples=["입안예고"])


class GapRequest(BaseModel):
    target_org: str
    topic: str = Field(min_length=1, examples=["사후평가"])


class TargetOrgRequest(BaseModel):
    target_org: str


def _ensure_data() -> None:
    if stats()["article_count"] == 0:
        raise HTTPException(status_code=400, detail="조문 데이터가 없습니다. 규정 파일을 업로드하세요.")


def _ensure_embedding() -> None:
    from src.vector_store import is_embedding_available

    if not is_embedding_available():
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY가 .env에 설정되어 있지 않습니다.",
        )


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    data_dir = ROOT / "data"
    if data_dir.exists() and any(data_dir.iterdir()):
        ingest_data_folder()
    else:
        rebuild_search_index()


@app.get("/api/health")
def health() -> dict:
    from src.vector_store import is_embedding_available

    return {
        "status": "ok",
        "version": "0.3.0",
        "embedding_enabled": is_embedding_available(),
    }


@app.get("/api/stats")
def api_stats() -> dict:
    s = stats()
    s["search_backend"] = get_search_backend()
    s.update(vector_store_stats())
    return s


@app.get("/api/regulations")
def api_regulations() -> list[dict]:
    return list_regulations()


@app.post("/api/regulations/upload")
async def upload_regulation(file: UploadFile = File(...)) -> dict:
    _ensure_embedding()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".hwp"}:
        raise HTTPException(status_code=400, detail="PDF 또는 HWP 파일만 업로드 가능합니다.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = ingest_file(tmp_path, copy_to_data=True)
        return {"ok": True, **result}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/api/regulations/reindex")
def reindex() -> dict:
    _ensure_embedding()
    results = ingest_data_folder(fresh=True)
    return {"ok": True, "results": results}


@app.post("/api/search")
def api_search(body: SearchRequest) -> dict:
    _ensure_data()
    _ensure_embedding()
    return run_search(body.query)


@app.post("/api/similar")
def api_similar(body: SearchRequest) -> dict:
    _ensure_data()
    _ensure_embedding()
    return run_similar_search(body.query)


@app.post("/api/compare")
def api_compare(body: CompareRequest) -> dict:
    _ensure_data()
    _ensure_embedding()
    return run_compare(body.org_a, body.org_b, body.topic)


@app.post("/api/gap")
def api_gap(body: GapRequest) -> dict:
    _ensure_data()
    _ensure_embedding()
    return run_gap_detection(body.target_org, body.topic)


@app.post("/api/gap/scan")
def api_gap_scan(body: TargetOrgRequest) -> dict:
    _ensure_data()
    _ensure_embedding()
    return run_gap_scan(body.target_org)


@app.post("/api/report")
def api_report(body: TargetOrgRequest) -> dict:
    _ensure_data()
    _ensure_embedding()
    return run_benchmark_report(body.target_org)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
