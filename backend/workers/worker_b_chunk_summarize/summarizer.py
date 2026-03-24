"""
Extractive chunk summarization — no LLM calls.

Uses a lead-sentence heuristic: the first 2 sentences of each chunk
serve as the summary.  This is instant and deterministic, eliminating
the Gemini API bottleneck entirely.
"""
import re
from typing import List
from dataclasses import dataclass

import structlog

from chunking.section_chunker import Chunk


logger = structlog.get_logger()

# Regex to split on sentence boundaries (. ! ? followed by space or end)
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')


@dataclass
class Summary:
    """Chunk summary."""
    chunk_id: str
    summary_text: str


def _extract_lead_sentences(text: str, n: int = 2) -> str:
    """
    Extract the first *n* sentences from text.
    Falls back to the first 150 characters if no sentence boundaries found.
    """
    text = text.strip()
    if not text:
        return ""

    sentences = _SENTENCE_RE.split(text)
    if len(sentences) >= n:
        return " ".join(sentences[:n]).strip()
    
    # Not enough sentence boundaries → use what we have
    return text[:200].strip()


def summarize_chunk(chunk: Chunk) -> Summary:
    """
    Extractive summary: first 2 sentences of the chunk text.
    For table/figure chunks the full text is already short, so use it as-is.
    """
    if chunk.chunk_type in ("table", "figure"):
        return Summary(chunk_id=chunk.chunk_id, summary_text=chunk.text)

    summary_text = _extract_lead_sentences(chunk.text, n=2)
    return Summary(chunk_id=chunk.chunk_id, summary_text=summary_text)


def summarize_chunks(chunks: List[Chunk]) -> List[Summary]:
    """
    Summarize all chunks using extractive lead-sentence heuristic.
    No async, no API calls — runs in <1 second.
    """
    summaries = [summarize_chunk(c) for c in chunks]
    logger.info(
        "Extractive summarization complete",
        total_chunks=len(chunks),
        summaries=len(summaries),
    )
    return summaries
