"""RAG chat engine: build prompt with retrieved context, call gpt-4o-mini."""

from __future__ import annotations

import logging
from typing import Any

from openai import OpenAI

from src.config import OPENAI_API_KEY
from src.processing.text_cleaner import extract_relevant_snippet
from src.rag.retriever import retrieve

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a Kubernetes ecosystem expert assistant. Answer questions using ONLY \
the provided context from Kubernetes-related updates, releases, \
deprecations, security advisories, and blog posts.

Rules:
- Base your answers strictly on the provided context.
- Cite sources using [Source N] notation matching the numbered sources below.
- If the context doesn't contain enough information, say so explicitly.
- Always present relevant information from the context, even if the sources are older. \
When the user asks for "latest" or "recent" items, include a note about the actual \
dates (e.g., "Note: the most recent CVEs in our knowledge base are from 2023").
- Focus on actionable information: what changed, what's deprecated, what to migrate to.
- Be concise but thorough.\
"""

MAX_CONTEXT_CHARS = 12000


def _format_metadata(result: dict[str, Any]) -> str:
    """Build a metadata line from structured fields (for thin-body items)."""
    parts = []
    if result.get("label"):
        parts.append(f"Category: {result['label']}")
    if result.get("cve_id"):
        parts.append(f"CVE: {result['cve_id']}")
    if result.get("tag"):
        parts.append(f"Version: {result['tag']}")
    if result.get("cycle"):
        parts.append(f"Cycle: {result['cycle']}")
    if result.get("latest_version"):
        parts.append(f"Latest: {result['latest_version']}")
    if result.get("eol_date"):
        parts.append(f"EOL: {result['eol_date']}")
    if result.get("is_eol") is True:
        parts.append("Status: End of Life")
    if result.get("lts") is True:
        parts.append("LTS: Yes")
    return " | ".join(parts)


def _build_context(results: list[dict[str, Any]], query: str) -> str:
    """Format retrieved results into numbered context blocks."""
    blocks = []
    budget = MAX_CONTEXT_CHARS
    for i, r in enumerate(results, 1):
        body = extract_relevant_snippet(r.get("body", ""), query, max_length=3000)
        source = r.get("source", "unknown")
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        date = r.get("published_at", "")[:10]

        header = f"[Source {i}] {title}\nFrom: {source} | Date: {date}\nURL: {url}"

        # Add structured metadata — especially useful when body is thin
        meta = _format_metadata(r)
        if meta:
            header += f"\n{meta}"

        block = f"{header}\n{body}" if body else header
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
    context = _build_context(results, query)

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if conversation_history:
        messages.extend(conversation_history)

    user_message = f"Context:\n{context}\n\nQuestion: {query}"
    messages.append({"role": "user", "content": user_message})

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,  # type: ignore[arg-type]
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
