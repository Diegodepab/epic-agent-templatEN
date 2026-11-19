"""Application entrypoint for {{PROJECT_NAME}}."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def health_status() -> dict[str, str]:
    """Return service health metadata."""
    return {"status": "ok", "env": os.getenv("APP_ENV", "development")}


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    logger.info("Service initialized: %s", health_status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
