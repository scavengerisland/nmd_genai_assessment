"""Run the real Step Functions definition against the real Lambda handlers, on this machine.

The interpreter covers the subset of Amazon States Language this pipeline uses:
Task states with Parameters, ResultSelector, ResultPath, Next and End. Each Task
calls the handler in-process and passes the payload through JSON, as Lambda does.

Run it with `make local-run`. S3 is served by moto and Bedrock by a fake that
returns the golden answers in tests/fixtures/golden.json, so nothing touches AWS.
"""

import copy
import importlib
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASL_PATH = ROOT / "terraform" / "modules" / "step-functions" / "state_machine.asl.json"
FUNCTIONS = ("preprocess", "classify", "extract", "aggregate")

Invoker = Callable[[str, dict], dict]


def load_definition() -> dict:
    """Render the ASL template the way Terraform's templatefile() does, with local ARNs."""
    text = ASL_PATH.read_text()
    for name in FUNCTIONS:
        text = text.replace("${" + name + "_arn}", f"local:{name}")
    return json.loads(text)


def get_path(data: object, path: str) -> object:
    """Resolve a JSONPath such as $ or $.a.b. A missing key raises KeyError, as Step Functions fails."""
    if path == "$":
        return data
    if not path.startswith("$."):
        raise ValueError(f"Unsupported path: {path}")
    for part in path[2:].split("."):
        if not isinstance(data, dict) or part not in data:
            raise KeyError(f"Path {path} not found (missing {part!r})")
        data = data[part]
    return data


def set_path(data: dict, path: str, value: object) -> object:
    """Return a copy of `data` with `value` placed at `path`."""
    if path == "$":
        return value
    result = copy.deepcopy(data)
    node = result
    parts = path[2:].split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    return result


def resolve(template: object, data: object) -> object:
    """Apply a Parameters or ResultSelector template: keys ending in .$ are paths into `data`."""
    if not isinstance(template, dict):
        return template
    out = {}
    for key, value in template.items():
        if key.endswith(".$"):
            out[key[:-2]] = get_path(data, value)
        else:
            out[key] = resolve(value, data)
    return out


def invoke_handler(function_arn: str, payload: dict) -> dict:
    """Call the Lambda handler that a local:<name> ARN points to."""
    name = function_arn.removeprefix("local:")
    module = importlib.import_module(f"lambdas.{name}.handler")
    event = json.loads(json.dumps(payload))
    return json.loads(json.dumps(module.handler(event, None)))


def run_state_machine(definition: dict, execution_input: dict, invoke: Invoker = invoke_handler) -> tuple[dict, list]:
    """Execute the definition. Returns (final output, [(state name, task payload), ...])."""
    data: object = execution_input
    trace = []
    state_name = definition["StartAt"]
    while True:
        state = definition["States"][state_name]
        if state["Type"] != "Task":
            raise NotImplementedError(f"State type {state['Type']} is not supported locally")
        params = resolve(state["Parameters"], data)
        trace.append((state_name, params["Payload"]))
        result: object = {"Payload": invoke(params["FunctionName"], params["Payload"])}
        if "ResultSelector" in state:
            result = resolve(state["ResultSelector"], result)
        data = set_path(data, state.get("ResultPath", "$"), result)
        if state.get("End"):
            return data, trace
        state_name = state["Next"]


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT))
    for key in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        os.environ.pop(key, None)
    os.environ.update(
        AWS_ACCESS_KEY_ID="local",
        AWS_SECRET_ACCESS_KEY="local",
        AWS_DEFAULT_REGION="us-west-2",
        LOG_LEVEL=os.environ.get("LOG_LEVEL", "WARNING"),
    )

    import boto3
    from moto import mock_aws

    import common.aws
    import common.bedrock
    from common.settings import Settings
    from tests.fakes import GoldenBedrock

    # Ignore any local .env, so a named AWS profile there cannot take effect.
    common.aws.get_settings = lambda: Settings(_env_file=None)
    bucket = "nmd-genai-local-documents"
    bedrock = GoldenBedrock()
    common.bedrock.get_bedrock_client = lambda: bedrock

    documents = {path.name: path.read_text() for path in sorted((ROOT / "data").glob("*.json"))}
    documents["unrelated-memo.json"] = json.dumps(
        {"title": "Office memo: kitchen rota", "content": "Please clean the kitchen on Fridays."}
    )

    definition = load_definition()
    failures = 0
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-west-2")
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})

        print(f"{'document':<28} {'type':<24} {'class':>5} {'extr':>5}  {'fields':<6} status")
        for name, body in documents.items():
            key = f"uploads/{name}"
            s3.put_object(Bucket=bucket, Key=key, Body=body)
            # Same shape as the EventBridge input_transformer output.
            try:
                output, _ = run_state_machine(definition, {"s3_bucket": bucket, "s3_key": key})
            except Exception as exc:  # report every document, then fail at the end
                failures += 1
                print(f"{name:<28} FAILED: {type(exc).__name__}: {exc}")
                continue
            result_key = f"results/{output['document_id']}.json"
            result = json.loads(s3.get_object(Bucket=bucket, Key=result_key)["Body"].read())
            filled = sum(1 for value in result["extracted_fields"].values() if value not in (None, []))
            print(
                f"{name:<28} {result['document_type']:<24} {result['classification_confidence']:>5.2f} "
                f"{result['extraction_confidence']:>5.2f}  {filled}/{len(result['extracted_fields']):<4} "
                f"{result['status']} {' '.join(result['review_reasons'])}"
            )

        keys = [obj["Key"] for obj in s3.list_objects_v2(Bucket=bucket, Prefix="results/").get("Contents", [])]
        print(f"\nresults/ holds {len(keys)} files. Fake Bedrock calls: {bedrock.calls}.")
        sample = ROOT / "data" / "drug-approval.json"
        if sample.exists():
            body = s3.get_object(Bucket=bucket, Key="results/drug-approval.json")["Body"].read().decode()
            print(f"\nresults/drug-approval.json:\n{body}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
