"""data/ 파싱 + OpenAI 임베딩 후 Supabase(pooler) 업로드."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

import psycopg2

REGIONS = [
    "ap-northeast-2",
    "ap-northeast-1",
    "us-east-1",
    "us-west-1",
    "eu-west-1",
    "eu-central-1",
    "ap-southeast-1",
    "ap-south-1",
    "sa-east-1",
]
POOLER_PREFIXES = ("aws-0", "aws-1")
PORTS = (5432, 6543)


def _password_and_project() -> tuple[str, str]:
    raw = os.getenv("DATABASE_URL", "").strip()
    parsed = urlparse(raw)
    if not parsed.password or not parsed.hostname:
        raise RuntimeError("DATABASE_URL이 .env에 없습니다.")
    host = parsed.hostname
    if host.startswith("db.") and host.endswith(".supabase.co"):
        project_ref = host.removeprefix("db.").removesuffix(".supabase.co")
    else:
        user = parsed.username or ""
        project_ref = user.removeprefix("postgres.") if user.startswith("postgres.") else ""
        if not project_ref:
            raise RuntimeError("DATABASE_URL에서 project ref를 찾을 수 없습니다.")
    return parsed.password, project_ref


def find_pooler(project_ref: str, password: str) -> tuple[str, int, str]:
    ssl_verify = os.getenv("DATABASE_SSL_VERIFY", "true").lower() not in (
        "0",
        "false",
        "no",
    )
    base = {"password": password, "dbname": "postgres", "sslmode": "require"}
    if not ssl_verify:
        base["sslrootcert"] = None

    last_errors: list[str] = []
    for prefix in POOLER_PREFIXES:
        for region in REGIONS:
            host = f"{prefix}-{region}.pooler.supabase.com"
            for port in PORTS:
                for user in (f"postgres.{project_ref}", "postgres"):
                    try:
                        conn = psycopg2.connect(host=host, port=port, user=user, **base)
                        conn.autocommit = True
                        with conn.cursor() as cur:
                            cur.execute("SELECT 1")
                        conn.close()
                        return host, port, user
                    except Exception as exc:
                        last_errors.append(str(exc).split("\n")[0][:100])
    raise RuntimeError("pooler 연결 실패. Supabase Dashboard에서 Session pooler URI를 확인하세요.\n" + "\n".join(last_errors[-3:]))


def _write_env_pooler(host: str, port: int, user: str, password: str) -> None:
    env_path = ROOT / ".env"
    db_url = (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/postgres"
        f"?sslmode=require"
    )
    os.environ["DATABASE_URL"] = db_url
    os.environ["SUPABASE_DB_MODE"] = "pooler"
    os.environ["DATABASE_SSL_VERIFY"] = "false"

    lines: list[str] = []
    if env_path.exists():
        for row in env_path.read_text(encoding="utf-8").splitlines():
            if row.startswith("DATABASE_URL="):
                lines.append(f"DATABASE_URL={db_url}")
            elif row.startswith("SUPABASE_DB_MODE="):
                lines.append("SUPABASE_DB_MODE=pooler")
            elif row.startswith("DATABASE_SSL_VERIFY="):
                lines.append("DATABASE_SSL_VERIFY=false")
            else:
                lines.append(row)
    else:
        lines = [f"DATABASE_URL={db_url}", "SUPABASE_DB_MODE=pooler", "DATABASE_SSL_VERIFY=false"]

    if not any(r.startswith("DATABASE_URL=") for r in lines):
        lines.append(f"DATABASE_URL={db_url}")
    if not any(r.startswith("SUPABASE_DB_MODE=") for r in lines):
        lines.append("SUPABASE_DB_MODE=pooler")
    if not any(r.startswith("DATABASE_SSL_VERIFY=") for r in lines):
        lines.append("DATABASE_SSL_VERIFY=false")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    password, project_ref = _password_and_project()
    print("Supabase pooler 탐색 중...")
    host, port, user = find_pooler(project_ref, password)
    print(f"연결 OK: {host}:{port} ({user})")
    _write_env_pooler(host, port, user, password)

    from backend.database import init_db
    from backend.services.regulation_service import ingest_data_folder, stats
    from src.vector_store import vector_store_stats

    init_db()
    print("data/ ingest + embedding 시작 (수 분 소요)...")
    results = ingest_data_folder(fresh=True)
    for row in results:
        print(row)

    s = stats()
    v = vector_store_stats()
    print("\n=== 완료 ===")
    print(f"articles: {s['article_count']}, files: {s['file_count']}, embeddings: {v.get('vector_count', 0)}")
    if s["article_count"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
