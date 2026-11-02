"""Tests for aggregate_results()."""

import json

import pytest

from tasks.aggregate import aggregate_results


def pipeline_state(bucket, document_type="drug_approval", missing_fields=()):
    return {
        "preprocess_result": {"document_id": "drug-approval", "s3_bucket": bucket},
        "classify_result": {"document_type": document_type, "confidence": 0.97, "evidence": "NDA 217845"},
        "extract_result": {
            "extracted_fields": {"drug_name": "LUXTERA (miravimod)"},
            "confidence": 0.9,
            "missing_fields": list(missing_fields),
        },
    }


def test_writes_results_json_to_s3(s3_bucket):
    client, bucket = s3_bucket

    summary = aggregate_results(pipeline_state(bucket))

    obj = client.get_object(Bucket=bucket, Key="results/drug-approval.json")
    assert obj["ContentType"] == "application/json"
    assert json.loads(obj["Body"].read()) == summary
    assert summary["status"] == "completed"


@pytest.mark.parametrize(
    ("document_type", "missing", "reason"),
    [("unknown", (), "unclassified"), ("drug_approval", ("applicant",), "missing_fields")],
)
def test_incomplete_results_are_flagged_for_review(s3_bucket, document_type, missing, reason):
    _, bucket = s3_bucket

    summary = aggregate_results(pipeline_state(bucket, document_type, missing))

    assert summary["status"] == "needs_review"
    assert summary["review_reasons"] == [reason]
