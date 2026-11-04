"""Đọc PDF/MD/TXT thành các "segment" (văn bản + metadata nguồn)."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Segment:
    text: str
    metadata: dict = field(default_factory=dict)
    markdown: bool = False


def parse(path: str | Path) -> list[Segment]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        return [
            Segment(page.extract_text() or "", {"page": i + 1})
            for i, page in enumerate(PdfReader(str(path)).pages)
        ]
    if ext in (".md", ".markdown", ".txt"):
        return [Segment(path.read_text(encoding="utf-8", errors="replace"), {}, ext != ".txt")]
    raise ValueError(f"Định dạng không hỗ trợ: {ext}")
