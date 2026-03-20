"""kube-news: Kubernetes Ecosystem Knowledge Hub."""

import sys
from pathlib import Path

# Add project root to path so `src.*` imports work on Streamlit Cloud
_project_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _project_root)

# Load .env file for local development
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(_project_root) / ".env")

import streamlit as st  # noqa: E402

_favicon = str(Path(__file__).parent / "static" / "favicon.svg")

st.set_page_config(
    page_title="kube-news",
    page_icon=_favicon,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("\u2638\ufe0f kube-news")
st.markdown(
    "Kubernetes ecosystem knowledge aggregator — "
    "track releases, deprecations, security advisories, and more."
)

st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### \U0001f4ac RAG Chat")
    st.markdown(
        "Ask questions about the Kubernetes ecosystem. "
        "Answers are grounded in real sources with citations."
    )
    st.page_link("pages/01_rag_chat.py", label="Open Chat", icon="\U0001f4ac")

with col2:
    st.markdown("### \u26a0\ufe0f Deprecation Alerts")
    st.markdown(
        "Deprecations, security advisories, and end-of-life notices "
        "across Kubernetes and CNCF projects."
    )
    st.page_link("pages/02_deprecation_alerts.py", label="View Alerts", icon="\u26a0\ufe0f")

with col3:
    st.markdown("### \U0001f4f0 Recent Updates")
    st.markdown(
        "Latest releases, blog posts, and news from across "
        "the Kubernetes ecosystem timeline."
    )
    st.page_link("pages/03_recent_updates.py", label="Browse Updates", icon="\U0001f4f0")

st.sidebar.markdown("---")
st.sidebar.caption(
    "Data sourced from ~25 Kubernetes & CNCF feeds. "
    "Classified with zero-shot BART-MNLI. "
    "Embeddings: all-MiniLM-L6-v2."
)
