"""Bind institution names and routing-number labels to the evidence that owns them."""
import re
from urllib.parse import urlsplit


def organization_names(page_url, title=""):
    host = (urlsplit(page_url).hostname or "").lower().removeprefix("www.")
    labels = host.split(".")
    names = {labels[-2] if len(labels) >= 2 else host} - {"", "com", "org", "co", "net"}
    for part in re.split(r"\s+[|–—]\s+|\s+-\s+", title.lower()):
        found = re.fullmatch(r"([a-z][a-z &'’-]{1,55}?)\s+(?:community |federal )?(?:credit union|bank)", part.strip())
        if found and not re.search(r"\b(?:your|the|how|about|join|from|for|at|rates|guide)\b", found[1]):
            names.update((found[1].strip(), part.strip()))
    return names


_ROUTING = re.compile(r"\b(?:routing(?:/ABA)?|ABA) (?:number|code|no\.?|#)"
                      r"[\s*:()#=_-]*(?:is\s+)?(?P<value>\d{9})\b", re.I)


def routing_entries(text, organization_names):
    """Return each owned value and its exact, independently attributable span."""
    names = sorted(organization_names, key=len, reverse=True)
    owner = r"\bour(?:\s+(?:bank|credit union)['’]s)?"
    for name in names:
        owner += r"|\b" + re.escape(name) + r"(?:\s+(?:community |federal )?(?:credit union|bank))?['’]s"
    owner = re.compile(r"(?:" + owner + r")\s*$", re.I)
    out = []
    for match in _ROUTING.finditer(text):
        prefix = text[:match.start()]
        marker = owner.search(prefix)
        last_clause = re.split(r"[.!?;\n]", prefix)[-1]
        if not marker and not re.fullmatch(r"[\s*_#•-]*", last_clause):
            continue
        start = marker.start() if marker else match.start()
        out.append((match["value"], text[start:match.end()]))
    return tuple(out)


# Question words and prepositions end a name, including in lower-case queries.
_NAME_WORD = (r"(?!(?:a|an|the|your|my|our|their|this|that|what|which|how|where|is|are|was|"
              r"do|does|did|can|could|will|would|at|from|for|of|by|with|on|to|and|or|than|apr|apy|rates?)\b)"
              r"[a-z0-9][a-z0-9-]*")
_INSTITUTION = re.compile(
    rf"\b(?P<brand>{_NAME_WORD}(?:\s+{_NAME_WORD}){{0,5}}?)"
    r"\s+(?:(?:community|federal)\s+)?(?:bank|credit union)\b", re.I)


def other_institution(question, inventory):
    """Bind named providers and possessives to the institution in this capture."""
    if not re.search(r"\b(?:APR|APY|rates?|yields?|routing|ABA|fees?)\b", question, re.I):
        return False
    providers = set()
    for match in _INSTITUTION.finditer(question):
        before, after = question[:match.start()], question[match.end():]
        if (re.search(r"\b(?:at|from|for|of|by|with|does|did)\s+(?:the\s+)?$", before, re.I)
                or re.match(r"['’]s\b|\s+(?:offer|pay|charge|publish|list)s?\b", after, re.I)):
            providers.add(match["brand"].casefold())
    possessives = re.finditer(r"\b([a-z0-9-]+)['’]s\b", question, re.I)
    common = {"what", "who", "it", "today", "yesterday", "tomorrow", "member", "account",
              "product", "card", "loan", "mortgage", "certificate", "branch", "bank",
              "union", "year", "month", "week", "checking", "saving", "savings", "customer"}
    names = {m[1].casefold() for m in possessives} - common
    if not (names or providers):
        return False
    for page in inventory.pages:
        known = organization_names(page.url, page.title)
        providers.difference_update(known)
        names.difference_update(known)
        if not (names or providers):
            return False
    # A named product can also own a measure ("Platinum Visa's APR").
    product_words = {word for c in inventory.claims for word in c.key.product.split()}
    return bool(providers or names - product_words)
