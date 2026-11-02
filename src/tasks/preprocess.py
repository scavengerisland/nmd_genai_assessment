"""Document preprocessing task logic."""

import json
import logging

from common.aws import get_s3_client

logger = logging.getLogger(__name__)


def preprocess_document(event: dict) -> dict:
    """Read a document from S3 and extract metadata for the pipeline.

    Args:
        event: Input with s3_bucket and s3_key.

    Returns:
        Document metadata including content and source info.
    """
    s3_bucket = event["s3_bucket"]
    s3_key = event["s3_key"]
    logger.info("Preprocessing %s/%s", s3_bucket, s3_key)

    s3 = get_s3_client()
    response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
    raw = response["Body"].read().decode("utf-8")
    doc = json.loads(raw)

    return {
        "document_id": document_id_from_key(s3_key),
        "s3_bucket": s3_bucket,
        "s3_key": s3_key,
        "title": doc.get("title", ""),
        "content": doc.get("content", ""),
        "source": doc.get("source", ""),
        "date": doc.get("date", ""),
        "status": "preprocessed",
    }


def document_id_from_key(s3_key: str) -> str:
    """Return the file name without its .json suffix: uploads/a.json.v2.json -> a.json.v2."""
    return s3_key.rsplit("/", 1)[-1].removesuffix(".json")
