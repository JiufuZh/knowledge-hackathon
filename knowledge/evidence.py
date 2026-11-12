"""Atomic, dated views of complete website captures."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from hashlib import sha256
from threading import RLock

from .extract import PARSER_VERSION, extract_page
from .schema import Claim, Evidence, Inventory, PageRecord


class History:
    def __init__(self) -> None:
        self._views: tuple[Inventory, ...] = ()
        self._cache: dict[tuple, tuple[tuple[Claim, ...], tuple[Evidence, ...]]] = {}
        self._lock = RLock()

    @property
    def views(self) -> tuple[Inventory, ...]:
        return self._views

    def add(self, snapshot) -> None:
        with self._lock:
            date.fromisoformat(snapshot.taken_on)
            pages = tuple(PageRecord(p.url, p.title, p.markdown, p.fetched_at)
                          for p in sorted(snapshot.pages, key=lambda p: p.url))
            previous = next((v for v in self._views if v.snapshot_id == snapshot.snapshot_id), None)
            if previous:
                if (previous.taken_on, previous.pages) != (snapshot.taken_on, pages):
                    raise ValueError("Snapshot ID already belongs to different content")
                return
            if len({p.url for p in pages}) != len(pages):
                raise ValueError("A complete inventory must have one record per URL")

            claims, passages = [], []
            next_cache = {}
            for page in pages:
                digest = sha256(page.markdown.encode("utf-8")).digest()
                key = (PARSER_VERSION, page.url, page.title, digest)
                cached = self._cache.get(key)
                if cached is None:
                    parsed = extract_page(page, snapshot.snapshot_id, snapshot.taken_on)
                else:
                    old_claims, old_passages = cached
                    versions = {id(e): replace(e, snapshot_id=snapshot.snapshot_id,
                                               taken_on=snapshot.taken_on, fetched_at=page.fetched_at)
                                for e in old_passages}
                    parsed = (tuple(replace(c, evidence=versions[id(c.evidence)]) for c in old_claims),
                              tuple(versions[id(e)] for e in old_passages))
                next_cache[key] = parsed
                claims.extend(parsed[0])
                passages.extend(parsed[1])
            view = Inventory(snapshot.snapshot_id, snapshot.taken_on, pages, tuple(claims), tuple(passages))
            self._views = tuple(sorted((*self._views, view), key=lambda v: (v.taken_on, v.snapshot_id)))
            self._cache = next_cache

    def at(self, cutoff: str | None = None) -> Inventory | None:
        views = self._views
        if cutoff is None:
            return views[-1] if views else None
        try:
            cutoff = date.fromisoformat(cutoff).isoformat()
        except (ValueError, TypeError):
            return None
        return next((view for view in reversed(views) if view.taken_on <= cutoff), None)

    def between(self, start: str, end: str) -> tuple[Inventory, ...]:
        try:
            first, last = date.fromisoformat(start).isoformat(), date.fromisoformat(end).isoformat()
        except (ValueError, TypeError):
            return ()
        return tuple(view for view in self._views if first <= view.taken_on <= last)
