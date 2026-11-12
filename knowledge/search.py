"""Evidence-first lexical retrieval for topics outside the structured readers."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from functools import lru_cache
from math import log
import re
from threading import RLock

from .schema import Reply


_WORD = re.compile(r"\b[a-z0-9]+(?:['’][a-z]+)?\b", re.I)
_IGNORED = set("""
a an the is are was were do does did what which who whom when where how can could
may would will must should me my your you our ours their them us i we they it its
to for from with that this those these of on in into out by at and or be as if
get give tell know please about information detail details find want need some
credit union website today now currently available any offer offers have has much many
""".split())
_ALIAS = {"charging": "charge", "charged": "charge", "cost": "fee", "costs": "fee",
          "replace": "replacement", "replacing": "replacement", "replaced": "replacement",
          "updating": "update", "updated": "update",
          "qualify": "eligible", "qualifies": "eligible", "eligibility": "eligible",
          "enroll": "join", "enrolling": "join", "enrollment": "join",
          "maximum": "limit", "limits": "limit", "charges": "charge",
          "locations": "location", "documents": "document", "identification": "id"}
_FORMATTING = re.compile(r"(?<!!)\[([^\]]+)\]\([^)]+\)")


@lru_cache(maxsize=8000)
def _normalize(word):
    if word in _ALIAS:
        return _ALIAS[word]
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _tokens(text):
    return {_normalize(word) for word in _WORD.findall(text.casefold()) if word not in _IGNORED}


class _Index:
    def __init__(self, passages):
        self.rows = []
        self.postings = defaultdict(list)
        for proof in passages:
            line = proof.quote.strip()
            if not 18 <= len(line) <= 1800 or line.startswith(("#", "|", "![", "[![")):
                continue
            visible = _FORMATTING.sub(r"\1", line)
            words = _tokens(visible)
            if not words:
                continue
            context = _tokens(" ".join((proof.title, *proof.headings)))
            idx = len(self.rows)
            self.rows.append((proof, words, context))
            for word in words | context:
                self.postings[word].append(idx)

    def candidates(self, words):
        n = len(self.rows)
        frequency = {word: len(self.postings.get(word, ())) for word in words}
        weights = {w: min(8, 1 + log((n + 1) / (1 + frequency[w]))) for w in words}
        # Visit the rarest available terms first; boilerplate terms can match almost every page.
        anchors = sorted((w for w in words if frequency[w]), key=frequency.get)[:3]
        indices = {i for term in anchors for i in self.postings[term]}
        return weights, indices


# The caller owns inventories. Keeping one recent index makes it cheap to switch to
# a historical view without retaining a second full copy of every historical index.
_cached = None
_lock = RLock()


def _index(view):
    global _cached
    with _lock:
        if _cached is None or _cached[0] is not view:
            _cached = (view, _Index(view.passages))
        return _cached[1]


def search_passages(inventory, question, effective_on):
    refusal = Reply("I couldn't verify that detail in the selected website capture.", confident=False)
    terms = _tokens(question)
    if not terms:
        return refusal
    index = _index(inventory)
    weights, indices = index.candidates(terms)
    total = sum(weights.values())
    requests_count = bool(re.search(r"\bhow (much|many)\b", question, re.I))
    best = None
    best_rank = ()
    seen = set()
    for i in indices:
        proof, words, context = index.rows[i]
        if proof.published_on and proof.published_on > effective_on:
            continue
        if proof.effective_from and proof.effective_from > effective_on:
            continue
        if proof.effective_until and proof.effective_until < effective_on:
            continue
        if (proof.url, proof.quote) in seen:
            continue
        seen.add((proof.url, proof.quote))
        direct = terms & words
        coverage = sum(weights[w] for w in terms & (words | context)) / total
        direct_fraction = sum(weights[w] for w in direct) / total
        if coverage < .86 or direct_fraction < .52 or len(direct) < min(2, len(terms)):
            continue
        if requests_count and not re.search(r"\d", proof.quote):
            continue
        if len(terms) == 1 and (not terms <= context or len(proof.quote) > 420):
            continue
        # A headline can establish the subject, but cannot supply every predicate.
        rank = (round(coverage, 2), proof.source_class not in {"news", "blog", "calculator"},
                round(direct_fraction, 2), len(terms & context), -len(proof.quote))
        if rank > best_rank or (rank == best_rank and (proof.url, proof.quote) < (best.url, best.quote)):
            best, best_rank = proof, rank
    if best is None:
        return refusal
    # Preserve full sentences and the exact contiguous evidence used to answer.
    quote = best.quote.strip()
    if len(quote) > 500:
        segments = [m.group().strip() for m in re.finditer(r"[^.!?\n]+(?:[.!?](?=\s|$)|$)", quote)]
        viable = [s for s in segments if 18 <= len(s) <= 500]
        if not viable:
            return refusal
        quote = max(viable, key=lambda s: sum(weights[w] for w in terms & _tokens(s)))
        if sum(weights[w] for w in terms & _tokens(quote)) / total < .52:
            return refusal
    text = _FORMATTING.sub(r"\1", quote).replace("**", "")
    return Reply(text, (replace(best, quote=quote),))
