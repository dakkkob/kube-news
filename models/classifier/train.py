"""Fine-tune DistilBERT on silver labels from the zero-shot classifier.

Designed to run on GitHub Actions (7 GB RAM).  Reads training data from
DynamoDB + S3, trains a DistilBERT sequence classifier, evaluates, logs
metrics to MLflow on DagsHub, and uploads the model to S3.

Usage:
    python models/classifier/train.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
from datasets import Dataset
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

from src.config import (
    AWS_REGION,
    CLASSIFIER_S3_PREFIX,
    MLFLOW_TRACKING_URI,
    S3_BUCKET,
)
from src.processing.text_cleaner import build_document
from src.storage.dynamodb_client import query_classified_items
from src.storage.s3_client import get_item

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_NAME = "distilbert-base-uncased"
MAX_LENGTH = 256
MIN_SAMPLES = 100

LABEL_NAMES = ["deprecation", "security", "feature", "release", "blog", "eol"]
LABEL2ID = {name: i for i, name in enumerate(LABEL_NAMES)}
ID2LABEL = {i: name for i, name in enumerate(LABEL_NAMES)}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_training_data() -> tuple[list[str], list[int]]:
    """Fetch silver-labeled items from DynamoDB + S3."""
    logger.info("Fetching classified items from DynamoDB (all labeled)...")
    items = query_classified_items(days=365, min_confidence=0.0, limit=5000)
    logger.info("Found %d candidate items", len(items))

    texts: list[str] = []
    labels: list[int] = []

    for item in items:
        label_str = item.get("label", "")
        if label_str not in LABEL2ID:
            continue

        # Try to get full text from S3
        s3_key = item.get("s3_key", "")
        body = ""
        if s3_key:
            try:
                full_item = get_item(s3_key)
                body = full_item.get("body", "") or full_item.get("content", "") or ""
            except Exception:
                pass

        text = build_document(
            {
                "title": item.get("title", ""),
                "body": body,
                "content": body,
            }
        )

        if len(text.strip()) < 20:
            continue

        texts.append(text[:2000])  # Truncate long docs
        labels.append(LABEL2ID[label_str])

    return texts, labels


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _compute_metrics(eval_pred: tuple) -> dict[str, float]:  # type: ignore[type-arg]
    """Compute accuracy and weighted F1 for the Trainer."""
    logits, label_ids = eval_pred
    predictions = np.argmax(logits, axis=-1)
    acc = accuracy_score(label_ids, predictions)
    f1 = f1_score(label_ids, predictions, average="weighted", zero_division=0)
    return {"accuracy": float(acc), "f1_weighted": float(f1)}


# ---------------------------------------------------------------------------
# S3 upload
# ---------------------------------------------------------------------------


def _next_model_version() -> int:
    """Determine the next model version number from S3."""
    import boto3

    s3 = boto3.client("s3", region_name=AWS_REGION)
    prefix = CLASSIFIER_S3_PREFIX
    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix, Delimiter="/")
    versions = []
    for cp in response.get("CommonPrefixes", []):
        folder = cp["Prefix"].rstrip("/").split("/")[-1]
        if folder.startswith("v") and folder[1:].isdigit():
            versions.append(int(folder[1:]))
    return max(versions, default=0) + 1


def _upload_model_to_s3(local_dir: str, version: int) -> str:
    """Upload model directory to S3. Returns the S3 prefix."""
    import boto3

    s3 = boto3.client("s3", region_name=AWS_REGION)
    s3_prefix = f"{CLASSIFIER_S3_PREFIX}v{version}/"

    for root, _dirs, files in os.walk(local_dir):
        for filename in files:
            local_path = os.path.join(root, filename)
            relative = os.path.relpath(local_path, local_dir)
            s3_key = f"{s3_prefix}{relative}"
            s3.upload_file(local_path, S3_BUCKET, s3_key)
            logger.info("Uploaded %s → s3://%s/%s", relative, S3_BUCKET, s3_key)

    return s3_prefix


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def train() -> None:
    """Run the full training pipeline."""
    texts, labels = _load_training_data()

    if len(texts) < MIN_SAMPLES:
        logger.error(
            "Not enough training data: %d samples (minimum %d). "
            "Wait for more items to be classified.",
            len(texts),
            MIN_SAMPLES,
        )
        sys.exit(1)

    # Label distribution
    label_dist = {name: labels.count(i) for name, i in LABEL2ID.items()}
    logger.info("Label distribution: %s", label_dist)
    logger.info("Total training samples: %d", len(texts))

    # Train/val split
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=0.2, stratify=labels, random_state=42
    )
    logger.info("Train: %d, Val: %d", len(train_texts), len(val_texts))

    # Tokenize
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    train_encodings = tokenizer(train_texts, truncation=True, padding=True, max_length=MAX_LENGTH)
    val_encodings = tokenizer(val_texts, truncation=True, padding=True, max_length=MAX_LENGTH)

    # Create datasets
    train_dataset = Dataset.from_dict(
        {
            **train_encodings,
            "labels": train_labels,
        }
    )
    val_dataset = Dataset.from_dict(
        {
            **val_encodings,
            "labels": val_labels,
        }
    )

    # Model
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=len(LABEL_NAMES),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    # Training
    output_dir = "/tmp/kube-news-classifier-output"
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=32,
        learning_rate=2e-5,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_weighted",
        greater_is_better=True,
        logging_steps=50,
        report_to="none",  # We log to MLflow manually
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=_compute_metrics,
    )

    logger.info("Starting training...")
    trainer.train()

    # Evaluate
    eval_results = trainer.evaluate()
    logger.info("Eval results: %s", eval_results)

    # Detailed classification report
    predictions = trainer.predict(val_dataset)
    pred_labels = np.argmax(predictions.predictions, axis=-1)
    report = classification_report(
        val_labels, pred_labels, target_names=LABEL_NAMES, zero_division=0
    )
    logger.info("Classification report:\n%s", report)

    # Save model locally
    save_dir = f"{output_dir}/best_model"
    trainer.save_model(save_dir)
    tokenizer.save_pretrained(save_dir)

    # Save label mapping
    with open(f"{save_dir}/label2id.json", "w") as f:
        json.dump(LABEL2ID, f, indent=2)

    # Upload to S3
    version = _next_model_version()
    s3_prefix = _upload_model_to_s3(save_dir, version)
    logger.info("Model uploaded to s3://%s/%s", S3_BUCKET, s3_prefix)

    # Write CURRENT_MODEL for git commit
    current_model_path = Path(__file__).parent / "CURRENT_MODEL"
    current_model_path.write_text(f"s3://{S3_BUCKET}/{s3_prefix}\n")
    logger.info("Wrote %s", current_model_path)

    # Log to MLflow
    if MLFLOW_TRACKING_URI:
        try:
            import mlflow

            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            mlflow.set_experiment("kube-news-classifier")

            with mlflow.start_run(run_name=f"distilbert-v{version}"):
                mlflow.log_params(
                    {
                        "model_name": MODEL_NAME,
                        "max_length": MAX_LENGTH,
                        "num_epochs": 5,
                        "learning_rate": 2e-5,
                        "batch_size": 16,
                        "train_samples": len(train_texts),
                        "val_samples": len(val_texts),
                    }
                )
                for key, value in eval_results.items():
                    if isinstance(value, (int, float)):
                        mlflow.log_metric(key.replace("eval_", ""), value)
                mlflow.set_tag("model_type", "distilbert-finetuned")
                mlflow.set_tag("model_version", f"v{version}")
                mlflow.set_tag("s3_path", f"s3://{S3_BUCKET}/{s3_prefix}")
                mlflow.log_dict(label_dist, "label_distribution.json")

            logger.info("Logged training run to MLflow")
        except Exception:
            logger.warning("MLflow logging failed", exc_info=True)

    # Export metrics for GitHub Actions
    accuracy = eval_results.get("eval_accuracy", 0.0)
    f1_weighted = eval_results.get("eval_f1_weighted", 0.0)

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"MODEL_VERSION={version}\n")
            f.write(f"ACCURACY={accuracy:.4f}\n")
            f.write(f"F1_WEIGHTED={f1_weighted:.4f}\n")
            f.write(f"NUM_SAMPLES={len(texts)}\n")

    logger.info(
        "Training complete: v%d — accuracy=%.4f, f1=%.4f, samples=%d",
        version,
        accuracy,
        f1_weighted,
        len(texts),
    )


if __name__ == "__main__":
    train()
