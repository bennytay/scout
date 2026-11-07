# X is the scheduled newsroom; RedNote (小红书) is scanned too when a xiaohongshu-mcp server is configured.
# arXiv / GitHub / Hugging Face are kept as resolvers for the links posts point to
# (and can still be run by hand: `scout ingest --source arxiv` with an enabled arxiv_* source).
from . import arxiv, github, huggingface, rednote, x  # noqa: F401  (registers connectors)
from .base import REGISTRY, Connector, http_client, register  # noqa: F401

SCHEDULED = ("x", "rednote")  # each is skipped when its credentials / server aren't configured
