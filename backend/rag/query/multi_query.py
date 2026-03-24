"""
Multi-query expansion using LangChain + Gemini.
Generates query variations for better retrieval coverage.
"""
import re
from collections import OrderedDict
from typing import List

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from clients.gemini import get_llm
from config import settings


logger = structlog.get_logger()
_EXPANSION_CACHE_MAX = 256
_expansion_cache: OrderedDict[str, List[str]] = OrderedDict()
_REFERENCE_QUERY_PATTERN = re.compile(
    r"\b(chapter|section|figure|fig\.?|table|appendix)\s+[a-z0-9][a-z0-9.\-]*\b",
    re.IGNORECASE,
)

_EXPAND_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant that generates alternative phrasings of questions."),
    ("human", (
        "Generate 2 alternative phrasings of the following question. "
        "Keep the same meaning but use different words and sentence structures.\n"
        "Return ONLY the 2 alternative questions, one per line. No numbering.\n\n"
        "Original question: {question}"
    )),
])


async def expand_query(query: str) -> List[str]:
    """
    Generate 3 query variations (original + 2 alternatives) for better retrieval.

    Args:
        query: Original user query

    Returns:
        List of query variations (including original)
    """
    query = query.strip()
    if not query:
        return []

    word_count = len(query.split())
    should_expand = settings.QUERY_EXPANSION_ENABLED
    if should_expand and word_count < settings.QUERY_EXPANSION_MIN_WORDS:
        should_expand = False
    if should_expand and _REFERENCE_QUERY_PATTERN.search(query):
        should_expand = False

    if not should_expand:
        logger.info("Query expansion skipped", word_count=word_count)
        return [query]

    cached = _expansion_cache.get(query)
    if cached is not None:
        _expansion_cache.move_to_end(query)
        logger.info("Query expansion cache hit", word_count=word_count, num_variations=len(cached))
        return cached

    chain = _EXPAND_PROMPT | get_llm() | StrOutputParser()

    try:
        result = await chain.ainvoke({"question": query})

        alternatives = [
            line.strip()
            for line in result.strip().split("\n")
            if line.strip()
        ]

        # Return original + alternatives (max 3 total)
        queries = [query] + alternatives[:2]
        _expansion_cache[query] = queries
        _expansion_cache.move_to_end(query)
        while len(_expansion_cache) > _EXPANSION_CACHE_MAX:
            _expansion_cache.popitem(last=False)

        logger.info("Query expanded", original=query, num_variations=len(queries))
        return queries

    except Exception as e:
        logger.error("Error expanding query", error=str(e))
        return [query]
