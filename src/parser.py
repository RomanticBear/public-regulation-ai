"""규정 파일(PDF/HWP)에서 텍스트·조문 추출."""

from __future__ import annotations

import re
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
    r"제(\d+)조(?:의(\d+))?(?:\(([^)]+)\))?",
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


def extract_hwp_text(path: Path) -> str:
    """HWP 5.0 OLE 파일에서 텍스트 추출 (PrvText + BodyText)."""
    if not olefile.isOleFile(path):
        raise ValueError(f"OLE 형식이 아닌 HWP 파일: {path.name}")

    ole = olefile.OleFileIO(str(path))
    chunks: list[str] = []

    if ole.exists("PrvText"):
        raw = ole.openstream("PrvText").read()
        chunks.append(raw.decode("utf-16le", errors="ignore"))

    for entry in ole.listdir():
        if entry[0] != "BodyText":
            continue
        try:
            import zlib

            data = ole.openstream(entry).read()
            header_size = 4 if data[:2] == b"\x78\x9c" else 256
            payload = data[header_size:]
            for wbits in (-15, 15):
                try:
                    decompressed = zlib.decompress(payload, wbits)
                    chunks.append(decompressed.decode("utf-16le", errors="ignore"))
                    break
                except zlib.error:
                    continue
        except Exception:
            continue

    ole.close()
    text = normalize_text("\n".join(chunks))
    if len(text) < 100:
        raise ValueError(
            f"HWP 텍스트 추출 실패: {path.name}. "
            "한글에서 PDF로 저장 후 data 폴더에 넣어 주세요."
        )
    return text


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
