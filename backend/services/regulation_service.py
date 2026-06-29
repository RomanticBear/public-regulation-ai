from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import delete, select

from backend.database import ArticleRecord, RegulationFile, get_session
from src.parser import Article, parse_regulation_file
from src.retriever import rebuild_index
from src.vector_store import delete_all_embeddings, delete_embeddings_for_file, vector_store_stats

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"


def article_to_record(article: Article) -> ArticleRecord:
    return ArticleRecord(
        org=article.org,
        regulation=article.regulation,
        source_file=article.source_file,
        article_no=article.article_no,
        title=article.title,
        body=article.body,
    )


def record_to_article(record: ArticleRecord) -> Article:
    return Article(
        org=record.org,
        regulation=record.regulation,
        source_file=record.source_file,
        article_no=record.article_no,
        title=record.title,
        body=record.body,
    )


def load_all_articles() -> list[Article]:
    with get_session() as session:
        rows = session.scalars(
            select(ArticleRecord).order_by(ArticleRecord.id)
        ).all()
        return [record_to_article(row) for row in rows]


def rebuild_search_index(articles: list[Article] | None = None) -> None:
    if articles is None:
        articles = load_all_articles()
    if articles:
        rebuild_index(articles)


def ingest_file(path: Path, *, copy_to_data: bool = True, rebuild: bool = True) -> dict:
    target = path
    if copy_to_data:
        DATA_DIR.mkdir(exist_ok=True)
        target = DATA_DIR / path.name
        if path.resolve() != target.resolve():
            shutil.copy2(path, target)

    articles = parse_regulation_file(target)
    org = articles[0].org if articles else path.stem.split("_")[0]
    regulation = articles[0].regulation if articles else "사규관리규정"

    with get_session() as session:
        session.execute(delete(ArticleRecord).where(ArticleRecord.source_file == target.name))
        session.execute(delete(RegulationFile).where(RegulationFile.filename == target.name))
        session.commit()

    delete_embeddings_for_file(target.name)

    with get_session() as session:
        session.add(
            RegulationFile(org=org, regulation=regulation, filename=target.name)
        )
        session.add_all([article_to_record(a) for a in articles])
        session.commit()

    if rebuild:
        rebuild_search_index(load_all_articles())

    return {
        "filename": target.name,
        "org": org,
        "regulation": regulation,
        "article_count": len(articles),
    }


def clear_all_regulations() -> None:
    with get_session() as session:
        session.execute(delete(ArticleRecord))
        session.execute(delete(RegulationFile))
        session.commit()
    delete_all_embeddings()


def ingest_data_folder(*, fresh: bool = False) -> list[dict]:
    if fresh:
        clear_all_regulations()
    results: list[dict] = []
    for path in sorted(DATA_DIR.glob("*.pdf")) + sorted(DATA_DIR.glob("*.hwp")):
        try:
            results.append(ingest_file(path, copy_to_data=False, rebuild=False))
        except Exception as exc:
            results.append({"filename": path.name, "error": str(exc)})
    rebuild_search_index()
    return results


def _local_data_files() -> set[str]:
    if not DATA_DIR.exists():
        return set()
    return {p.name for p in DATA_DIR.glob("*.pdf")} | {p.name for p in DATA_DIR.glob("*.hwp")}


def sync_data_folder_on_startup() -> None:
    """DB·임베딩이 Supabase에 있으면 skip, 없거나 신규 파일만 처리."""
    local_files = _local_data_files()
    if not local_files:
        return

    current = stats()
    if current["article_count"] == 0:
        ingest_data_folder()
        return

    registered = {row["filename"] for row in list_regulations()}
    new_files = sorted(local_files - registered)
    if new_files:
        for name in new_files:
            ingest_file(DATA_DIR / name, copy_to_data=False, rebuild=False)
        rebuild_search_index()
        return

    vector_count = vector_store_stats().get("vector_count", 0)
    if vector_count == 0 and current["article_count"] > 0:
        rebuild_search_index()


def list_regulations() -> list[dict]:
    with get_session() as session:
        rows = session.scalars(select(RegulationFile).order_by(RegulationFile.org)).all()
        return [
            {
                "id": row.id,
                "org": row.org,
                "regulation": row.regulation,
                "filename": row.filename,
                "uploaded_at": row.uploaded_at.isoformat(),
            }
            for row in rows
        ]


def stats() -> dict:
    with get_session() as session:
        orgs = session.scalars(select(ArticleRecord.org).distinct()).all()
        article_count = len(session.scalars(select(ArticleRecord)).all())
        file_count = len(session.scalars(select(RegulationFile)).all())
    return {
        "org_count": len(orgs),
        "orgs": sorted(orgs),
        "article_count": article_count,
        "file_count": file_count,
    }
