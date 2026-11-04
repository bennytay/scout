"""LLM adapter. One interface, swappable providers: anthropic (default), openai, fake (offline/tests)."""
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


def _cost(inp: int, out: int) -> float:
    s = settings()
    return inp / 1e6 * s.llm_input_usd_per_mtok + out / 1e6 * s.llm_output_usd_per_mtok


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
        return r.parsed_output, _cost(r.usage.input_tokens, r.usage.output_tokens)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=20), reraise=True)
    async def text(self, system, user, max_tokens=2000):
        r = await self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}]
        )
        out = "".join(b.text for b in r.content if b.type == "text")
        return out, _cost(r.usage.input_tokens, r.usage.output_tokens)


class OpenAILLM:
    def __init__(self, model: str):
        from openai import AsyncOpenAI

        self.model = model
        self.client = AsyncOpenAI(api_key=settings().openai_api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=20), reraise=True)
    async def structured(self, system, user, schema):
        r = await self.client.chat.completions.parse(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=schema,
        )
        return r.choices[0].message.parsed, _cost(r.usage.prompt_tokens, r.usage.completion_tokens)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=20), reraise=True)
    async def text(self, system, user, max_tokens=2000):
        r = await self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return r.choices[0].message.content or "", _cost(r.usage.prompt_tokens, r.usage.completion_tokens)


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
        )
        return e, 0.0

    async def text(self, system, user, max_tokens=2000):
        return "(fake LLM) " + user[:500], 0.0


def get_llm() -> LLM:
    s = settings()
    if s.llm_provider == "anthropic":
        return AnthropicLLM(s.llm_model)
    if s.llm_provider == "openai":
        return OpenAILLM(s.llm_model)
    return FakeLLM()
