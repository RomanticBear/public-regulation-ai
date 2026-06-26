from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "processed" / "regulation.db"


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


engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()
