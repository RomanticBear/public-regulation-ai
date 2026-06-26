"""data/ 폴더 규정 파일 → processed/articles.json 생성."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.parser import parse_regulation_file


def main() -> None:
    data_dir = ROOT / "data"
    out_dir = ROOT / "processed"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "articles.json"

    files = sorted(data_dir.glob("*.pdf")) + sorted(data_dir.glob("*.hwp"))
    if not files:
        print(f"[오류] {data_dir} 에 PDF/HWP 파일이 없습니다.")
        sys.exit(1)

    all_articles = []
    report: list[str] = []

    for path in files:
        try:
            articles = parse_regulation_file(path)
            all_articles.extend(articles)
            report.append(f"  ✓ {path.name}: 조문 {len(articles)}개")
        except Exception as exc:
            report.append(f"  ✗ {path.name}: {exc}")

    payload = {
        "article_count": len(all_articles),
        "org_count": len({a["org"] for a in [x.to_dict() for x in all_articles]}),
        "articles": [a.to_dict() for a in all_articles],
    }
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 규정 인덱스 빌드 결과 ===")
    print("\n".join(report))
    print(f"\n총 {payload['article_count']}개 조문, {payload['org_count']}개 기관")
    print(f"저장: {out_file}")


if __name__ == "__main__":
    main()
