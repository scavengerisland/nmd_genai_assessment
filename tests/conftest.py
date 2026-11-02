"""Shared fixtures: fake AWS credentials, fresh cached clients, and a moto S3 bucket."""

import boto3
import pytest
from moto import mock_aws

from common.aws import get_bedrock_client, get_session
from common.settings import Settings

BUCKET = "nmd-genai-test-documents"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Use fake credentials and ignore any local .env, so tests never pick up a real AWS profile."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setattr("common.aws.get_settings", lambda: Settings(_env_file=None))
    get_session.cache_clear()
    get_bedrock_client.cache_clear()
    yield
    get_session.cache_clear()
    get_bedrock_client.cache_clear()


@pytest.fixture
def s3_bucket():
    """A moto-backed S3 bucket. Yields (client, bucket name)."""
    with mock_aws():
        client = boto3.client("s3", region_name="us-west-2")
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
        yield client, BUCKET


@pytest.fixture
def fake_bedrock(monkeypatch):
    """Install a FakeBedrock. Call the fixture with the responses to queue."""
    from tests.fakes import FakeBedrock

    def install(*responses):
        fake = FakeBedrock(*responses)
        monkeypatch.setattr("common.bedrock.get_bedrock_client", lambda: fake)
        return fake

    return install
