from apps.documents.services.chunking import chunk_segments
from apps.documents.services.parsing import Segment


def test_heading_metadata_and_breadcrumb():
    md = "# A\nintro\n## B\nbody of b\n# C\nbody c"
    chunks = chunk_segments([Segment(md, {}, markdown=True)])
    assert [c.metadata.get("heading") for c in chunks] == ["A", "A > B", "C"]


def test_long_section_split_with_overlap():
    text = ". ".join(f"sentence number {i}" for i in range(400))
    chunks = chunk_segments([Segment(text)], chunk_tokens=50, overlap_tokens=10)
    assert len(chunks) > 3
    assert all(c.token_count <= 60 for c in chunks)
    assert chunks[0].text[-20:] in chunks[1].text  # overlap


def test_page_metadata_kept():
    chunks = chunk_segments([Segment("hello", {"page": 3})])
    assert chunks[0].metadata == {"page": 3}
