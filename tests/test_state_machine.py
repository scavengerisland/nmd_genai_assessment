"""Contract tests: the Step Functions definition run against the real task code."""

import json
from pathlib import Path

import pytest

from scripts.local_pipeline import invoke_handler, load_definition, run_state_machine
from tests.fakes import GOLDEN, GoldenBedrock

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def golden_bedrock(monkeypatch):
    fake = GoldenBedrock()
    monkeypatch.setattr("common.bedrock.get_bedrock_client", lambda: fake)
    return fake


def upload(client, bucket, name, body):
    key = f"uploads/{name}.json"
    client.put_object(Bucket=bucket, Key=key, Body=body)
    return {"s3_bucket": bucket, "s3_key": key}


@pytest.mark.parametrize("sample", sorted(GOLDEN))
def test_each_sample_runs_end_to_end(s3_bucket, golden_bedrock, sample):
    client, bucket = s3_bucket
    execution_input = upload(client, bucket, sample, (ROOT / "data" / f"{sample}.json").read_bytes())

    output, trace = run_state_machine(load_definition(), execution_input)

    expected = GOLDEN[sample]
    assert output == {"document_id": sample, "document_type": expected["document_type"], "status": "completed"}
    assert dict(trace)["Extract"]["document_type"] == expected["document_type"]
    result = json.loads(client.get_object(Bucket=bucket, Key=f"results/{sample}.json")["Body"].read())
    assert result["extracted_fields"] == expected["extracted_fields"]


def test_unrelated_document_is_flagged_without_an_extraction_call(s3_bucket, golden_bedrock):
    client, bucket = s3_bucket
    memo = json.dumps({"title": "Office memo", "content": "Clean the kitchen on Fridays."})

    output, _ = run_state_machine(load_definition(), upload(client, bucket, "memo", memo))

    assert output == {"document_id": "memo", "document_type": "unknown", "status": "needs_review"}
    assert golden_bedrock.calls == 1


def test_every_result_selector_key_exists_in_the_task_output(s3_bucket, golden_bedrock):
    """Fails if a task stops returning a key that its ResultSelector reads."""
    client, bucket = s3_bucket
    execution_input = upload(client, bucket, "d", (ROOT / "data" / "drug-approval.json").read_bytes())
    outputs = {}

    def recording_invoke(function_arn, payload):
        outputs[function_arn] = invoke_handler(function_arn, payload)
        return outputs[function_arn]

    definition = load_definition()
    run_state_machine(definition, execution_input, recording_invoke)

    for state in definition["States"].values():
        returned = outputs[state["Parameters"]["FunctionName"]]
        for path in state.get("ResultSelector", {}).values():
            assert path.removeprefix("$.Payload.") in returned, f"{state['Parameters']['FunctionName']}: {path}"


def test_tasks_retry_transient_errors():
    states = load_definition()["States"]
    for name, state in states.items():
        retried = {error for rule in state.get("Retry", []) for error in rule["ErrorEquals"]}
        assert "Lambda.TooManyRequestsException" in retried, name
        if name in ("Classify", "Extract"):
            assert "BedrockThrottlingError" in retried, name
