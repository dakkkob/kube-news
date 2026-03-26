# Architecture

## System Overview

```
                         Mon/Wed/Fri 06:00-08:00 UTC (EC2 auto-started by Lambda)
                         =========================================================

  GitHub API ──┐
  RSS feeds  ──┤  06:00-06:45         07:15              07:45
  CVE feed   ──┼─► [ Ingestion ] ──► [ Process & Embed ] ──► [ Drift Check ]
  EOL API    ──┘        │                    │                      │
                        ▼                    ▼                      ▼
                   S3 (raw JSON)        Qdrant Cloud         DynamoDB (metrics)
                   DynamoDB (meta)      DynamoDB (labels)    GitHub Actions
                                        MLflow (metrics)     (if drifted)

  ───────────────────────────────────────────────────────────────────────────

  Streamlit Community Cloud (always on)
  ======================================

  User ──► [ RAG Chat ]           reads: Qdrant, S3, OpenAI (gpt-4o-mini)
       ──► [ Deprecation Alerts ] reads: DynamoDB
       ──► [ Recent Updates ]     reads: DynamoDB
       ──► [ MLOps Dashboard ]    reads: DynamoDB (drift-metrics table)
```

---

## Data Flow

### 1. Ingestion (4 parallel flows)

```
  GitHub Releases API                RSS/Atom Feeds
  (kubernetes, istio,                (k8s blog, LWKD,
   argo, envoy, ...)                  KubeWeekly, ...)
        │                                  │
        ▼                                  ▼
  fetch_releases()                   fetch_rss()
        │                                  │
        ├──── SHA-256 dedup ───────────────┤
        │     (item_exists?)               │
        ▼                                  ▼
  ┌──────────────┐                 ┌──────────────┐
  │  S3 Bucket   │                 │  S3 Bucket   │
  │  (full JSON) │                 │  (full JSON) │
  └──────┬───────┘                 └──────┬───────┘
         │                                │
         ▼                                ▼
  ┌──────────────────────────────────────────────┐
  │              DynamoDB (kube-news)             │
  │  item_id | source | title | s3_key | label="" │
  └──────────────────────────────────────────────┘

  Same pattern for CVE feed (pre-labeled "security")
  and endoflife.date API (pre-labeled "eol" if is_eol=true)
```

### 2. Process & Embed

```
  DynamoDB (label="")          S3 (full JSON)
  "unprocessed items"          "item body text"
        │                           │
        └───────────┬───────────────┘
                    ▼
            build_document()
            (title + body, clean HTML, normalize)
                    │
        ┌───────────┼────────────────┐
        ▼           ▼                ▼
  classify_text()  extract_entities()  embed_batch()
        │           │                │
        │     K8s entities:          │
        │     - API versions         │
        │     - CVE IDs              │
        │     - Resource kinds       │
        │     - Semver versions      │
        │           │                │
        ▼           ▼                ▼
  ┌─────────────────────┐    ┌──────────────┐
  │  DynamoDB (updated) │    │ Qdrant Cloud │
  │  label, confidence, │    │ 384-dim vecs │
  │  is_deprecation,    │    │ + payload    │
  │  is_security,       │    └──────────────┘
  │  entities           │
  └─────────────────────┘
```

### 3. Classifier Dual-Mode

```
  classify_text(doc)
        │
        ▼
  ┌─ CURRENT_MODEL file exists? ─┐
  │ YES                          │ NO
  ▼                              ▼
  Download from S3          Zero-shot BART-MNLI
  (DistilBERT, cached       (HuggingFace Inference API)
   in /tmp/kube-news-model)      │
        │                        │
        ▼                        ▼
  Local inference           API call with candidates:
  (torch.no_grad)           [deprecation, security,
        │                    feature, release, blog,
        │                    end of life]
        │                        │
        └────────┬───────────────┘
                 ▼
         confidence > 0.3?
         YES → return label
         NO  → return "unknown"
```

### 4. Drift Detection & Retraining

```
  Drift Check Flow (Mon/Wed/Fri 07:45 UTC)
  =========================================

  ┌─────────────────────┐     ┌──────────────┐
  │ DynamoDB             │     │ Qdrant Cloud │
  │ (7-day classified)  │     │ (500 vectors)│
  └─────────┬───────────┘     └──────┬───────┘
            ▼                        ▼
   Confidence Drift              Embedding Drift
   ┌────────────────┐           ┌────────────────────┐
   │ avg(confidence) │           │ PCA (10 components) │
   │ vs baseline     │           │ PSI vs baseline     │
   │ threshold: 0.05 │           │ threshold: 0.2      │
   └────────┬───────┘           └──────────┬─────────┘
            │                              │
            └──────────┬───────────────────┘
                       ▼
               Any drift detected?
               │ YES                │ NO
               ▼                    ▼
         repository_dispatch     Save metrics to
         → GitHub Actions        DynamoDB drift-metrics
               │
               ▼
  ┌──────────────────────────────────────────┐
  │  Retrain Workflow (GitHub Actions)       │
  │  1. Fetch silver labels from DynamoDB    │
  │  2. Get full text from S3                │
  │  3. Fine-tune DistilBERT (5 epochs)     │
  │  4. Evaluate (accuracy, F1)              │
  │  5. Upload model to S3 v{N}/             │
  │  6. Log to MLflow on DagsHub             │
  │  7. Open PR with CURRENT_MODEL update    │
  └──────────────────────────────────────────┘
               │
               ▼ (human merges PR)
         New model goes live
         on next process-and-embed run
```

### 5. RAG Chat

```
  User query: "What's deprecated in K8s 1.32?"
        │
        ▼
  embed_text(query)          → 384-dim vector
        │
        ▼
  Qdrant search              → 15 candidates (3x top_k)
        │
        ▼
  Re-rank: 90% similarity + 10% recency
  (exponential decay, 90-day half-life)
        │
        ▼
  Top 5 results → fetch full text from S3
        │
        ▼
  Build context (6000 char budget)
        │
        ▼
  gpt-4o-mini (system prompt + context + query)
        │
        ▼
  Answer with source citations
```

---

## Storage Schema

### DynamoDB: `kube-news` (single-table design)

| Field | Type | Description |
|-------|------|-------------|
| `item_id` | String (PK) | SHA-256 hash of source + unique key |
| `source` | String | e.g. `github/kubernetes/kubernetes` |
| `source_type` | String | github_release, rss_entry, cve, eol_cycle |
| `title` | String | Item title |
| `url` | String | Original URL |
| `published_at` | String | ISO 8601 timestamp |
| `s3_key` | String | Path to full JSON in S3 |
| `label` | String | deprecation, security, feature, release, blog, eol, unknown, "" |
| `confidence` | String | Classification confidence (0.0-1.0) |
| `is_deprecation` | String | "true"/"false" (string for GSI compatibility) |
| `is_security` | String | "true"/"false" |
| `entities` | String | JSON dict: api_versions, cve_ids, k8s_kinds, versions |

**GSIs:**
- `source-published_at-index` — query by source, sorted by date
- `deprecation-published_at-index` — query deprecations/security by date

### DynamoDB: `kube-news-drift-metrics`

| Field | Type | Description |
|-------|------|-------------|
| `check_type` | String (PK) | confidence, embedding_psi, or *_baseline |
| `timestamp` | String (SK) | ISO 8601, or "baseline" for baselines |
| `current_value` | Number | Current metric value |
| `baseline_value` | Number | Baseline comparison value |
| `delta` | Number | Difference |
| `is_drifted` | String | "true"/"false" |

### S3: `kube-news-raw`

```
kube-news-raw/
├── github/kubernetes/kubernetes/2024/03/26/{item_id}.json
├── rss/kubernetes-blog/2024/03/26/{item_id}.json
├── cve/kubernetes/2024/03/26/{item_id}.json
├── eol/kubernetes/2024/03/26/{item_id}.json
└── models/
    ├── classifier/v1/          # Fine-tuned DistilBERT
    │   ├── model.safetensors
    │   ├── config.json
    │   ├── tokenizer.json
    │   └── label2id.json
    └── drift/
        └── pca_baseline.npz   # PCA params for embedding drift
```

### Qdrant Cloud: `kube-news` collection

- **Vectors:** 384-dim (all-MiniLM-L6-v2), Cosine distance
- **Payload:** item_id, source, title, url, published_at, label, s3_key

---

## Schedule (Mon/Wed/Fri)

| UTC | Flow | Duration | Description |
|-----|------|----------|-------------|
| 05:50 | Lambda starts EC2 | — | EventBridge → Lambda |
| 06:00 | ingest-github-releases | ~5 min | ~15 repos |
| 06:15 | ingest-rss-feeds | ~5 min | ~10 feeds |
| 06:30 | ingest-k8s-cves | ~2 min | K8s CVE feed |
| 06:45 | ingest-endoflife | ~5 min | ~10 products |
| 07:15 | process-and-embed | ~15 min | Classify + embed new items |
| 07:45 | drift-check | ~2 min | Confidence + embedding PSI |
| 08:00 | Lambda stops EC2 | — | EventBridge → Lambda |

---

## Technology Stack

| Layer | Technology | Tier |
|-------|-----------|------|
| Orchestration | Prefect Cloud (serve mode) | Free |
| Compute | EC2 t3.micro (eu-north-1) | Free tier |
| Object Storage | S3 | Free tier |
| Database | DynamoDB (single-table + drift-metrics) | Free tier |
| Vector DB | Qdrant Cloud | Free (1 GB) |
| Embeddings | all-MiniLM-L6-v2 (384-dim, CPU) | Free / local |
| Classifier | DistilBERT fine-tuned → zero-shot BART-MNLI fallback | Free |
| LLM | gpt-4o-mini (RAG chat) | Pay-per-use |
| Experiment Tracking | MLflow on DagsHub | Free |
| Frontend | Streamlit Community Cloud | Free |
| CI/CD | GitHub Actions (lint, test, retrain) | Free (public repo) |
| IaC | Terraform | Free |
