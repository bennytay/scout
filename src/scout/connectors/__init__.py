# X is the only scheduled source. arXiv / GitHub / Hugging Face are kept as resolvers for the links posts point to
# (and can still be run by hand: `scout ingest --source arxiv` with an enabled arxiv_* source).
from . import arxiv, github, huggingface, x  # noqa: F401  (registers connectors)
from .base import REGISTRY, Connector, http_client, register  # noqa: F401

SCHEDULED = ("x",)
