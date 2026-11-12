"""Retrieve verbatim spans and dated references from the selected capture."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from threading import RLock
from urllib.parse import urljoin, urlsplit
from weakref import ref

from .schema import Evidence, Inventory, PageRecord, Reply

LINK = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^\s)]+)\)")
MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE = re.compile(r"\b(?:" + MONTH + r"\.?\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})\b", re.I)


def parsed_date(value: str) -> str:
    value = re.sub(r"\bSept\b", "Sep", value, flags=re.I).replace(".", "").replace(",", "")
    for fmt in ("%B %d %Y", "%b %d %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def plain(value: str) -> str:
    value = LINK.sub(r"\1", value)
    return re.sub(r"\s+", " ", re.sub(r"[\*_#]", "", value)).strip(" -\t\n")


def refuse(reason="I couldn't verify that detail in the selected website capture.", sources=()) -> Reply:
    return Reply(reason, tuple(sources), False)


@dataclass(frozen=True)
class Document:
    page: PageRecord
    body: str
    path: str
    published: str
    archive: bool

    def evidence(self, view: Inventory, quote: str) -> Evidence:
        return Evidence(view.snapshot_id, view.taken_on, self.page.url, self.page.title,
                        "news" if self.archive else "product", (), quote, self.page.fetched_at,
                        published_on=self.published or None)


class Site:
    def __init__(self, view: Inventory):
        docs = []
        for page in sorted(view.pages, key=lambda p: p.url):
            path = urlsplit(page.url).path.lower().rstrip("/")
            if "/tag/" in path or "/author/" in path:
                continue
            body = re.split(r"(?im)^#{1,4}\s+(?:Handpicked for You|Related (?:Posts|Articles)|You May Also Like)\s*$", page.markdown, maxsplit=1)[0]
            archive = bool(re.search(r"(?:^|/)(?:news(?:room)?|blog|press|20\d\d)(?:/|$)", path))
            # Unlike a footer copyright year, a publication dateline belongs to the article.
            stamp = re.search(r"(?im)^(?:Published(?: on)?[ :]+)?(" + DATE.pattern + r")\s*$", body[:1000])
            published = parsed_date(stamp[1]) if stamp else ""
            docs.append(Document(page, body, path, published, archive))
        self.docs = tuple(docs)

    def visible(self, on: str):
        return (d for d in self.docs if not d.published or d.published <= on)


_sites = {}
_lock = RLock()


def site_for(view: Inventory) -> Site:
    # Inventories are immutable, but hashing one would visit every page and claim.
    key = id(view)
    with _lock:
        entry = _sites.get(key)
        if entry and entry[0]() is view:
            return entry[1]
        dead = [k for k, (owner, _) in _sites.items() if owner() is None]
        for k in dead:
            del _sites[k]
        site = Site(view)
        _sites[key] = (ref(view), site)
        return site


def blocks(body: str):
    return (m.group().strip() for m in re.finditer(r"[^\n]+", body)
            if not m.group().lstrip().startswith(("![", "[![", "|", "Remaining data")))


def literal_link(doc: Document, match) -> str:
    target = urljoin(doc.page.url, match[2])
    return target if urlsplit(target).scheme in ("http", "https") else ""


def narrative(site, on, pattern, *, topic=None, editorial=False, rank=None):
    """Pick the newest attributed statement within an eligible class of sources."""
    constraint = re.compile(pattern, re.I)
    topic_re = re.compile(topic, re.I) if topic else None
    matches = []
    for d in site.visible(on):
        if topic_re and not topic_re.search(d.page.title + " " + d.body[:500]):
            continue
        if not constraint.search(d.body):
            continue
        for line in blocks(d.body):
            if not constraint.search(line) or line.startswith(("#", "[")) or len(line) > 2500:
                continue
            score = rank(d, line) if rank else 0
            priority = (score, d.archive == editorial, d.published)
            matches.append((priority, d, line))
    matches.sort(key=lambda row: row[0], reverse=True)
    return [(doc, line) for _, doc, line in matches]


def cited(view, doc, quote, text=None):
    return Reply(plain(quote) if text is None else text, (doc.evidence(view, quote),))
