"""Chia chunk: theo cấu trúc trước (heading), rồi theo kích thước (có overlap).

TẠI SAO không cắt cứng theo N ký tự?
  - Cắt giữa câu/giữa mục làm embedding "lẫn" hai ý, truy xuất kém và trích dẫn khó đọc.
  - Cắt theo heading giữ nguyên một ý trọn vẹn và cho ta metadata `heading` để trích dẫn.
TẠI SAO vẫn cần giới hạn kích thước? Mục dài > ngữ cảnh embedding/LLM hữu ích, nên chia tiếp.
TẠI SAO overlap (~12%)? Câu nằm sát ranh giới vẫn xuất hiện trọn vẹn ở ít nhất một chunk.
"""

import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .parsing import Segment

CHARS_PER_TOKEN = 4  # xấp xỉ; đủ để cắt, không cần tokenizer thật
CHUNK_TOKENS = 600  # trong khoảng 500–800 theo spec
OVERLAP_TOKENS = 72  # ~12%

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


@dataclass
class ChunkData:
    text: str
    metadata: dict
    token_count: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _sections(text: str) -> list[tuple[str, str]]:
    """[(heading_breadcrumb, body)] — heading dạng 'A > B' theo cấp."""
    matches = list(_HEADING.finditer(text))
    if not matches:
        return [("", text)]
    out: list[tuple[str, str]] = []
    if text[: matches[0].start()].strip():
        out.append(("", text[: matches[0].start()]))
    stack: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        level, title = len(m.group(1)), m.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((" > ".join(t for _, t in stack), text[m.end() : end]))
    return out


def chunk_segments(
    segments: list[Segment],
    chunk_tokens: int = CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[ChunkData]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_tokens * CHARS_PER_TOKEN,
        chunk_overlap=overlap_tokens * CHARS_PER_TOKEN,
        separators=["\n\n", "\n", ". ", " ", ""],  # ưu tiên đoạn > dòng > câu > từ
    )
    chunks: list[ChunkData] = []
    for seg in segments:
        sections = _sections(seg.text) if seg.markdown else [("", seg.text)]
        for heading, body in sections:
            if not body.strip():
                continue
            for piece in splitter.split_text(body.strip()):
                meta = dict(seg.metadata)
                if heading:
                    meta["heading"] = heading
                chunks.append(ChunkData(piece, meta, estimate_tokens(piece)))
    return chunks
