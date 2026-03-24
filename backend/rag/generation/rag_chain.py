"""
RAG generation using LangChain chain (Prompt → LLM → Parser).
"""
from typing import List

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from clients.gemini import get_llm
from config import settings


logger = structlog.get_logger()

_RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "You are a helpful document assistant. Answer questions based ONLY on the provided context. "
        "If the answer cannot be found in the context, say "
        "\"I cannot answer this based on the provided document.\""
    )),
    ("human", (
        "Context:\n{context}\n\n"
        "Question: {question}\n\n"
        "Answer:"
    )),
])


def _build_context(contexts: List[str], context_metadata: List[dict]) -> str:
    """Build the context string from chunks and metadata."""
    parts = []
    for i, (text, meta) in enumerate(zip(contexts, context_metadata), 1):
        parts.append(
            f"[Context {i} - Page {meta['page_start']}, {meta['section_path']}]\n{text}"
        )
    return "\n\n".join(parts)


async def generate_answer(
    query: str,
    contexts: List[str],
    context_metadata: List[dict],
) -> str:
    """
    Generate answer using LangChain Gemini chain with retrieved context.

    Args:
        query: User question
        contexts: List of relevant chunk texts
        context_metadata: Metadata for each context (page, section)

    Returns:
        Generated answer
    """
    chain = _RAG_PROMPT | get_llm() | StrOutputParser()

    context_str = _build_context(contexts, context_metadata)

    try:
        answer = await chain.ainvoke({
            "context": context_str,
            "question": query,
        })

        answer = answer.strip()
        logger.info("Generated answer", query=query, answer_length=len(answer))
        return answer

    except Exception as e:
        logger.error("Error generating answer", error=str(e))
        return "I encountered an error while generating the answer. Please try again."
