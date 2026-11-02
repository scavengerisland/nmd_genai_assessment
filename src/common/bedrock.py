"""Bedrock helpers: one forced tool call per request, parsed into a dict."""

import json
import logging
import re

from botocore.exceptions import ClientError, ConnectionError, ReadTimeoutError

from common.aws import get_bedrock_client

logger = logging.getLogger(__name__)

ANTHROPIC_VERSION = "bedrock-2023-05-31"

# Transient errors that Step Functions retries with backoff. Everything else fails fast.
RETRYABLE_ERROR_CODES = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelNotReadyException",
    "ModelTimeoutException",
}


class BedrockThrottlingError(Exception):
    """Bedrock throttled or was briefly unavailable. Step Functions retries this error name."""


class BedrockResponseError(Exception):
    """Bedrock answered, but the answer had no usable structured output."""


def invoke_tool(
    *,
    model_id: str,
    system: str,
    prompt: str,
    tool: dict,
    max_tokens: int = 1024,
) -> dict:
    """Call a Claude model on Bedrock and force it to answer through `tool`.

    The tool's input_schema is the output contract, so the model returns
    structured JSON instead of prose. Sampling parameters are left at their
    defaults: Claude Haiku 5.5 rejects any non-default temperature.

    Returns:
        The tool input the model produced.

    Raises:
        BedrockThrottlingError: on throttling or a transient service or network error.
        BedrockResponseError: when the output was cut off, refused, or unparseable.
    """
    body = {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool["name"]},
    }

    try:
        response = get_bedrock_client().invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in RETRYABLE_ERROR_CODES:
            raise BedrockThrottlingError(f"{code}: {exc}") from exc
        raise
    except (ReadTimeoutError, ConnectionError) as exc:
        raise BedrockThrottlingError(f"{type(exc).__name__}: {exc}") from exc

    payload = json.loads(response["body"].read())
    stop_reason = payload.get("stop_reason")
    usage = payload.get("usage", {})
    logger.info(
        "Bedrock call: model=%s tool=%s stop_reason=%s input_tokens=%s output_tokens=%s",
        model_id,
        tool["name"],
        stop_reason,
        usage.get("input_tokens"),
        usage.get("output_tokens"),
    )

    # A cut-off tool call can still parse as a valid but partial object, so reject it.
    if stop_reason in ("max_tokens", "refusal"):
        raise BedrockResponseError(f"Model stopped with stop_reason={stop_reason}")

    for block in payload.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == tool["name"]:
            return block.get("input", {})

    # Fallback: the model answered in text. Take the JSON object from it.
    text = "".join(block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text")
    return parse_json_object(text)


def parse_json_object(text: str) -> dict:
    """Parse the first JSON object in `text`, ignoring code fences and prose around it."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise BedrockResponseError(f"No JSON object in model output: {text[:200]!r}")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise BedrockResponseError(f"Invalid JSON in model output: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BedrockResponseError("Model output JSON is not an object")
    return parsed


def clamp_confidence(value: object) -> float:
    """Return `value` as a float in [0.0, 1.0]. Anything unparseable becomes 0.0."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN
        return 0.0
    return max(0.0, min(1.0, number))


def document_prompt(*, title: str, source: str, date: str, content: str) -> str:
    """Wrap the document in tags. A closing tag inside the content cannot end the wrapper early."""
    safe = content.replace("</document>", "</ document>")
    return f"<title>{title}</title>\n<source>{source}</source>\n<date>{date}</date>\n<document>\n{safe}\n</document>"
