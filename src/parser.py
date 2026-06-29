"""규정 파일(PDF/HWP)에서 텍스트·조문 추출."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import fitz
import olefile


@dataclass
class Article:
    org: str
    regulation: str
    source_file: str
    article_no: str
    title: str
    body: str

    @property
    def label(self) -> str:
        if self.title:
            return f"{self.article_no}({self.title})"
        return self.article_no

    def to_dict(self) -> dict:
        return asdict(self)


ARTICLE_PATTERN = re.compile(
    r"제\s*(\d+)\s*조(?:의(\d+))?\s*(?:\(([^)]+)\))?(?!\s*의)",
    re.MULTILINE,
)
NOISE_PATTERN = re.compile(
    r"(law\.kwater\.or\.kr|-- \d+ of \d+ --|\[\d+/\d+\]|^\d+$)",
    re.MULTILINE,
)


def normalize_text(text: str) -> str:
    """PDF/HWP 추출 텍스트 정리."""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_org_name(filename: str) -> str:
    """파일명에서 기관명 추출. 예: 한국수자원공사_사규관리규정.pdf"""
    stem = Path(filename).stem
    if "_" in stem:
        return stem.split("_", 1)[0]
    return stem


def parse_regulation_name(filename: str) -> str:
    stem = Path(filename).stem
    if "_" in stem:
        return stem.split("_", 1)[1]
    return "사규관리규정"


def extract_pdf_text(path: Path) -> str:
    doc = fitz.open(path)
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text())
    doc.close()
    return normalize_text("\n".join(parts))


def _hwp5txt_binary() -> Path | None:
    venv_bin = Path(sys.executable).resolve().parent / "hwp5txt.exe"
    if venv_bin.exists():
        return venv_bin
    found = shutil.which("hwp5txt")
    return Path(found) if found else None


def _extract_hwp_text_legacy(path: Path) -> str:
    """PrvText 미리보기 fallback (본문 일부만 추출될 수 있음)."""
    ole = olefile.OleFileIO(str(path))
    chunks: list[str] = []
    try:
        if ole.exists("PrvText"):
            raw = ole.openstream("PrvText").read()
            chunks.append(raw.decode("utf-16le", errors="ignore"))
    finally:
        ole.close()
    return normalize_text("\n".join(chunks))


def extract_hwp_text(path: Path) -> str:
    """HWP 5.0 텍스트 추출 (pyhwp hwp5txt 우선)."""
    if not olefile.isOleFile(path):
        raise ValueError(f"OLE 형식이 아닌 HWP 파일: {path.name}")

    binary = _hwp5txt_binary()
    if binary is not None:
        result = subprocess.run(
            [str(binary), str(path.resolve())],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            text = normalize_text(result.stdout.decode("utf-8", errors="replace"))
            if len(text) >= 100:
                return text

    legacy = _extract_hwp_text_legacy(path)
    if len(legacy) >= 100:
        return legacy

    raise ValueError(
        f"HWP 텍스트 추출 실패: {path.name}. "
        "pip install pyhwp 후 재시도하거나, 한글에서 PDF로 저장해 주세요."
    )


def extract_file_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix == ".hwp":
        return extract_hwp_text(path)
    raise ValueError(f"지원하지 않는 형식: {path.suffix}")


def split_articles(text: str, org: str, regulation: str, source_file: str) -> list[Article]:
    """조문 단위 분리."""
    text = NOISE_PATTERN.sub("", text)
    matches = list(ARTICLE_PATTERN.finditer(text))
    if not matches:
        return [
            Article(
                org=org,
                regulation=regulation,
                source_file=source_file,
                article_no="전체",
                title="",
                body=text[:8000],
            )
        ]

    articles: list[Article] = []
    for idx, match in enumerate(matches):
        main_no = match.group(1)
        sub_no = match.group(2)
        title = (match.group(3) or "").strip()
        article_no = f"제{main_no}조"
        if sub_no:
            article_no = f"제{main_no}조의{sub_no}"

        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = normalize_text(text[start:end])
        if len(body) < 5:
            continue

        articles.append(
            Article(
                org=org,
                regulation=regulation,
                source_file=source_file,
                article_no=article_no,
                title=title,
                body=body,
            )
        )
    return articles


def parse_regulation_file(path: Path) -> list[Article]:
    org = parse_org_name(path.name)
    regulation = parse_regulation_name(path.name)
    text = extract_file_text(path)
    return split_articles(text, org, regulation, path.name)
