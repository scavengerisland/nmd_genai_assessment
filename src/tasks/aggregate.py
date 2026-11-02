"""Results aggregation task logic."""

import json
import logging
import os
from datetime import UTC, datetime

from common.aws import get_s3_client

logger = logging.getLogger(__name__)

# Results below this extraction confidence are flagged for human review.
MIN_EXTRACTION_CONFIDENCE = 0.5


def aggregate_results(event: dict) -> dict:
    """Aggregate extraction results and write summary to S3.

    Writes the summary to s3://{bucket}/results/{document_id}.json.

    Args:
        event: Full pipeline state with preprocess, classify, and extract results.

    Returns:
        Summary of the pipeline execution.
    """
    logger.info("Aggregating results")

    preprocess = event.get("preprocess_result", {})
    classify = event.get("classify_result", {})
    extract = event.get("extract_result", {})
    document_id = preprocess.get("document_id", "unknown")
    s3_bucket = preprocess.get("s3_bucket") or os.environ.get("S3_BUCKET_NAME", "")
    if not s3_bucket:
        raise ValueError("No S3 bucket in the pipeline state or in S3_BUCKET_NAME")

    document_type = classify.get("document_type", "unknown")
    extraction_confidence = extract.get("confidence", 0.0)
    missing_fields = extract.get("missing_fields", [])

    review_reasons = []
    if document_type == "unknown":
        review_reasons.append("unclassified")
    else:
        if missing_fields:
            review_reasons.append("missing_fields")
        if extraction_confidence < MIN_EXTRACTION_CONFIDENCE:
            review_reasons.append("low_extraction_confidence")

    summary = {
        "document_id": document_id,
        "document_type": document_type,
        "classification_confidence": classify.get("confidence", 0.0),
        "classification_evidence": classify.get("evidence", ""),
        "extracted_fields": extract.get("extracted_fields", {}),
        "extraction_confidence": extraction_confidence,
        "missing_fields": missing_fields,
        "status": "needs_review" if review_reasons else "completed",
        "review_reasons": review_reasons,
        "processed_at": datetime.now(UTC).isoformat(),
    }

    key = f"results/{document_id}.json"
    get_s3_client().put_object(
        Bucket=s3_bucket,
        Key=key,
        Body=json.dumps(summary, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    logger.info("Wrote s3://%s/%s (status: %s)", s3_bucket, key, summary["status"])

    return summary
