import logging
import sys

import structlog


def setup(level: str = "INFO", json: bool | None = None) -> None:
    json = (not sys.stderr.isatty()) if json is None else json
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=level)
    for noisy in ("httpx", "httpcore", "discord.gateway"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),  # stdout is reserved for MCP stdio
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
    )


log = structlog.get_logger()
