"""LLM adapter. One interface, providers: anthropic (Claude), fake (offline/tests)."""
import re
from typing import Protocol, TypeVar

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    model: str

    async def structured(self, system: str, user: str, schema: type[T]) -> tuple[T, float]: ...
    async def text(self, system: str, user: str, max_tokens: int = 2000) -> tuple[str, float]: ...


PRICES = {  # $/MTok (input, output); anything else falls back to LLM_*_USD_PER_MTOK
    "claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0),
}


def _cost(inp: int, out: int, model: str | None = None) -> float:
    s = settings()
    pin, pout = PRICES.get(model or "", (s.llm_input_usd_per_mtok, s.llm_output_usd_per_mtok))
    return inp / 1e6 * pin + out / 1e6 * pout


class AnthropicLLM:
    def __init__(self, model: str):
        from anthropic import AsyncAnthropic

        self.model = model
        self.client = AsyncAnthropic(api_key=settings().anthropic_api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=20), reraise=True)
    async def structured(self, system, user, schema):
        r = await self.client.messages.parse(
            model=self.model,
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        return r.parsed_output, _cost(r.usage.input_tokens, r.usage.output_tokens, self.model)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=20), reraise=True)
    async def text(self, system, user, max_tokens=2000):
        r = await self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}]
        )
        out = "".join(b.text for b in r.content if b.type == "text")
        return out, _cost(r.usage.input_tokens, r.usage.output_tokens, self.model)


KEYWORDS = {
    "manipulation": r"manipulat|grasp|dexter|pick-and-place|bimanual|gripper",
    "locomotion": r"locomot|legged|quadruped|gait|walking|biped",
    "humanoids": r"humanoid",
    "vla-foundation-models": r"vision-language-action|\bvla\b|foundation model|generalist polic|world model",
    "sim2real": r"sim2real|sim-to-real|simulat|domain random|synthetic data",
    "slam-spatial-mapping": r"\bslam\b|locali[sz]|mapping|reconstruct|spatial|gaussian splat|nerf|relocali",
    "perception": r"percept|segment|detect|depth|tracking|point cloud|tactile",
    "hardware": r"actuator|hardware|motor|sensor|exoskeleton",
    "datasets-benchmarks": r"dataset|benchmark",
    "multi-agent": r"multi-agent|multi-robot|swarm|fleet",
}


class FakeLLM:
    """Deterministic keyword heuristics. Lets the full pipeline run with no API keys (tests, demos)."""

    model = "fake-heuristic"

    async def structured(self, system, user, schema):
        from ..models import Enrichment, Entities

        if schema.__name__ == "Brief":  # offline: one story per candidate, highest relevance first
            ids = [int(m) for m in re.findall(r"^\[(\d+)\]", user, re.M)][:8]
            return schema.model_validate({"stories": [
                {"headline": f"Story {i}", "why": "Offline heuristic brief.", "primary_id": i, "supporting_ids": []}
                for i in ids]}), 0.0
        if schema is not Enrichment:  # e.g. QueryPlan for /ask: plain keyword search
            return schema.model_validate({"query": user}), 0.0
        low = user.lower()
        topics = [t for t, rx in KEYWORDS.items() if re.search(rx, low)][:3] or ["other"]
        rel = 0.85 if "slam-spatial-mapping" in topics else 0.6 if "multi-agent" in topics else 0.35
        title = re.search(r"title:\s*(.+)", user, re.IGNORECASE)
        summary = (title.group(1) if title else user[:200]).strip()
        e = Enrichment(
            summary=summary, topics=topics, authors=[], orgs=[], entities=Entities(),
            auki_relevance=rel, auki_relevance_reason=f"Heuristic: topics {', '.join(topics)}.",
            importance=0.3 if topics == ["other"] else 0.5,
            signal="off_topic" if topics == ["other"] else "news",
        )
        return e, 0.0

    async def text(self, system, user, max_tokens=2000):
        return "(fake LLM) " + user[:500], 0.0


def get_llm(model: str | None = None) -> LLM:
    s = settings()
    if s.llm_provider == "anthropic":
        return AnthropicLLM(model or s.llm_model)
    return FakeLLM()
