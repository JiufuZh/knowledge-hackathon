"""Compare observations at the same scope and keep their original provenance."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from decimal import Decimal
from itertools import combinations
import re

from .schema import Bound, Claim, Decision, Disagreement, FactKey


AUTHORITY = {
    "rate_sheet": 5, "fee_schedule": 5, "branch": 5,
    "product": 4, "other": 2, "news": 1, "blog": 1, "calculator": 0,
}


def _value(value):
    # Equivalent formatting is common across the product and schedule pages.
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", value.casefold())
    text = re.sub(r"\d+(?:\.\d+)?", lambda m: format(Decimal(m[0]).normalize(), "f"), text)
    return re.sub(r"\s+", "", text.replace("–", "-").replace("—", "-"))


def _covers(outer: Bound, inner: Bound) -> bool:
    if (outer.axis, outer.unit) != (inner.axis, inner.unit):
        return False
    low = outer.low is None or (inner.low is not None and (
        outer.low < inner.low or outer.low == inner.low and (outer.low_inclusive or not inner.low_inclusive)))
    high = outer.high is None or (inner.high is not None and (
        outer.high > inner.high or outer.high == inner.high and (outer.high_inclusive or not inner.high_inclusive)))
    return low and high


def _applies(claim, scope, on):
    key, evidence = claim.key, claim.evidence
    if evidence.published_on and evidence.published_on > evidence.taken_on:
        return False
    for name in ("entity", "product", "audience", "measure"):
        requested, provided = getattr(scope, name), getattr(key, name)
        if requested and provided != requested:
            return False
    if evidence.effective_from and on < evidence.effective_from:
        return False
    if evidence.effective_until and on > evidence.effective_until:
        return False
    quals = dict(key.qualifiers)
    if any(k in quals and quals[k] != v for k, v in scope.qualifiers):
        return False
    bounds = {b.axis: b for b in key.bounds}
    return all(b.axis in bounds and _covers(bounds[b.axis], b) for b in scope.bounds)


def _authority(claim):
    kind = claim.evidence.source_class
    if re.search(r"\b(?:for illustrative purposes only|(?:sample|hypothetical) (?:payment|loan) example)\b",
                 claim.evidence.quote, re.I):
        return 0
    if kind == "rate_sheet" and claim.key.measure == "fee":
        return AUTHORITY["product"]
    return AUTHORITY.get(kind, AUTHORITY["other"])


def _order(c):
    e = c.evidence
    return (e.taken_on, e.url, e.headings, e.quote, c.value)


def supporting_sources(winner, candidates, on, canonical_rank=None):
    """Keep the deciding evidence and a directly corroborating product page."""
    sources = [winner.evidence]
    for c in sorted(candidates, key=canonical_rank or _order):
        if (c.evidence.source_class == "product" and c.evidence.url != winner.evidence.url
                and _key(c.key) == _key(winner.key) and _value(c.value) == _value(winner.value)
                and _applies(c, winner.key, on)):
            sources.append(c.evidence)
            break
    return tuple(sources)


def resolve(claims, requested_scope: FactKey, effective_on: str) -> Decision:
    applicable = sorted((c for c in claims if _applies(c, requested_scope, effective_on)), key=_order)
    if not applicable:
        return Decision("insufficient", reason="No applicable evidence covers this product, tier and date.")
    # A schedule may label nested limits as 'up to X'. At a requested point
    # a lower ceiling in the same table describes a more specific loan tier.
    requested_axes = {b.axis for b in requested_scope.bounds}
    requested_tags = dict(requested_scope.qualifiers)

    def rank(c):
        tags = sum(requested_tags.get(k) == v for k, v in c.key.qualifiers)
        return _authority(c), tags

    top_rank = max(map(rank, applicable))
    pool = [c for c in applicable if rank(c) == top_rank]
    if top_rank[0] == 0:
        return Decision("insufficient", competitors=tuple(pool), reason="A calculator example does not establish a published offer.")

    def narrower(a, b):
        a_bounds = {x.axis: x for x in a.key.bounds if x.axis in requested_axes}
        b_bounds = {x.axis: x for x in b.key.bounds if x.axis in requested_axes}
        return bool(a_bounds) and a_bounds != b_bounds and all(
            axis in b_bounds and _covers(b_bounds[axis], lim) for axis, lim in a_bounds.items())

    pool = [b for b in pool if not any(narrower(a, b) for a in pool)]
    # Only an explicitly applicable effective date can supersede a peer
    # schedule. Fetching an older statement again does not make it current.
    latest_effective = max((c.evidence.effective_from or "" for c in pool), default="")
    if latest_effective:
        pool = [c for c in pool if c.evidence.effective_from == latest_effective]
    if len({_value(c.value) for c in pool}) > 1:
        extra_scopes = {
            (c.key.product, c.key.audience, c.key.measure,
             tuple(sorted((k, v) for k, v in c.key.qualifiers if k not in requested_tags)),
             tuple(sorted((repr(b) for b in c.key.bounds if b.axis not in requested_axes))))
            for c in pool
        }
        if len(extra_scopes) > 1:
            return Decision("insufficient", competitors=tuple(pool), reason="The published values depend on a qualifier that was not specified.")
        return Decision("disputed", competitors=tuple(pool), reason="Equally authoritative, applicable sources disagree.")
    chosen = _value(pool[0].value)
    competing = tuple(c for c in applicable if _value(c.value) != chosen)
    reason = "The applicable source establishes this value."
    if competing:
        reason = "The directly applicable schedule or more specific published tier determines this value."
    return Decision("supported", tuple(pool), competing, reason)


def _format_number(x, unit):
    digits = f"{x:,.2f}".rstrip("0").rstrip(".") if unit == "dollars" else f"{x:g}"
    return ("$" if unit == "dollars" else "") + digits


def describe_bound(b):
    unit = " months" if b.unit == "months" else ""
    if b.low is not None and b.low == b.high:
        return _format_number(b.low, b.unit) + unit
    if b.low is None and b.high is not None:
        return ("up to " if b.high_inclusive else "below ") + _format_number(b.high, b.unit) + unit
    if b.high is None and b.low is not None:
        return ("at least " if b.low_inclusive else "over ") + _format_number(b.low, b.unit) + unit
    if b.low is None:
        return "any"
    left = "" if b.low_inclusive else "over "
    right = "" if b.high_inclusive else "under "
    return left + _format_number(b.low, b.unit) + " to " + right + _format_number(b.high, b.unit) + unit


def describe_key(key):
    qualifiers = [v for _, v in key.qualifiers]
    tiers = [f"{b.axis} {describe_bound(b)}" for b in key.bounds]
    return " ".join(filter(None, (key.audience, key.product, key.measure, *qualifiers, *tiers)))


def _key(key):
    return replace(key, qualifiers=tuple(sorted(key.qualifiers)), bounds=tuple(sorted(key.bounds, key=repr)))


def _representatives(claims):
    by_value = {}
    for c in sorted(claims, key=lambda c: (-_authority(c), _order(c))):
        by_value.setdefault(_value(c.value), c)
    return tuple(by_value.values())


def _intersection(a, b):
    if (a.axis, a.unit) != (b.axis, b.unit):
        return None
    lows = [x.low for x in (a, b) if x.low is not None]
    highs = [x.high for x in (a, b) if x.high is not None]
    lo, hi = max(lows, default=None), min(highs, default=None)
    include_low = all(x.low != lo or x.low_inclusive for x in (a, b))
    include_high = all(x.high != hi or x.high_inclusive for x in (a, b))
    if lo is not None and hi is not None and (lo > hi or lo == hi and not (include_low and include_high)):
        return None
    return Bound(a.axis, a.unit, lo, hi, include_low, include_high)


def _overlapping_groups(grouped):
    """Compare crossing intervals; nested schedule ceilings define separate tiers."""
    families = defaultdict(list)
    for key in grouped:
        if key.bounds:
            axes = tuple((b.axis, b.unit) for b in key.bounds)
            families[replace(key, bounds=()), axes].append(key)
    shared = defaultdict(list)
    for (base, _), keys in families.items():
        for left, right in combinations(keys, 2):
            bounds = tuple(_intersection(a, b) for a, b in zip(left.bounds, right.bounds))
            if None in bounds or bounds == left.bounds or bounds == right.bounds:
                continue
            shared[replace(base, bounds=bounds)].extend((*grouped[left], *grouped[right]))
    return shared


def discover_conflicts(history):
    records = {}
    first_seen = {}
    previous = {}
    for view in history.views:
        grouped = defaultdict(list)
        for claim in view.claims:
            grouped[_key(claim.key)].append(claim)
        crossing = _overlapping_groups(grouped)
        current = {}
        for key, claims in (*grouped.items(), *crossing.items()):
            decision = resolve(claims, key, view.taken_on)
            applicable = [c for c in claims if _applies(c, key, view.taken_on)]
            peers = _representatives(applicable) if any(_authority(c) for c in applicable) else ()
            winner = decision.winners[0] if decision.winners else None
            if len(peers) > 1:
                signature = ("disagreement", key, tuple(sorted(_value(c.value) for c in peers)),
                             _value(winner.value) if winner else None)
                first = first_seen.setdefault(signature, view.taken_on)
                observation = (f"in the {first} capture" if first == view.taken_on
                               else f"in captures first seen on {first} and last seen on {view.taken_on}")
                records[signature] = Disagreement(describe_key(key), tuple(c.value for c in peers),
                    tuple(c.evidence for c in peers), winner.value if winner else None,
                    f"Sources disagree {observation}. {decision.reason}")
            if winner and key not in crossing:
                current[key] = winner
                old = previous.get(key)
                if old and _value(old.value) != _value(winner.value):
                    signature = ("change", key, old.evidence.snapshot_id, winner.evidence.snapshot_id)
                    records[signature] = Disagreement(describe_key(key), (old.value, winner.value),
                        (old.evidence, winner.evidence), winner.value,
                        f"The published value changed between the {old.evidence.taken_on} and {view.taken_on} captures.")
        # Absence, or an unresolved peer dispute, breaks a chain of comparable observations.
        previous = current
    return tuple(sorted(records.values(), key=lambda d: (d.topic, d.sources[0].taken_on, d.reason, d.values)))
