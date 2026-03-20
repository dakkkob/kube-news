"""RAG chat engine: build prompt with retrieved context, call gpt-4o-mini."""

from __future__ import annotations

import logging
from typing import Any

from openai import OpenAI

from src.config import OPENAI_API_KEY
from src.processing.text_cleaner import clean_text
from src.rag.retriever import retrieve

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a Kubernetes ecosystem expert assistant. Answer questions using ONLY \
the provided context from recent Kubernetes-related updates, releases, \
deprecations, security advisories, and blog posts.

Rules:
- Base your answers strictly on the provided context.
- Cite sources using [Source N] notation matching the numbered sources below.
- If the context doesn't contain enough information, say so explicitly.
- Focus on actionable information: what changed, what's deprecated, what to migrate to.
- Be concise but thorough.\
"""

MAX_CONTEXT_CHARS = 6000


def _build_context(results: list[dict[str, Any]]) -> str:
    """Format retrieved results into numbered context blocks."""
    blocks = []
    budget = MAX_CONTEXT_CHARS
    for i, r in enumerate(results, 1):
        body = clean_text(r.get("body", ""), max_length=1500)
        source = r.get("source", "unknown")
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        date = r.get("published_at", "")[:10]

        block = f"[Source {i}] {title}\nFrom: {source} | Date: {date}\nURL: {url}\n{body}"
        if len(block) > budget:
            block = block[:budget]
        blocks.append(block)
        budget -= len(block)
        if budget <= 0:
            break

    return "\n\n---\n\n".join(blocks)


def chat(
    query: str,
    top_k: int = 5,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Run a RAG query: retrieve context, build prompt, call LLM.

    Returns dict with keys: answer, sources (list of {title, url, source, score}).
    """
    results = retrieve(query, top_k=top_k)
    context = _build_context(results)

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if conversation_history:
        messages.extend(conversation_history)

    user_message = f"Context:\n{context}\n\nQuestion: {query}"
    messages.append({"role": "user", "content": user_message})

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.3,
        max_tokens=1024,
    )

    answer = response.choices[0].message.content or ""

    sources = [
        {
            "title": r["title"],
            "url": r["url"],
            "source": r["source"],
            "published_at": r["published_at"],
            "score": round(r["score"], 3),
        }
        for r in results
    ]

    return {"answer": answer, "sources": sources}
