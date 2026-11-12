"""Shared records used by the local engine and the organizer adapter."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bound:
    axis: str
    unit: str
    low: float | None = None
    high: float | None = None
    low_inclusive: bool = True
    high_inclusive: bool = True

    def contains(self, value: float) -> bool:
        lower = self.low is None or value > self.low or (value == self.low and self.low_inclusive)
        upper = self.high is None or value < self.high or (value == self.high and self.high_inclusive)
        return lower and upper


@dataclass(frozen=True)
class FactKey:
    entity: str
    product: str
    audience: str
    measure: str
    qualifiers: tuple[tuple[str, str], ...] = ()
    bounds: tuple[Bound, ...] = ()


@dataclass(frozen=True)
class Evidence:
    snapshot_id: str
    taken_on: str
    url: str
    title: str
    source_class: str
    headings: tuple[str, ...]
    quote: str
    fetched_at: str = ""
    published_on: str | None = None
    effective_from: str | None = None
    effective_until: str | None = None


@dataclass(frozen=True)
class Claim:
    key: FactKey
    value: str
    evidence: Evidence


@dataclass(frozen=True)
class PageRecord:
    url: str
    title: str
    markdown: str
    fetched_at: str


@dataclass(frozen=True)
class Inventory:
    snapshot_id: str
    taken_on: str
    pages: tuple[PageRecord, ...]
    claims: tuple[Claim, ...]
    passages: tuple[Evidence, ...]


@dataclass(frozen=True)
class Decision:
    status: str
    winners: tuple[Claim, ...] = ()
    competitors: tuple[Claim, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class Reply:
    text: str
    sources: tuple[Evidence, ...] = ()
    confident: bool = True
    conflict_note: str | None = None


@dataclass(frozen=True)
class Disagreement:
    topic: str
    values: tuple[str, ...]
    sources: tuple[Evidence, ...]
    resolution: str | None
    reason: str
