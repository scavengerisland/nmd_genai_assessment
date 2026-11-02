"""Lambda handler for aggregating extraction results."""

import logging

from common.log import configure_logging
from tasks.aggregate import aggregate_results

configure_logging()
logger = logging.getLogger(__name__)


def handler(event: dict, context: object) -> dict:
    """Aggregate extraction results and write final output to S3."""
    logger.info("Aggregating results")
    return aggregate_results(event)
