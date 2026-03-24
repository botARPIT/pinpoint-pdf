"""
Section-aware hybrid chunking with tiktoken and sliding-window overlap.

Strategy:
  1. Flatten ALL text blocks into one ordered stream with metadata tags.
  2. Use a sliding window (target ~250-400 tokens, overlap ~15-25%)
     across the full document text.
  3. Each chunk inherits section_path / page from the text blocks it
     overlaps with.
  4. Tables and figures become atomic chunks.
"""
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional

import tiktoken

from config import settings


# ── tiktoken encoder (loaded once, thread-safe) ──────────────────────
_ENC = tiktoken.encoding_for_model("gpt-4o")


def count_tokens(text: str) -> int:
    """Exact BPE token count via tiktoken."""
    return len(_ENC.encode(text))


def encode_tokens(text: str) -> list[int]:
    """Encode text to token IDs."""
    return _ENC.encode(text)


def decode_tokens(token_ids: list[int]) -> str:
    """Decode token IDs back to text."""
    return _ENC.decode(token_ids)


# ── Config ────────────────────────────────────────────────────────────
TARGET_CHUNK_TOKENS = settings.TARGET_CHUNK_TOKENS
MAX_CHUNK_TOKENS = settings.MAX_CHUNK_TOKENS
MIN_CHUNK_TOKENS = settings.MIN_CHUNK_TOKENS
CHUNK_OVERLAP = settings.CHUNK_OVERLAP


@dataclass
class Chunk:
    """Enhanced chunk representation with detailed metadata."""
    chunk_id: str
    doc_id: str
    section_path: str
    section_level: int
    page_start: int
    page_end: int
    chunk_type: str  # 'paragraph' | 'table' | 'figure'
    token_count: int
    text: str
    table_id: Optional[str] = None
    figure_id: Optional[str] = None


def get_section_level(section_path: str) -> int:
    """Extract section level from path like 'Chapter 2 > 2.2 Method'."""
    return len(section_path.split(">"))


# ── Sliding-window splitter  ─────────────────────────────────────────

# Sentence-ending characters for boundary snapping
_BOUNDARY_CHARS = frozenset(".?!\n")


@lru_cache(maxsize=8192)
def _is_boundary_token(token_id: int) -> bool:
    """Cached token-level boundary check to avoid repeated decode() calls."""
    char = decode_tokens([token_id]).lstrip()
    return bool(char) and char[0] in _BOUNDARY_CHARS


def _snap_to_sentence(
    tokens: list[int],
    base_end: int,
    total: int,
    max_scan: int = 40,
    maximum: int = MAX_CHUNK_TOKENS,
    pos: int = 0,
) -> int:
    """
    Starting from *base_end*, scan forward up to *max_scan* tokens
    looking for a sentence-ending token.  Return the adjusted end index
    (inclusive of the boundary token).  If no boundary is found, return
    *base_end* unchanged.
    """
    scan_limit = min(base_end + max_scan, total, pos + maximum)
    for i in range(base_end, scan_limit):
        if _is_boundary_token(tokens[i]):
            return i + 1
    return base_end


def sliding_window_split(
    text: str,
    target: int = TARGET_CHUNK_TOKENS,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """
    Split *text* into overlapping chunks using a token-level sliding window.

    Returns a list of chunk strings.
    """
    tokens = encode_tokens(text)
    total = len(tokens)

    if total <= target:
        return [text] if total >= MIN_CHUNK_TOKENS else []

    chunks: list[str] = []
    pos = 0

    while pos < total:
        # Determine window end
        base_end = min(pos + target, total)

        if base_end < total:
            end = _snap_to_sentence(tokens, base_end, total, pos=pos)
        else:
            end = base_end

        chunk_text = decode_tokens(tokens[pos:end]).strip()
        chunk_tok = end - pos

        if chunk_text and chunk_tok >= MIN_CHUNK_TOKENS:
            chunks.append(chunk_text)

        # Advance: consumed minus overlap
        advance = max(chunk_tok - overlap, 1)
        new_pos = pos + advance

        # Safety: guarantee forward progress
        if new_pos <= pos:
            new_pos = pos + 1
        pos = new_pos

    return chunks


# ── Metadata tagging helpers ─────────────────────────────────────────

@dataclass
class _TextSpan:
    """A block of text with its character offset range and metadata."""
    char_start: int
    char_end: int
    section_path: str
    page: int
    is_heading: bool


def _build_text_stream(text_blocks: list[dict]) -> tuple[str, list[_TextSpan]]:
    """
    Concatenate all text blocks into one string, tracking character offsets
    so we can map each chunk back to its source section/page.
    """
    parts: list[str] = []
    spans: list[_TextSpan] = []
    offset = 0

    for block in text_blocks:
        if block.get("is_heading"):
            continue

        text = block["text"]
        sep = " " if offset > 0 else ""
        start = offset + len(sep)
        end = start + len(text)

        parts.append(sep + text)
        spans.append(_TextSpan(
            char_start=start,
            char_end=end,
            section_path=block["section_path"],
            page=block["page"],
            is_heading=False,
        ))
        offset = end

    return "".join(parts), spans


def _find_metadata_for_range(
    chunk_text: str,
    full_text: str,
    search_start: int,
    spans: list[_TextSpan],
) -> tuple[str, int, int, int]:
    """
    Given a chunk's text, find it in the full_text starting from search_start,
    then determine which spans it overlaps with.
    Returns (section_path, section_level, page_start, page_end).
    """
    idx = full_text.find(chunk_text, search_start)
    if idx == -1:
        # Fallback: try from beginning
        idx = full_text.find(chunk_text[:50])
        if idx == -1:
            idx = search_start

    chunk_start = idx
    chunk_end = idx + len(chunk_text)

    # Find all spans that overlap with this chunk
    overlapping = [
        s for s in spans
        if s.char_end > chunk_start and s.char_start < chunk_end
    ]

    if overlapping:
        # Use the section that covers the majority of the chunk
        section_path = overlapping[0].section_path
        pages = {s.page for s in overlapping}
        page_start = min(pages)
        page_end = max(pages)
    else:
        section_path = "Unknown"
        page_start = 0
        page_end = 0

    section_level = get_section_level(section_path)
    return section_path, section_level, page_start, page_end


# ── Main entry point ─────────────────────────────────────────────────

def chunk_document(structured_doc: dict, doc_id: str) -> List[Chunk]:
    """
    Chunk document using a document-level sliding window with tiktoken.

    1. Flatten all text blocks into one string with metadata tracking.
    2. Apply sliding_window_split() across the entire document.
    3. Map each chunk back to its source section/page.
    4. Tables → atomic chunks.
    5. Figures → atomic chunks.
    """
    chunks: list[Chunk] = []
    text_blocks = structured_doc.get("structured_text", [])

    if not text_blocks:
        return chunks

    # ── Build full document text with metadata spans ──────────────
    full_text, spans = _build_text_stream(text_blocks)

    if not full_text.strip():
        return chunks

    # ── Sliding-window split across the entire document ───────────
    chunk_texts = sliding_window_split(full_text)

    search_pos = 0
    for chunk_text in chunk_texts:
        section_path, section_level, page_start, page_end = \
            _find_metadata_for_range(chunk_text, full_text, search_pos, spans)

        # Advance search_pos for next chunk (with overlap, chunks overlap)
        idx = full_text.find(chunk_text, search_pos)
        if idx >= 0:
            search_pos = idx  # don't advance past, overlap means next chunk starts nearby

        chunks.append(Chunk(
            chunk_id=str(uuid.uuid4()),
            doc_id=doc_id,
            section_path=section_path,
            section_level=section_level,
            page_start=page_start,
            page_end=page_end,
            chunk_type="paragraph",
            token_count=count_tokens(chunk_text),
            text=chunk_text,
        ))

    # ── Tables (atomic) ───────────────────────────────────────────
    table_counter = 0
    for table in structured_doc.get("tables", []):
        table_counter += 1
        table_id = f"table_{table['page']}_{table_counter}"

        table_text = f"Table {table_id} (Page {table['page']}):\n"
        if table.get("headers"):
            table_text += " | ".join(str(h) for h in table["headers"]) + "\n"
        for row in table.get("rows", []):
            table_text += " | ".join(str(cell) for cell in row) + "\n"

        chunks.append(Chunk(
            chunk_id=str(uuid.uuid4()),
            doc_id=doc_id,
            section_path="Tables",
            section_level=0,
            page_start=table["page"],
            page_end=table["page"],
            chunk_type="table",
            token_count=count_tokens(table_text),
            text=table_text,
            table_id=table_id,
        ))

    # ── Figures (atomic) ──────────────────────────────────────────
    for fig in structured_doc.get("figures", []):
        figure_id = fig.get("figure_id", f"fig_{fig['page']}")
        fig_text = (
            f"[Figure {figure_id}] "
            f"(Page {fig['page']}, "
            f"size: {fig.get('width', 0)}x{fig.get('height', 0)})"
        )
        if fig.get("caption"):
            fig_text += f"\nCaption: {fig['caption']}"

        chunks.append(Chunk(
            chunk_id=str(uuid.uuid4()),
            doc_id=doc_id,
            section_path="Figures",
            section_level=0,
            page_start=fig["page"],
            page_end=fig["page"],
            chunk_type="figure",
            token_count=count_tokens(fig_text),
            text=fig_text,
            figure_id=figure_id,
        ))

    return chunks
