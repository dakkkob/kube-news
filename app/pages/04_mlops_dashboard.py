"""MLOps Dashboard — Drift monitoring and model health."""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

from src.storage.dynamodb_client import (  # noqa: E402
    query_classified_items,
    query_drift_metrics,
)

st.set_page_config(page_title="MLOps Dashboard | kube-news", page_icon="\U0001f4ca", layout="wide")

st.title("\U0001f4ca MLOps Dashboard")
st.caption("Drift monitoring, model health, and label distribution.")

# ---------------------------------------------------------------------------
# Current model info
# ---------------------------------------------------------------------------

st.markdown("### Current Model")

current_model_file = (
    Path(__file__).resolve().parent.parent.parent / "models" / "classifier" / "CURRENT_MODEL"
)
if current_model_file.exists():
    model_uri = current_model_file.read_text().strip()
    st.success(f"Active model: `{model_uri}`")
else:
    st.info("No fine-tuned model deployed yet. Using zero-shot BART-MNLI classifier.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Confidence drift
# ---------------------------------------------------------------------------

st.markdown("### Confidence Drift")

with st.spinner("Loading confidence metrics..."):
    try:
        conf_metrics = query_drift_metrics("confidence", limit=30)
        if not conf_metrics:
            st.info("No confidence drift data yet. Drift checks run after each processing cycle.")
        else:
            chart_data = []
            for m in reversed(conf_metrics):
                chart_data.append(
                    {
                        "timestamp": m.get("timestamp", "")[:16],
                        "Current Avg": float(m.get("current_value", 0)),
                        "Baseline": float(m.get("baseline_value", 0)),
                    }
                )

            st.line_chart(
                data=chart_data,
                x="timestamp",
                y=["Current Avg", "Baseline"],
                use_container_width=True,
            )

            # Show latest status
            latest = conf_metrics[0]
            is_drifted = latest.get("is_drifted", "false") == "true"
            delta = float(latest.get("delta", 0))
            if is_drifted:
                st.error(f"Drift detected! Confidence dropped by {delta:.4f}")
            else:
                st.success(f"No drift. Delta: {delta:.4f}")
    except Exception as e:
        st.warning(f"Failed to load confidence metrics: {e}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Embedding drift (PSI)
# ---------------------------------------------------------------------------

st.markdown("### Embedding Drift (PSI)")

with st.spinner("Loading PSI metrics..."):
    try:
        psi_metrics = query_drift_metrics("embedding_psi", limit=30)
        if not psi_metrics:
            st.info("No embedding drift data yet.")
        else:
            chart_data = []
            for m in reversed(psi_metrics):
                chart_data.append(
                    {
                        "timestamp": m.get("timestamp", "")[:16],
                        "PSI": float(m.get("current_value", 0)),
                        "Threshold": 0.2,
                    }
                )

            st.line_chart(
                data=chart_data,
                x="timestamp",
                y=["PSI", "Threshold"],
                use_container_width=True,
            )

            latest = psi_metrics[0]
            is_drifted = latest.get("is_drifted", "false") == "true"
            psi_val = float(latest.get("current_value", 0))
            if is_drifted:
                st.error(f"Embedding drift detected! PSI: {psi_val:.4f} (threshold: 0.2)")
            else:
                st.success(f"No embedding drift. PSI: {psi_val:.4f}")
    except Exception as e:
        st.warning(f"Failed to load PSI metrics: {e}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Label distribution
# ---------------------------------------------------------------------------

st.markdown("### Recent Label Distribution")

days = st.slider("Look back (days)", min_value=7, max_value=90, value=30)

with st.spinner("Loading classified items..."):
    try:
        items = query_classified_items(days=days, min_confidence=0.0, limit=2000)
        if not items:
            st.info("No classified items in this time range.")
        else:
            label_counts = Counter(item.get("label", "unknown") for item in items)
            labels_sorted = sorted(label_counts.items(), key=lambda x: x[1], reverse=True)

            chart_data = [{"Label": label, "Count": count} for label, count in labels_sorted]
            st.bar_chart(data=chart_data, x="Label", y="Count", use_container_width=True)

            # Summary stats
            total = len(items)
            avg_conf = sum(float(i.get("confidence", "0") or "0") for i in items) / total
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Items", total)
            col2.metric("Avg Confidence", f"{avg_conf:.3f}")
            col3.metric("Unique Labels", len(label_counts))
    except Exception as e:
        st.warning(f"Failed to load label distribution: {e}")
