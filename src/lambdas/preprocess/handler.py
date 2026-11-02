"""Lambda handler for document preprocessing."""

import logging

from common.log import configure_logging
from tasks.preprocess import preprocess_document

configure_logging()
logger = logging.getLogger(__name__)


def handler(event: dict, context: object) -> dict:
    """Preprocess an uploaded document for the extraction pipeline."""
    logger.info("Preprocessing document: %s", event.get("s3_key"))
    return preprocess_document(event)
