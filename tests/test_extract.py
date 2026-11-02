"""Tests for extract_fields()."""

from tasks.extract import extract_fields
from tests.fakes import tool_use_response


def event(document_type):
    return {"document_id": "doc-1", "title": "T", "content": "...", "document_type": document_type}


def test_unknown_type_makes_no_model_call(fake_bedrock):
    fake = fake_bedrock()

    result = extract_fields(event("unknown"))

    assert result["extracted_fields"] == {}
    assert fake.requests == []


def test_output_is_normalized_to_the_schema(fake_bedrock):
    fake_bedrock(
        tool_use_response(
            "record_fields",
            {
                "company_name": "Meridian Technologies Inc.",
                "filing_date": "",
                "revenue": "$487,300,000",
                "net_income": 62100000.0,
                "ceo_ssn": "123-45-6789",
                "confidence": 0.8,
            },
        )
    )

    result = extract_fields(event("financial_filing"))

    assert result["extracted_fields"] == {
        "company_name": "Meridian Technologies Inc.",
        "filing_date": None,
        "event_type": None,
        "revenue": 487300000,
        "net_income": 62100000,
    }
    assert result["missing_fields"] == ["filing_date", "event_type"]
    assert result["extraction_confidence"] == 0.8


def test_list_fields_are_coerced_to_lists(fake_bedrock):
    fake_bedrock(
        tool_use_response(
            "record_fields",
            {"severity": "Critical", "cve_ids": "CVE-2024-1", "affected_products": None, "mitigation_steps": ["Patch"]},
        )
    )

    fields = extract_fields(event("cybersecurity_advisory"))["extracted_fields"]

    assert fields["cve_ids"] == ["CVE-2024-1"]
    assert fields["affected_products"] == []
