"""Test doubles for Bedrock Runtime."""

import io
import json
from pathlib import Path

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "golden.json").read_text())


def tool_use_response(name: str, tool_input: dict, stop_reason: str = "tool_use") -> dict:
    """Build an invoke_model response that holds one tool_use block."""
    return _response([{"type": "tool_use", "id": "toolu_test", "name": name, "input": tool_input}], stop_reason)


def text_response(text: str) -> dict:
    """Build an invoke_model response that holds one text block."""
    return _response([{"type": "text", "text": text}], "end_turn")


def _response(content: list, stop_reason: str) -> dict:
    payload = {"content": content, "stop_reason": stop_reason, "usage": {"input_tokens": 100, "output_tokens": 20}}
    return {"body": io.BytesIO(json.dumps(payload).encode())}


class FakeBedrock:
    """Records each invoke_model request and returns queued responses in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[dict] = []

    def invoke_model(self, **kwargs):
        self.requests.append({**kwargs, "body": json.loads(kwargs["body"])})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class GoldenBedrock:
    """Answers each request with the golden answer for the sample document in the prompt.

    Used by the local pipeline runner, so the pipeline runs end to end without AWS.
    """

    TITLE_CUES = {
        "Airworthiness Directive": "airworthiness-directive",
        "Cybersecurity Advisory": "cybersecurity-advisory",
        "FDA Approval": "drug-approval",
        "Form 8-K": "financial-filing",
    }

    def __init__(self):
        self.calls = 0

    def invoke_model(self, **kwargs):
        self.calls += 1
        body = json.loads(kwargs["body"])
        tool_name = body["tool_choice"]["name"]
        prompt = body["messages"][0]["content"]
        title = prompt.split("</title>", 1)[0]
        golden = next((GOLDEN[doc] for cue, doc in self.TITLE_CUES.items() if cue in title), None)

        if tool_name == "record_classification":
            if golden is None:
                return tool_use_response(tool_name, {"document_type": "unknown", "confidence": 0.3, "evidence": ""})
            return tool_use_response(
                tool_name, {"document_type": golden["document_type"], "confidence": 0.97, "evidence": title[7:80]}
            )
        return tool_use_response(tool_name, {**(golden or {}).get("extracted_fields", {}), "confidence": 0.9})
