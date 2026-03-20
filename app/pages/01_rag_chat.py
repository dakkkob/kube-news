"""RAG Chat — Ask questions about the Kubernetes ecosystem."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

from src.rag.chat_engine import chat  # noqa: E402

st.set_page_config(page_title="RAG Chat | kube-news", page_icon="\U0001f4ac", layout="wide")

st.title("\U0001f4ac Kubernetes Knowledge Chat")
st.caption("Ask anything about Kubernetes releases, deprecations, security, and CNCF projects.")

# Session state for conversation
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar controls
with st.sidebar:
    st.markdown("### Settings")
    top_k = st.slider("Number of sources to retrieve", min_value=1, max_value=10, value=5)
    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.markdown("### Example questions")
    examples = [
        "What's deprecated in Kubernetes 1.31?",
        "Is Kyverno dropping non-CEL policies?",
        "Latest security CVEs in Kubernetes",
        "What's new in Istio?",
        "Gateway API vs Ingress — what should I use?",
    ]
    for example in examples:
        if st.button(example, key=f"ex_{example}"):
            st.session_state.pending_query = example
            st.rerun()

# Display conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander(f"Sources ({len(msg['sources'])})"):
                for i, src in enumerate(msg["sources"], 1):
                    score = src.get("score", 0)
                    date = src.get("published_at", "")[:10]
                    st.markdown(
                        f"**[Source {i}]** [{src['title']}]({src['url']})  \n"
                        f"`{src['source']}` | {date} | relevance: {score}"
                    )

# Handle input — either from text input or example button
query = st.chat_input("Ask about Kubernetes...")
if "pending_query" in st.session_state:
    query = st.session_state.pop("pending_query")

if query:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    # Build conversation history for context (last 4 exchanges max)
    history = []
    for msg in st.session_state.messages[-8:]:
        if msg["role"] in ("user", "assistant"):
            history.append({"role": msg["role"], "content": msg["content"]})

    # Get RAG response
    with st.chat_message("assistant"), st.spinner("Searching knowledge base..."):
        try:
            result = chat(query, top_k=top_k, conversation_history=history[:-1])
            answer = result["answer"]
            sources = result["sources"]

            st.markdown(answer)

            if sources:
                with st.expander(f"Sources ({len(sources)})"):
                    for i, src in enumerate(sources, 1):
                        score = src.get("score", 0)
                        date = src.get("published_at", "")[:10]
                        st.markdown(
                            f"**[Source {i}]** [{src['title']}]({src['url']})  \n"
                            f"`{src['source']}` | {date} | relevance: {score}"
                        )

            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "sources": sources,
            })

        except Exception as e:
            st.error(f"Error: {e}")
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"Error: {e}",
            })
