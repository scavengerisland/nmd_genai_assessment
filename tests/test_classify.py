"""Tests for classify_document()."""

import pytest
from botocore.exceptions import ClientError

from common.bedrock import BedrockThrottlingError
from tasks.classify import classify_document
from tests.fakes import text_response, tool_use_response

EVENT = {"document_id": "doc-1", "title": "CISA Advisory", "source": "CISA", "content": "CVE-2024-21887 ..."}


def classification(document_type="cybersecurity_advisory", confidence=0.95):
    return tool_use_response(
        "record_classification", {"document_type": document_type, "confidence": confidence, "evidence": "CVE IDs"}
    )


def test_returns_type_and_the_confidence_key_the_state_machine_reads(fake_bedrock):
    fake_bedrock(classification())

    result = classify_document(EVENT)

    assert result["document_type"] == "cybersecurity_advisory"
    assert result["classification_confidence"] == 0.95


@pytest.mark.parametrize(
    ("document_type", "confidence", "expected_confidence"),
    [("press_release", 0.9, 0.0), ("drug_approval", 0.3, 0.3)],
    ids=["label outside the set", "low confidence"],
)
def test_untrusted_answers_become_unknown(fake_bedrock, document_type, confidence, expected_confidence):
    fake_bedrock(classification(document_type, confidence))

    result = classify_document(EVENT)

    assert result["document_type"] == "unknown"
    assert result["classification_confidence"] == expected_confidence


def test_text_answer_with_code_fence_still_parses(fake_bedrock):
    fake_bedrock(text_response('```json\n{"document_type": "drug_approval", "confidence": 0.9}\n```'))

    assert classify_document(EVENT)["document_type"] == "drug_approval"


def test_cut_off_answer_becomes_unknown(fake_bedrock):
    fake_bedrock(tool_use_response("record_classification", {"document_type": "drug_approval"}, "max_tokens"))

    assert classify_document(EVENT)["document_type"] == "unknown"


def test_throttling_raises_the_error_name_step_functions_retries(fake_bedrock):
    fake_bedrock(ClientError({"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "InvokeModel"))

    with pytest.raises(BedrockThrottlingError):
        classify_document(EVENT)
