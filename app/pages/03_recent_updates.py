"""Recent Updates — Timeline of Kubernetes ecosystem news."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

from src.storage.dynamodb_client import query_by_source, query_recent  # noqa: E402

st.set_page_config(
    page_title="Recent Updates | kube-news", page_icon="\U0001f4f0", layout="wide"
)

st.title("\U0001f4f0 Recent Updates")
st.caption("Latest releases, blog posts, and news across the Kubernetes ecosystem.")

# Sidebar filters
with st.sidebar:
    st.markdown("### Filters")

    view_mode = st.radio("View by", ["All recent", "By project"], index=0)

    SOURCES = [
        "github/kubernetes/kubernetes",
        "github/kyverno/kyverno",
        "github/helm/helm",
        "github/istio/istio",
        "github/cert-manager/cert-manager",
        "github/argoproj/argo-cd",
        "github/cilium/cilium",
        "github/kubernetes-sigs/gateway-api",
        "github/open-policy-agent/gatekeeper",
        "github/crossplane/crossplane",
        "rss/kubernetes-blog",
        "rss/lwkd",
        "rss/kubeweekly",
        "rss/cncf-blog",
        "rss/istio-news",
        "rss/kyverno-blog",
        "cve/kubernetes",
        "eol/kubernetes",
    ]

    selected_source = None
    if view_mode == "By project":
        # Show friendly names
        friendly = {s: s.split("/")[-1] for s in SOURCES}
        selected_source = st.selectbox(
            "Select source",
            SOURCES,
            format_func=lambda s: friendly[s],
        )

    label_filter = st.multiselect(
        "Filter by label",
        ["deprecation", "security", "feature", "release", "blog", "end of life"],
        default=[],
    )

    max_items = st.slider("Max items", 10, 100, 50)

# Fetch data
with st.spinner("Loading updates..."):
    try:
        if view_mode == "By project" and selected_source:
            items = query_by_source(selected_source, limit=max_items)
        else:
            items = query_recent(days=30, limit=max_items)

        # Apply label filter
        if label_filter:
            items = [i for i in items if i.get("label", "") in label_filter]

    except Exception as e:
        st.error(f"Failed to load updates: {e}")
        items = []

if not items:
    st.info("No updates found matching your filters.")
else:
    st.markdown(f"Showing **{len(items)}** items")

    for item in items:
        source = item.get("source", "unknown")
        project = source.split("/")[-1] if "/" in source else source
        date = item.get("published_at", "")[:10]
        label = item.get("label", "")
        url = item.get("url", "")
        title = item.get("title", "Untitled")
        source_type = item.get("source_type", "")

        # Label color mapping
        label_colors = {
            "deprecation": ":red[deprecation]",
            "security": ":red[security]",
            "feature": ":green[feature]",
            "release": ":blue[release]",
            "blog": ":violet[blog]",
            "end of life": ":orange[end of life]",
        }
        label_display = label_colors.get(label, label) if label else ""

        with st.container(border=True):
            col_main, col_meta = st.columns([4, 1])
            with col_main:
                if url:
                    st.markdown(f"**[{title}]({url})**")
                else:
                    st.markdown(f"**{title}**")
                if label_display:
                    st.markdown(label_display)
            with col_meta:
                st.caption(f"\U0001f4e6 {project}")
                st.caption(f"\U0001f4c5 {date}")
                if source_type:
                    st.caption(f"\U0001f3f7\ufe0f {source_type}")
