"""Lambda handler for document classification."""

import logging

from common.log import configure_logging
from tasks.classify import classify_document

configure_logging()
logger = logging.getLogger(__name__)


def handler(event: dict, context: object) -> dict:
    """Classify a document using Bedrock LLM."""
    logger.info("Classifying document: %s", event.get("document_id"))
    return classify_document(event)
