from __future__ import annotations

import os
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from sqlalchemy import DateTime, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "processed" / "regulation.db"
EMBEDDING_DIM = 1536


def _ssl_verify_enabled() -> bool:
    return os.getenv("DATABASE_SSL_VERIFY", "true").lower() not in ("0", "false", "no")


def _resolve_ipv6_host(hostname: str) -> str | None:
    override = os.getenv("SUPABASE_DB_IPV6", "").strip()
    if override:
        return override
    try:
        import httpx

        r = httpx.get(
            "https://dns.google/resolve",
            params={"name": hostname, "type": "AAAA"},
            verify=_ssl_verify_enabled(),
            timeout=8,
        )
        for item in r.json().get("Answer") or []:
            if item.get("type") == 28:
                return item["data"]
    except Exception:
        pass
    return None


def _normalize_database_url(raw: str) -> str:
    """회사망 DNS: db.* 호스트(IPv6-only) → DoH로 AAAA 조회 후 직접 연결."""
    url = raw.strip()
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host.startswith("db.") and host.endswith(".supabase.co"):
        mode = os.getenv("SUPABASE_DB_MODE", "direct").lower()
        if mode == "pooler":
            project_ref = host.removeprefix("db.").removesuffix(".supabase.co")
            region = os.getenv("SUPABASE_REGION", "ap-northeast-2")
            pooler_host = f"aws-0-{region}.pooler.supabase.com"
            user = parsed.username or "postgres"
            if not user.startswith("postgres."):
                user = f"postgres.{project_ref}"
            host = pooler_host
        else:
            ipv6 = _resolve_ipv6_host(host)
            if ipv6:
                host = f"[{ipv6}]"
            user = parsed.username or "postgres"
        port = parsed.port or 5432
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault("sslmode", "require")
        return urlunparse(
            parsed._replace(
                netloc=f"{user}:{parsed.password}@{host}:{port}",
                query=urlencode(query),
            )
        )
    return url


DATABASE_URL = _normalize_database_url(os.getenv("DATABASE_URL", ""))


class Base(DeclarativeBase):
    pass


class RegulationFile(Base):
    __tablename__ = "regulation_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org: Mapped[str] = mapped_column(String(100), index=True)
    regulation: Mapped[str] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(255))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ArticleRecord(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org: Mapped[str] = mapped_column(String(100), index=True)
    regulation: Mapped[str] = mapped_column(String(100))
    source_file: Mapped[str] = mapped_column(String(255))
    article_no: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text)


if DATABASE_URL:
    from pgvector.sqlalchemy import Vector

    class ArticleEmbedding(Base):
        __tablename__ = "article_embeddings"

        id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
        article_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
        org: Mapped[str] = mapped_column(String(100), index=True)
        source_file: Mapped[str] = mapped_column(String(255), index=True)
        article_no: Mapped[str] = mapped_column(String(50))
        model: Mapped[str] = mapped_column(String(100))
        embedding = mapped_column(Vector(EMBEDDING_DIM))
else:
    ArticleEmbedding = None  # type: ignore[misc, assignment]


def get_database_url() -> str | None:
    return DATABASE_URL or None


def is_postgres() -> bool:
    return bool(DATABASE_URL)


def _postgres_connect_args() -> dict:
    if _ssl_verify_enabled():
        return {}
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return {"sslmode": "require", "sslrootcert": None}


def _create_engine():
    if DATABASE_URL:
        return create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            connect_args=_postgres_connect_args(),
        )
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    if DATABASE_URL:
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
        except Exception:
            pass  # Supabase 대시보드에서 이미 활성화된 경우
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()
