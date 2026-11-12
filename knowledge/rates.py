"""Interpret financial product questions against the products in a selected inventory."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from html import unescape
import re

from .extract import member_condition
from .resolve import describe_bound, resolve, supporting_sources
from .schema import Bound, FactKey, Reply


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "seventeen": 17, "eighteen": 18, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_WORD_NUMBER = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")(?:[- ](one|two|three|four|five|six|seven|eight|nine))?(?=[ -]+(?:month|mo\b|year|yr\b))")
_RATE_MEASURES = {"apy", "apr", "interest rate", "dividend rate", "fee", "points", "minimum to open", "minimum to earn"}
_CASH = re.compile(r"(?:\$\s*(\d[\d,]*(?:\.\d+)?)(?:\s*(k|million|thousand)\b)?|"
                   r"\b(\d[\d,]*(?:\.\d+)?)\s*(k|million|thousand)?\s*(?:dollars?|usd)\b)")
_EXPLAIN = re.compile(r"\b(?:disagree\w*|contradict\w*|conflict\w*)\b|\b(?:compare|different)\b.{0,45}\b(?:sources?|pages?|schedules?)\b")
_MEASURE_TERMS = {
    "apy": r"annual percentage yield|apys?",
    "apr": r"annual percentage rate|aprs?",
    "dividend rate": r"dividends?(?: rates?)?",
}


def _amount(match):
    return float((match[1] or match[3]).replace(",", "")) * {
        "k": 1000, "thousand": 1000, "million": 1000000}.get(match[2] or match[4], 1)


def _normalize(question):
    q = question.casefold().replace("’", "'").replace("–", "-").replace("—", "-")
    q = _WORD_NUMBER.sub(lambda m: str(_NUMBER_WORDS[m[1]] + _NUMBER_WORDS.get(m[2], 0)), q)
    q = re.sub(r"\b(?:cds?|share certificates?|certificates of deposit)\b", "certificate", q)
    q = re.sub(r"\b(?:automobile|car|motorcycle|vehicle) (?:financing|loan)s?\b", "auto loan", q)
    return q


def _point(axis, unit, value):
    return Bound(axis, unit, value, value)


def _request_bounds(q, loan):
    bounds = []
    term = re.search(r"\b(\d{1,3})[ -]*(mo(?:nth)?s?|yr?s?|years?)\b", q)
    if term:
        months = int(term[1]) * (12 if term[2].startswith("y") else 1)
        bounds.append(_point("term", "months", months))
    year = re.search(r"\b(?:19|20)\d{2}\b", q)
    if year and "auto" in loan:
        # Capture dates and an automobile's model year are separate qualifiers.
        direct = re.search(r"\b((?:19|20)\d{2})[ -]*(?:model|vehicle|car|truck|auto|sedan|suv|motorcycle)", q)
        if direct or not re.search(r"\b(as of|effective|posted)\b", q):
            bounds.append(_point("model year", "years", int(direct[1] if direct else year[0])))
    money = list(_CASH.finditer(q))
    if money:
        axis = "amount" if loan and loan != "certificate" else "balance"
        value = _amount(money[0])
        before = q[:money[0].start()].rstrip()
        if len(money) > 1 and re.search(r"(?:between|\bto\b|through|\$[\d,.]+\s*-)", q):
            other = _amount(money[1])
            bounds.append(Bound(axis, "dollars", min(value, other), max(value, other)))
        elif re.search(r"\b(?:above|over|more than|at least)$", before):
            bounds.append(Bound(axis, "dollars", value, low_inclusive=before.endswith("at least")))
        elif re.search(r"\b(?:below|under|less than|up to|at most)$", before):
            bounds.append(Bound(axis, "dollars", None, value, high_inclusive=before.endswith(("up to", "at most"))))
        else:
            bounds.append(_point(axis, "dollars", value))
    return tuple(bounds)


def _family(q):
    if re.search(r"\b(mortgages?|home loans?|housing loans?|arms?)\b", q):
        return "mortgage"
    if re.search(r"\b(auto|vehicle|car|motorcycle)\b", q):
        return "auto loan"
    if re.search(r"\b(iras?|individual retirement)\b", q):
        return "ira"
    if re.search(r"\b(certificates?|term deposit)\b", q):
        return "certificate"
    if re.search(r"\b(visa|credit cards?)\b", q):
        return "card"
    for family in ("checking", "savings", "money market", "loan"):
        if family in q:
            return family
    return ""


def _product_match(q, products, family):
    clean = re.sub(r"[^a-z0-9]+", " ", q).strip()
    # Prefer a named account. A broad question can legitimately cover a family.
    if family in {"mortgage", "auto loan", "certificate", "ira"}:
        return {p for p in products if p == family}
    named = {p for p in products if re.search(r"\b" + re.escape(p) + r"s?\b", clean)}
    if named:
        longest = max(len(p.split()) for p in named)
        return {p for p in named if len(p.split()) == longest}
    if family == "card":
        match = {p for p in products if "visa" in p or "credit card" in p}
        descriptions = set(clean.split()) & {"rewards", "platinum"}
        return {p for p in match if descriptions <= set(p.split())}
    if family:
        family_matches = {p for p in products if family in p.split() or family in p}
        # A named product such as a construction loan cannot inherit a
        # published rate from a different loan. Generic class names are allowed.
        before = re.search(r"\b([a-z]+)\s+" + re.escape(family) + r"s?\b", clean)
        fillers = {"a", "an", "the", "any", "your", "our", "my", "their", "for", "on", "all",
                   "of", "these", "those", "with", "and", "current", "standard", "some"}
        if before and before[1] not in fillers and not any(before[1] in p.split() for p in family_matches):
            return set()
        return family_matches
    return set()


def _display_name(key):
    product = re.sub(r"(\d+)(St|Nd|Rd|Th)\b", lambda m: m[1] + m[2].lower(), key.product.title())
    if key.audience == "business" and "business" not in key.product:
        product = "Business " + product
    qualifiers = [v for k, v in key.qualifiers if not (k == "type" and v == "standard")]
    tiers = [describe_bound(b) + (" balance" if b.axis == "balance" else
             " loan" if b.axis == "amount" else " model year" if b.axis == "model year" else "")
             for b in key.bounds]
    labels = [*qualifiers, *tiers]
    return product + (" (" + ", ".join(labels) + ")" if labels else "")


def _measure(q, family, available):
    if re.search(r"\bapy\b|annual percentage yield", q):
        return "apy"
    if re.search(r"\bapr\b|annual percentage rate", q):
        return "apr"
    if re.search(r"\bdividends?\b", q):
        return "dividend rate"
    if "minimum" in q or "minimum deposit" in q:
        if "open" in q:
            return "minimum to open"
        if "earn" in q or "deposit" in q:
            return "minimum to earn"
    if "points" in q:
        return "points"
    if family in {"checking", "savings", "certificate", "ira", "money market"} and "apy" in available:
        return "apy"
    return next((m for m in ("interest rate", "apr", "apy", "dividend rate") if m in available), "")


def _tag_filters(q, family, candidates):
    requested = {}
    if family == "mortgage":
        requested["purpose"] = "refinance" if "refinanc" in q else "purchase"
        if re.search(r"\barm\b|adjustable", q):
            # An ARM reset period is material even when another ARM is present.
            match = re.search(r"\b\d+\s*/\s*\d+\b", q)
            requested["program"] = match[0].replace(" ", "") if match else "adjustable"
        elif program := re.search(r"\b(fha|va|usda|construction|jumbo|balloon|interest.only)\b", q):
            requested["program"] = program[0]
        elif any(k == "program" and "conventional" in v for c in candidates for k, v in c.key.qualifiers):
            requested["program"] = "fixed conventional"
    if family == "card":
        requested["type"] = "introductory balance transfer" if re.search(r"\bintro|balance transfer", q) else "standard"
    if family == "certificate":
        if "jumbo" in q:
            requested["type"] = "jumbo"
        elif "regular" in q or "standard" in q:
            requested["type"] = "regular"
        elif "special" in q:
            requested["type"] = "special"
    for plan in ("roth", "traditional"):
        if plan in q:
            requested["plan"] = plan
    noun = r"(?:members?|customers?|cardholders?)\b"
    new = bool(re.search(r"\bnew[ -]+" + noun, q))
    existing = bool(re.search(r"\b(?:existing|current|longtime|long-standing)[ -]+" + noun
                              + r"|\balready (?:a |an? existing )?" + noun, q))
    if re.search(r"\b(?:not|no longer) (?:a )?new " + noun, q):
        new, existing = False, True
    if new != existing:
        requested["eligibility"] = "new members" if new else "existing members"
    return requested


def _find_fee(q, claims):
    words = {w.rstrip("s") for w in re.findall(r"[a-z]+", q)} - {"card", "a", "the", "fee", "for", "of", "to", "how", "much", "is", "what", "replacement"}
    if not words:
        return []
    scored = []
    for c in claims:
        product_words = {w.rstrip("s") for w in c.key.product.split()} - {"fee", "for", "of", "a", "the"}
        overlap = len(words & product_words)
        if overlap and (overlap >= min(2, len(product_words)) or "overdraft" in (words & product_words)):
            scored.append((overlap / max(1, len(product_words)), c))
    best = max((v for v, _ in scored), default=0)
    return [c for score, c in scored if score == best]


_POLICY = re.compile(r"\b(?:if|unless|waiv\w*|exempt\w*|maximum|minimum|free for|limited to)\b", re.I)
_WAIVER = re.compile(r"\b(?:no fee|no charge|not (?:be )?charged|waived|free)\b[^.;|]{0,160}?"
                     r"\b(below|under|less than|at most|up to)\s*\$([\d,]+(?:\.\d+)?)", re.I)


def _fee_policy(evidence):
    quote = unescape(unescape(evidence.quote)).replace("*", "")
    return " ".join(s.strip() for s in quote.strip("|").split("|") if s.strip())


def _explain_values(decision):
    observations = (*decision.winners[:1], *decision.competitors)
    statements = []
    proof = []
    seen = set()
    for c in observations:
        source = c.evidence.source_class.replace("_", " ")
        if source == "other":
            source = f'page “{c.evidence.title}”'
        if (c.value, source) not in seen:
            statements.append(f"The {source} lists {c.value}.")
            proof.append(c.evidence)
            seen.add((c.value, source))
    return f"{' '.join(statements)} {decision.reason}", tuple(proof)


def answer_rates(inventory, question, effective_on):
    q = _normalize(question)
    terms = "|".join(_MEASURE_TERMS.values())
    q = re.sub(r"\b(?:not|instead of|rather than)\s+(?:the\s+)?(?:" + terms + r")\b", "", q)
    measures = [name for name, terms in _MEASURE_TERMS.items() if re.search(r"\b(?:" + terms + r")\b", q)]
    if len(measures) <= 1:
        return _answer_measure(inventory, q, effective_on, next(iter(measures), None))
    replies = [_answer_measure(inventory, q, effective_on, measure) for measure in measures]
    if any(r is None for r in replies):
        return None
    return Reply(" ".join(r.text for r in replies), tuple(dict.fromkeys(e for r in replies for e in r.sources)),
                 all(r.confident for r in replies), " ".join(dict.fromkeys(r.conflict_note for r in replies if r.conflict_note)) or None)


def _answer_measure(inventory, q, effective_on, explicit_measure):
    if re.search(r"\b(?:links?|url|website|where (?:can|do|should) i (?:find|see|view))\b", q):
        return None
    fee = bool(re.search(r"\b(fees?|cost|charge|price|how much)\b", q)) and not re.search(r"\b(rates?|apr|apy)\b", q)
    rate = bool(re.search(r"\b(rates?|aprs?|apys?|interest|dividend|yield|earn|pay|points|minimum)\b", q))
    if not (fee or rate):
        return None
    all_claims = [c for c in inventory.claims if c.key.measure in _RATE_MEASURES]
    family = _family(q)
    if fee and ("fee" in q or not family or family == "card"):
        candidates = _find_fee(q, [c for c in all_claims if c.key.measure == "fee"])
        if not candidates:
            return None
        metric = "fee"
    else:
        if not rate:
            return None
        products = {c.key.product for c in all_claims if c.key.measure != "fee"}
        stripped = q
        for entity in {c.key.entity.split(".")[0] for c in all_claims}:
            stripped = re.sub(r"\b" + re.escape(entity) + r"(?:'s)?\b", " ", stripped)
        selected = _product_match(stripped, products, family)
        if not selected:
            if family:
                return Reply("I don't know. I could not confirm a published rate for that product.", confident=False)
            return None
        candidates = [c for c in all_claims if c.key.product in selected]
        if family == "loan" and len(selected) > 1:
            return Reply("Which loan product do you mean? The published terms depend on the product.", confident=False)
        metric = explicit_measure or _measure(q, family, {c.key.measure for c in candidates})
    candidates = [c for c in candidates if c.key.measure == metric]
    if "nonmember" in q or "non-member" in q:
        candidates = [c for c in candidates if c.key.audience == "nonmember"]
    elif "business" in q:
        candidates = [c for c in candidates if c.key.audience == "business"]
    elif "personal" in q or family != "card" or re.search(r"\b(?:platinum|rewards)\b", q):
        candidates = [c for c in candidates if c.key.audience not in {"business", "nonmember"}]
    filters = _tag_filters(q, family, candidates)
    for tag, value in filters.items():
        # A card may state its APR under a product name without an explicit
        # 'standard' tag. Treat only untagged ordinary rates as standard.
        def matches(c):
            actual = dict(c.key.qualifiers).get(tag)
            if actual is None:
                return tag == "eligibility" or (tag == "type" and value == "standard") or (tag == "purpose" and value == "purchase")
            return value in actual
        candidates = [c for c in candidates if matches(c)]
    request_bounds = () if metric == "fee" else _request_bounds(q, family if family in {"mortgage", "auto loan", "loan"} else "")
    axes = {b.axis for b in request_bounds}
    by_scope = defaultdict(list)
    for c in candidates:
        # Include the point/range in the lookup. Retain the original published
        # tier on the winning claim for the member-facing explanation.
        other_bounds = tuple(b for b in c.key.bounds if b.axis not in axes)
        tags = dict(c.key.qualifiers)
        if "eligibility" in filters:
            tags["eligibility"] = filters["eligibility"]
        scope = replace(c.key, qualifiers=tuple(sorted(tags.items())),
                        bounds=tuple(sorted((*other_bounds, *request_bounds), key=repr)))
        by_scope[scope].append(c)
    pages = {page.url: page.markdown for page in inventory.pages}
    link_counts = {}

    def canonical_rank(c):
        # Captures include aliases that serve identical content. Footer and
        # section links in that content usually identify the maintained URL.
        url = c.evidence.url
        if url not in link_counts:
            link_counts[url] = pages.get(url, "").count("](" + url.rstrip("/") + "#")
        return (-link_counts[url], url, c.evidence.quote)

    winners, unresolved, notes, sources, explanations = [], [], [], {}, []
    for scope, group in by_scope.items():
        decision = resolve(group, scope, effective_on)
        status = filters.get("eligibility")
        if status:
            # A general schedule remains a fallback if the more specific offer has expired
            # or does not cover the member's balance. An applicable offer may live on
            # its own official product page even when the main schedule lists only base rates.
            offers = [c for c in group if dict(c.key.qualifiers).get("eligibility") == status
                      and c.evidence.source_class in {"rate_sheet", "product"}]
            specific = resolve(offers, scope, effective_on)
            if specific.status in {"supported", "disputed"}:
                decision = specific
        if decision.status == "supported":
            claim = decision.winners[0]
            if metric == "fee":
                claim = max(decision.winners, key=lambda c: bool(_POLICY.search(c.evidence.quote)))
            winners.append(claim)
            sources[claim] = supporting_sources(claim, group, effective_on, canonical_rank)
            membership = dict(claim.key.qualifiers).get("eligibility")
            if membership:
                condition = next((s for s in reversed(claim.evidence.headings)
                                  if member_condition(s) == membership and s in pages.get(claim.evidence.url, "")), None)
                if condition:
                    sources[claim] += (replace(claim.evidence, quote=condition),)
            if decision.competitors:
                notes.append(decision.reason)
                if _EXPLAIN.search(q):
                    explanation, proof = _explain_values(decision)
                    explanations.append(explanation)
                    sources[claim] += proof
        elif decision.status == "disputed":
            unresolved.extend(c.evidence for c in decision.competitors)
            if _EXPLAIN.search(q):
                explanations.append(_explain_values(decision)[0])
    if unresolved:
        return Reply("I can't confirm the rate because the applicable published sources disagree. " + " ".join(explanations),
                     tuple(dict.fromkeys(unresolved)), False, "Equally authoritative sources disagree.")
    if not winners:
        return Reply("I don't know. I couldn't confirm a published value for those terms.", confident=False)
    if re.search(r"\b(highest|maximum|best|top)\b", q) and metric in {"apr", "apy", "dividend rate", "interest rate"}:
        def numeric(c):
            return max((float(v) for v in re.findall(r"(\d+(?:\.\d+)?)\s*%", c.value)), default=0)
        highest = max(map(numeric, winners))
        winners = [c for c in winners if numeric(c) == highest]
    percent = re.search(r"\b(\d+(?:\.\d+)?)\s*%", q)
    lead, distinction, context_claims = "", "", []
    if percent and re.search(r"\b(any|pay|offer|earn)\b", q):
        target = float(percent[1])
        matching = [c for c in winners if target in [float(v) for v in re.findall(r"(\d+(?:\.\d+)?)\s*%", c.value)]]
        if matching:
            # Distinguish a special-purpose product from the ordinary share
            # account when a member asks whether any deposit tier pays a rate.
            if family == "savings" and "share savings" not in q:
                ordinary = [c for c in winners if c.key.product in {"share savings", "regular savings", "basic savings", "savings"}]
                if ordinary and not any(c in matching for c in ordinary):
                    top = max(ordinary, key=lambda c: float(re.search(r"[\d.]+", c.value)[0]))
                    distinction = f" {_display_name(top.key)} tops out at {top.value} {metric.upper()}."
                    context_claims = [top]
            winners = matching
            lead = "Yes. "
        else:
            lead = "I found the following published tiers. "
    winners.sort(key=lambda c: (c.key.audience, c.key.product, tuple((b.axis, b.low if b.low is not None else -1, b.high if b.high is not None else float('inf')) for b in c.key.bounds), c.key.qualifiers))
    label = metric.upper() if metric in {"apr", "apy"} else metric
    rows = []
    for c in winners:
        if metric == "fee":
            policy = _fee_policy(c.evidence)
            conditional = bool(_POLICY.search(policy))
            asked_amount = _CASH.search(q)
            if asked_amount or re.search(r"\b(?:waiv\w*|exempt\w*|free)\b", q):
                threshold = _WAIVER.search(policy)
                if asked_amount and threshold:
                    ceiling = float(threshold[2].replace(",", ""))
                    amount = _amount(asked_amount)
                    if amount < ceiling or (amount == ceiling and threshold[1].lower() in {"up to", "at most"}):
                        rows.append("No fee applies to that transaction under the published threshold. " + policy)
                        continue
                details = policy if conditional else f"The published price is {c.value}."
                return Reply("I can't confirm the charge for this transaction. " + details,
                             sources[c], confident=False)
            if conditional:
                rows.append(policy)
                continue
        modifier = "as low as " if "as low as" in " ".join(c.evidence.headings).lower() else ""
        rows.append(f"{_display_name(c.key)}: {modifier}{c.value} {label}.")
    clarify_membership = "eligibility" not in filters and any("eligibility" in dict(c.key.qualifiers) for c in winners)
    response = lead + " ".join([*rows, *explanations]) + distinction
    if clarify_membership:
        response += " Are you a new or existing member? That determines which published offer applies."
    return Reply(response, tuple(dict.fromkeys(e for c in [*winners, *context_claims] for e in sources[c])),
                 confident=not clarify_membership, conflict_note=" ".join(dict.fromkeys(notes)) or None)
