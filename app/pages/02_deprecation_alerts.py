"""Deprecation Alerts — Deprecations, security, and EOL notices."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

from src.storage.dynamodb_client import query_deprecations, query_security  # noqa: E402

st.set_page_config(
    page_title="Deprecation Alerts | kube-news", page_icon="\u26a0\ufe0f", layout="wide"
)

st.title("\u26a0\ufe0f Deprecation & Security Alerts")
st.caption("Deprecations, security advisories, and end-of-life notices across the K8s ecosystem.")

# Tabs for different alert types
tab_dep, tab_sec = st.tabs(["\U0001f6a8 Deprecations", "\U0001f512 Security"])

with tab_dep:
    st.markdown("### Deprecation Notices")
    with st.spinner("Loading deprecations..."):
        try:
            items = query_deprecations(limit=50)
            if not items:
                st.info("No deprecation notices found yet.")
            else:
                for item in items:
                    source = item.get("source", "unknown")
                    project = source.split("/")[1] if "/" in source else source
                    date = item.get("published_at", "")[:10]
                    confidence = item.get("confidence", "")
                    url = item.get("url", "")
                    title = item.get("title", "Untitled")

                    with st.container(border=True):
                        col_main, col_meta = st.columns([3, 1])
                        with col_main:
                            if url:
                                st.markdown(f"**[{title}]({url})**")
                            else:
                                st.markdown(f"**{title}**")
                            # Show entities if available
                            entities = item.get("entities", {})
                            if entities:
                                tags = []
                                for api_ver in entities.get("api_versions", []):
                                    tags.append(f"`{api_ver}`")
                                for kind in entities.get("k8s_kinds", []):
                                    tags.append(f"`{kind}`")
                                if tags:
                                    st.markdown(" ".join(tags[:10]))
                        with col_meta:
                            st.caption(f"\U0001f4e6 {project}")
                            st.caption(f"\U0001f4c5 {date}")
                            source_type = item.get("source_type", "")
                            if source_type:
                                st.caption(f"\U0001f3f7\ufe0f {source_type}")
        except Exception as e:
            st.error(f"Failed to load deprecations: {e}")

with tab_sec:
    st.markdown("### Security Advisories")
    with st.spinner("Loading security items..."):
        try:
            items = query_security(limit=50)
            if not items:
                st.info("No security advisories found yet.")
            else:
                for item in items:
                    source = item.get("source", "unknown")
                    project = source.split("/")[1] if "/" in source else source
                    date = item.get("published_at", "")[:10]
                    cve_id = item.get("cve_id", "")
                    url = item.get("url", "")
                    title = item.get("title", "Untitled")

                    with st.container(border=True):
                        col_main, col_meta = st.columns([3, 1])
                        with col_main:
                            if url:
                                st.markdown(f"**[{title}]({url})**")
                            else:
                                st.markdown(f"**{title}**")
                            if cve_id:
                                st.markdown(f"\U0001f6e1\ufe0f `{cve_id}`")
                        with col_meta:
                            st.caption(f"\U0001f4e6 {project}")
                            st.caption(f"\U0001f4c5 {date}")
                            source_type = item.get("source_type", "")
                            if source_type:
                                st.caption(f"\U0001f3f7\ufe0f {source_type}")
        except Exception as e:
            st.error(f"Failed to load security advisories: {e}")
