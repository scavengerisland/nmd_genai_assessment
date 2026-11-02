"""AWS client factories with lazy session caching."""

from functools import lru_cache

import boto3
from botocore.config import Config

from common.settings import get_settings


@lru_cache
def get_session() -> boto3.Session:
    """Cached boto3 session."""
    settings = get_settings()
    return boto3.Session(profile_name=settings.aws_profile, region_name=settings.aws_region)


def get_s3_client():
    """Get S3 client."""
    return get_session().client("s3")


@lru_cache
def get_bedrock_client():
    """Get a cached Bedrock Runtime client with extended timeout.

    Caching keeps adaptive retry state across calls in a warm Lambda. Retries
    stay low on purpose: Step Functions retries throttles with backoff, and SDK
    retries multiply with them.
    """
    return get_session().client(
        "bedrock-runtime",
        config=Config(read_timeout=180, retries={"max_attempts": 2, "mode": "adaptive"}),
    )
