"""LLM enrichment: summary, topics, authors/orgs, entities, importance,
Auki relevance, signal. One structured call per item."""
from functools import lru_cache
from pathlib import Path

from ..models import Enrichment, Item
from ..providers.llm import LLM

PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
TOPIC_LINES = {
    "manipulation": "grasping, dexterous/bimanual manipulation",
    "locomotion": "legged/wheeled/aerial movement",
    "humanoids": "humanoid platforms and whole-body control",
    "vla-foundation-models": "vision-language-action and robot foundation/world models",
    "sim2real": "simulation, synthetic data, sim-to-real transfer",
    "slam-spatial-mapping": "SLAM, localization, 3D reconstruction, shared maps, spatial computing",
    "perception": "vision, depth, segmentation, tracking, tactile sensing",
    "hardware": "actuators, sensors, robot bodies, compute",
    "datasets-benchmarks": "datasets, benchmarks, evaluations",
    "multi-agent": "multi-robot coordination, fleets, swarms",
    "other": "anything else robotics-related",
}


@lru_cache
def system_prompt() -> str:
    topics = "\n".join(f"    - `{k}`: {v}" for k, v in TOPIC_LINES.items())
    return (PROMPTS / "enrich.md").read_text().format(
        topics=topics, auki_context=(PROMPTS / "auki_context.md").read_text()
    )


def item_prompt(item: Item) -> str:
    body = item.summary or ""
    if item.full_text and len(body) < 400:
        body = (body + "\n\n" + item.full_text)[:6000]
    lines = [
        f"Type: {item.type}",
        f"Title: {item.title}",
        f"URL: {item.url}",
        f"Source: {item.source}",
        f"Known authors: {', '.join(item.authors[:15])}" if item.authors else "",
        f"Known orgs: {', '.join(item.orgs)}" if item.orgs else "",
        f"Content:\n{body[:6000]}",
    ]
    return "\n".join(l for l in lines if l)


async def enrich(llm: LLM, item: Item) -> tuple[Enrichment, float]:
    e, cost = await llm.structured(system_prompt(), item_prompt(item), Enrichment)
    e.auki_relevance = max(0.0, min(1.0, e.auki_relevance))
    e.importance = max(0.0, min(1.0, e.importance))
    e.topics = list(dict.fromkeys(e.topics))[:3] or ["other"]
    # Source metadata beats LLM extraction for authors when we have it (arXiv, HF).
    if item.authors:
        e.authors = item.authors
    return e, cost
