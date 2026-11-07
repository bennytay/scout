from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

TOPICS = (
    "manipulation", "locomotion", "humanoids", "vla-foundation-models", "sim2real",
    "slam-spatial-mapping", "perception", "hardware", "datasets-benchmarks", "multi-agent", "other",
)
TopicSlug = Literal[
    "manipulation", "locomotion", "humanoids", "vla-foundation-models", "sim2real",
    "slam-spatial-mapping", "perception", "hardware", "datasets-benchmarks", "multi-agent", "other",
]


class ItemType(StrEnum):
    paper = "paper"
    repo = "repo"
    post = "post"
    article = "article"
    model = "model"
    dataset = "dataset"
    video = "video"


class Item(BaseModel):
    """What every connector returns. Only url/type/title/source are required."""

    url: str
    type: ItemType
    title: str
    source: str
    summary: str | None = None          # source-provided abstract/description (LLM summary replaces it)
    full_text: str | None = None
    published_at: datetime | None = None
    source_ref: str | None = None
    submitted_by: str | None = None
    arxiv_id: str | None = None
    doi: str | None = None
    authors: list[str] = Field(default_factory=list)
    orgs: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    outlinks: list[str] = Field(default_factory=list)   # URLs mentioned in the item (for linking)
    author_handles: dict[str, str] = Field(default_factory=dict)  # e.g. {"x": "DrJimFan"}
    media: dict[str, str] = Field(default_factory=dict)  # {"image": post photo/video thumbnail, "avatar": poster}


class Entities(BaseModel):
    robots: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    benchmarks: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)


class Enrichment(BaseModel):
    """Structured output of the enrichment LLM call."""

    summary: str = Field(description="2-3 sentence plain-English summary: what it is and what is new.")
    title_en: str = Field("", description="Only if the item's title is not in English: an English headline, "
                                          "<= 14 words. Otherwise empty.")
    topics: list[TopicSlug] = Field(description="1-3 topics from the fixed taxonomy, most relevant first.")
    authors: list[str] = Field(description="Person authors, full names. Empty if unknown.")
    orgs: list[str] = Field(description="Organisations/labs/companies involved. Canonical names.")
    entities: Entities
    importance: float = Field(0.5, description="0-1 how significant this is for robotics in general, per the rubric.")
    auki_relevance: float = Field(description="0-1 relevance to Auki Labs, per the rubric.")
    auki_relevance_reason: str = Field(description="One sentence: why it matters (or not) to Auki.")
    signal: Literal["news", "discussion", "promo", "off_topic", "noise"] = Field(
        "news", description="What kind of item this is, per the signal rules. Decides whether an X post is kept.")
