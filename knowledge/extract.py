"""Read member-facing prose and structured pricing without consulting evaluation data."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from html import unescape
import re
from urllib.parse import urlsplit

from .schema import Bound, Claim, Evidence, FactKey, PageRecord

PARSER_VERSION = 1
NUMBER = r"\d[\d,]*(?:\.\d+)?"
PERCENT = re.compile(r"(?<![\w.])\d+(?:\.\d+)?\s*%")
CASH = re.compile(r"\$\s*" + NUMBER)
TERM = re.compile(r"\b(\d+)(?:\s*[-–]\s*(\d+))?[\s-]*(months?|mo|years?|yr)\b", re.I)
MODEL_YEAR = re.compile(r"\b((?:19|20)\d{2})(?:\s*[-–]\s*(\d{2,4}))?\b")
MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE = rf"(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}|{MONTH}\.?\s+\d{{1,2}},?\s+\d{{4}})"
START = re.compile(rf"\b(?:effective(?:\s+(?:as\s+of|from|on|beginning|date))?|valid\s+from|begins?|starts?)\s*[: ]*\s*({DATE})", re.I)
END = re.compile(rf"\b(?:expires?|expired|ends?|ended|valid\s+(?:until|through)|through)\s*(?:on\s+)?[: ]*\s*({DATE})", re.I)
PLAIN_DATE = re.compile(rf"^(?:published\s*(?:on|:)?\s*)?({DATE})$", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TABLE_SEPARATOR = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-*\s*\|?\s*$")
LINK = re.compile(r"\[([^\]]*)\]\([^)]+\)")


def clean(text: str) -> str:
    text = unescape(unescape(text))
    return re.sub(r"\s+", " ", LINK.sub(r"\1", text).replace("**", "").replace("\\*", "").strip())


def words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", clean(text).lower().replace("&", " and ").replace("’", "").replace("'", "")))


def iso(text: str) -> str | None:
    text = text.replace(",", "").replace(".", "")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def dates(text: str) -> tuple[str | None, str | None]:
    def unique(rx):
        found = {iso(m.group(1)) for m in rx.finditer(text)}
        return found.pop() if len(found) == 1 else None
    return unique(START), unique(END)


def classify(page: PageRecord) -> str:
    path = urlsplit(page.url).path.lower().strip("/")
    tail = path.split("/")[-1]
    title = words(page.title)
    if re.search(r"fee[-_ ]schedule|schedule[-_ ]of[-_ ]fees", path + " " + title):
        return "fee_schedule"
    if re.search(r"\bcalculator\b", words(tail + " " + title)) or path.startswith("calculators/"):
        return "calculator"
    if path.startswith(("newsroom/", "news/", "press/")):
        return "news"
    if "/blog/" in "/" + path or re.match(r"\d{4}/\d{2}/", path):
        return "blog"
    if tail in {"rates", "business-rates", "rate-sheet", "rate-schedule", "rate-table"} or title in {"rates", "rate sheet", "rate schedule"}:
        return "rate_sheet"
    if "branch" in path or "location" in path:
        return "branch"
    if any(x in path for x in ("personal/", "business/", "loan", "certificate", "savings", "checking", "credit-card", "account", "product")):
        return "product"
    return "other"


def published(page: PageRecord, source: str, lines: list[str]) -> str | None:
    if source not in {"blog", "news"}:
        return None
    for line in lines[:20]:
        if match := PLAIN_DATE.fullmatch(clean(line)):
            return iso(match.group(1))
    if match := re.search(r"/(\d{4})/(\d{2})/(\d{2})/", page.url):
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    return None


def cells(line: str) -> list[str]:
    return [clean(cell.replace(r"\|", "|")) for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def money_bound(text: str, axis: str) -> Bound | None:
    numbers = re.findall(NUMBER, text)
    if not numbers:
        return None
    first = float(numbers[0].replace(",", ""))
    if len(numbers) >= 2 and re.search(r"[-–—]|\bto\b|\band\b", text, re.I):
        second = float(numbers[1].replace(",", ""))
        return Bound(axis, "dollars", min(first, second), max(first, second))
    low = text.lower()
    if re.search(r"\bor (?:less|lower|below)|\bup to\b|\bat most\b|<=", low):
        return Bound(axis, "dollars", None, first)
    if re.search(r"\b(?:under|less than|below)\b|<", low):
        return Bound(axis, "dollars", None, first, high_inclusive=False)
    if re.search(r"\+|\bor (?:more|higher|above)|\band (?:above|up)|\bat least\b|>=", low):
        return Bound(axis, "dollars", first)
    if re.search(r"\b(?:over|more than|above)\b|>", low):
        return Bound(axis, "dollars", first, low_inclusive=False)
    return Bound(axis, "dollars", first, first)


def term_bound(text: str) -> Bound | None:
    if not (match := TERM.search(text)):
        return None
    factor = 12 if match[3].lower().startswith("y") else 1
    first, second = int(match[1]) * factor, int(match[2] or match[1]) * factor
    if re.search(r"\bup to\b", text, re.I):
        return Bound("term", "months", None, second)
    return Bound("term", "months", min(first, second), max(first, second))


def year_bound(text: str) -> Bound | None:
    if not (match := MODEL_YEAR.search(text)):
        return None
    first = int(match[1])
    if match[2]:
        second = int(match[2]) + (first // 100 * 100 if len(match[2]) == 2 else 0)
        return Bound("model year", "years", min(first, second), max(first, second))
    if re.search(r"\b(?:older|earlier|before|prior)\b", text, re.I):
        return Bound("model year", "years", None, first)
    if re.search(r"\b(?:newer|later|after)\b|\+", text, re.I):
        return Bound("model year", "years", first)
    return Bound("model year", "years", first, first)


def canonical_product(label: str) -> str:
    product = words(label)
    product = re.sub(r"\bbusiness\b", "", product).strip()
    product = re.sub(r"\s+(?:account|rates?)$", "", product)
    if re.search(r"\b(?:auto|vehicle|motorcycle)\b", product):
        return "auto loan"
    if "investors choice" in product:
        return "investors choice money market"
    if "home equity line" in product or "heloc" in product:
        return "home equity line of credit"
    if "home equity loan" in product:
        return "home equity loan"
    if product.startswith("health saving"):
        return "health savings"
    if re.search(r"\b(?:platinum|rewards)\b", product) and re.search("visa|card", product):
        return "platinum visa" if "platinum" in product else "rewards visa"
    return re.sub(r"\bloans\b", "loan", product).strip()


def measure(header: str) -> str | None:
    h = re.sub(r"(?<=[a-z])\d+$", "", words(header))
    if "annual percentage yield" in h or re.search(r"\bapy\d*\b", h):
        return "apy"
    if "annual percentage rate" in h or re.search(r"\bapr\d*\b", h):
        return "apr"
    if "dividend rate" in h:
        return "dividend rate"
    if h in {"rate", "interest rate", "note rate"}:
        return "interest rate"
    if h.startswith(("min to ", "minimum to ")):
        return "minimum to " + h.split(" to ", 1)[1]
    if h == "points":
        return "points"
    return None


def value_of(text: str, metric: str) -> str | None:
    if metric.startswith("minimum"):
        match = CASH.search(text)
        return match[0].replace(" ", "") if match else None
    if metric == "points":
        return text if re.fullmatch(r"\d+(?:\.\d+)?", text) else None
    values = [v.replace(" ", "") for v in PERCENT.findall(text)]
    if len(values) == 2 and re.search(r"[-–—]|\bto\b", text):
        return " – ".join(values)
    if len(values) == 1:
        return values[0]
    # Some APR columns omit the unit on every row.
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return text + "%"
    return None


def tier_type(label: str) -> str:
    return "jumbo special" if "jumbo" in label else "special" if "special" in label else "regular"


def column_qualifier(header: str) -> tuple[str, str] | None:
    """Preserve a cell's pricing period independently of the loan/deposit term."""
    label = words(header)
    if match := re.search(r"\b(?:first|1st|initial)\s+(\d+)\s+(months?|years?)\b", label):
        return ("period", "first " + match[1] + " " + match[2])
    if re.search(r"\bafter (?:the )?(?:promotional|introductory) period\b", label):
        return ("period", "after promotional period")
    if re.search(r"\b(?:introductory|promotional)\b", label):
        return ("period", "promotional")
    return None


def member_condition(text: str) -> str | None:
    """Accept explicit membership groups and offer restrictions, never incidental mentions."""
    text = words(text)
    groups = re.findall(r"\b(new|existing|current)\s+(?:members?|customers?|cardholders?)\b", text)
    if len(set(groups)) != 1 or re.search(r"\b(?:new (?:and|or) existing|existing (?:and|or) new)\b", text):
        return None
    noun = r"(?:members?|customers?|cardholders?)"
    group = r"(?:new|existing|current)\s+" + noun
    if re.search(r"\bnot (?:only|limited|restricted)\b", text):
        return None
    if re.search(r"\b(?:not available to|excludes|not open to|unavailable to)\s+" + group + r"\b", text):
        return "existing members" if groups[0] == "new" else "new members"
    if not (re.fullmatch(group, text)
            or re.search(r"\b" + group + r"\s+(?:only|offer|promotion|special|rates?|pricing)\b", text)
            or re.search(r"\b(?:for|limited to|available to|restricted to|open to|exclusively for)\s+(?:eligible\s+)?" + group + r"\b", text)):
        return None
    return "new members" if groups[0] == "new" else "existing members"


def table_claims(headers: list[str], data: list[str], section: str, e: Evidence,
                 membership: str | None = None) -> list[Claim]:
    labels = [words(h) for h in headers]
    row = dict(zip(labels, data))
    first = data[0]
    initial = words(first)
    context = words(section)
    text = " ".join((context, *labels, initial))
    audience = "business" if "business" in text or "business" in urlsplit(e.url).path else "personal"
    primary_label = row.get("account type") or row.get("account") or section
    if "product" in row and words(row["product"]) not in {"standard", "loan", "heloc standard"}:
        if not re.match(r"^(?:loan|heloc)\s*[-–]", row["product"], re.I):
            primary_label = row["product"]
    product = canonical_product(primary_label)
    qualifiers, bounds = {}, []
    eligibility = member_condition(row.get("eligibility", "") or row.get("member type", "")) or membership
    if eligibility:
        qualifiers["eligibility"] = eligibility
    term = row.get("term", row.get("term length", ""))
    for name in ("balance tier", "balance", "balance range", "loan amount", "amount"):
        if name in row and (bound := money_bound(row[name], "balance" if "balance" in name else "amount")):
            bounds.append(bound)
    if "loan type" in row and "$" in first and (bound := money_bound(first, "amount")):
        bounds.append(bound)

    if "points" in labels and ("apr" in labels or any("payment example" in h for h in labels)):
        product = "mortgage"
        purpose = re.search(r"\b(purchase|refinance)\b", initial)
        if purpose:
            qualifiers["purpose"] = purpose[0]
        if match := TERM.search(first):
            program_label = first[match.end():].split("$", 1)[0].strip(" :-")
        else:
            program_label = first.split("$", 1)[0].strip(" :-")
        if program_label:
            qualifiers["program"] = words(program_label)
        if "$" in first and (bound := money_bound(first[first.index("$"):], "amount")):
            bounds.append(bound)
        term = first
    elif ("ira" in context.split() or "iras" in context.split() or "ira type" in labels
          or re.match(r"(?:roth|traditional)\s*:", first, re.I)):
        product = "ira"
        qualifiers["type"] = "variable" if "variable" in context else tier_type(initial + " " + context)
        if plan := re.search(r"\b(roth|traditional)\b", initial):
            qualifiers["plan"] = plan[0]
        if "$" in first and not bounds and (bound := money_bound(first[first.index("$"):], "balance")):
            bounds.append(bound)
        term = first
    elif ("certificate" in text or ("term" in labels and "dividend rate" in labels)
          or re.search(r"\bcds?\b", context)):
        product = "certificate"
        qualifiers["type"] = tier_type(initial + " " + context)
        term = first
    elif "card type" in labels or "visa" in text or any("credit card" in h for h in labels):
        candidate = next((p for p in (context, labels[0], initial) if "platinum" in p or "rewards" in p), context)
        product = canonical_product(candidate)
        qualifiers["type"] = "introductory balance transfer" if "balance transfer" in initial else "standard"
    else:
        if year := year_bound(first):
            if "model year" in initial or "model year" in labels:
                bounds.append(year)
        if "model year" in row and (bound := year_bound(row["model year"])) and bound not in bounds:
            bounds.append(bound)
        if not term and ("year" in initial or "month" in initial or "(" in first):
            term = first
    if parsed_term := term_bound(term):
        bounds.append(parsed_term)
    if not product:
        return []
    entity = (urlsplit(e.url).hostname or "").removeprefix("www.")
    result = []
    combined = words(" ".join(e.headings))
    model_context = "model year" in combined or "vehicle year" in combined
    apr_context = "apr" in combined.split() or "annual percentage rate" in combined
    columns = []
    for label in headers:
        metric = measure(label)
        year = year_bound(label) if model_context and "term" in labels else None
        if year and not metric and apr_context:
            metric = "apr"
        columns.append((metric, column_qualifier(label), year))
    for cell, (metric, regime, year) in zip(data, columns):
        if not metric or columns.count((metric, regime, year)) > 1:
            # A repeated column with unspecified scope cannot support a unique fact.
            continue
        if value := value_of(cell, metric):
            tags = dict(qualifiers)
            if regime:
                tags[regime[0]] = regime[1]
            cell_bounds = [*bounds, year] if year else bounds
            key = FactKey(entity, product, audience, metric, tuple(sorted(tags.items())),
                          tuple(sorted(cell_bounds, key=lambda b: b.axis)))
            result.append(Claim(key, value, e))
    return result


def fee_claim(label: str, description: str, group: str, e: Evidence) -> Claim | None:
    # Keep conditions visible. A fee can be waived below a threshold or charged per item.
    description = clean(description)
    description = description.replace("*", "").replace("_", "")
    amount = re.match(r"^(\$\s*[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?\s*%|free\b|available at no charge\b)", description, re.I)
    if not amount:
        return None
    if "free for members" in description.lower() and re.search(r"[$%]", description):
        # Two audiences and two rates in one PDF cell. It remains a searchable passage.
        return None
    audience_text = words(" ".join((group, label, description)))
    audience = "nonmember" if "non member" in audience_text and "free for members" not in audience_text else (
        "business" if "business" in audience_text else "personal")
    product = words(label)
    # A PDF bullet such as "We will charge $12 per item for..." has no service
    # name before the price. Preserve the passage without inventing a product.
    if not product or re.fullmatch(r"(?:we|you|members?) (?:will |may |are |must )?(?:be )?(?:pay|charge|charged)", product):
        return None
    entity = (urlsplit(e.url).hostname or "").removeprefix("www.")
    value = amount[0].replace(" ", "") if re.match(r"[$\d]", amount[0]) else "Free"
    unit = re.match(r"\s*(per\s+(?:item|day|month|year|hour|roll|inquiry|transaction(?:/balance inquiry)?)\b|each\b|of\s+(?:the\s+)?(?:amount|total)\b)",
                    description[amount.end():], re.I)
    if unit:
        unit_label = unit[1].lower()
        value += " " + ("per item" if unit_label == "each" else unit_label)
    return Claim(FactKey(entity, product, audience, "fee"), value, e)


PROSE_METRIC = re.compile(r"\b(APY|APR|annual percentage (?:yield|rate)|interest rate|dividend rate)\b", re.I)
BRANCH_COUNT = re.compile(r"(?:\b(?:now\s+)?(?:operates?|has)\s+|[’']s\s+)(\d{1,3})\s+(?:full.service\s+)?branches\b", re.I)


def prose_claims(e: Evidence) -> list[Claim]:
    from .identity import organization_names, routing_entries

    text = clean(e.quote)
    entity = (urlsplit(e.url).hostname or "").removeprefix("www.")
    if "routing" in text.lower() or "aba" in text.lower():
        owned = routing_entries(e.quote, organization_names(e.url, e.title))
        if owned:
            return [Claim(FactKey(entity, "routing", "", "routing number"), number, e)
                    for number, _ in owned]
    if match := BRANCH_COUNT.search(text):
        # Exclude third-party counts or citations with no attributable institution.
        identity = words(entity.split(".")[0])
        subject = words(text[max(0, match.start() - 55):match.start()])
        if identity in subject.split() or subject.endswith(("credit union", "our institution", "we")):
            return [Claim(FactKey(entity, "branch network", "personal", "branch count"), match[1], e)]

    if match := re.fullmatch(r"(.{2,110}?\bfee)\s*:\s*(\$\s*[\d,]+(?:\.\d+)?(?:\s+per\s+\w+)?)\.?", text, re.I):
        fee = fee_claim(match[1], match[2], "", e)
        return [fee] if fee else []
    if e.source_class == "fee_schedule" and "|" not in text and len(text) < 220:
        if match := re.fullmatch(r"(.+?)\s+(\$[\d,.]+[^$]*|Free(?:\s.*)?|\d+(?:\.\d+)?%\s+of .+)", text, re.I):
            fee = fee_claim(match[1], match[2], " ".join(e.headings), e)
            if fee:
                return [fee]
    if "%" not in text or len(text) > 800:
        return []
    matches = list(PROSE_METRIC.finditer(text))
    if not matches:
        return []
    metrics = {measure(m[0]) for m in matches}
    if len(metrics) != 1 or not (metric := metrics.pop()):
        return []
    # Multiple percentages are safe only when they form a single stated range.
    if len(PERCENT.findall(text)) > 1 and not re.search(r"%\s*[-–—]\s*\d+(?:\.\d+)?%", text):
        return []
    if not (value := value_of(text, metric)):
        return []
    context = words(" ".join(e.headings[-2:]))
    body = words(text)
    tier = ()
    bound = term_bound(text)
    if "certificate" in body:
        product = "certificate"
        tier = (("type", tier_type(body)),)
    elif ("auto loan" in body or "vehicle loan" in body) and "example" in body:
        product = "auto loan"
    else:
        # Explicit labeled assertions only; a paragraph mentioning finance and a number is insufficient.
        label = re.match(r"^(?:[\s_*#-]*)([A-Za-z][\w \-’']{1,65}?)\s+(?:APY|APR|dividend rate|interest rate)\s*(?::|is|of|=)\s*\d", text, re.I)
        if not label:
            return []
        product = canonical_product(label[1])
        if product in {"the", "our", "your", "an", "the current"}:
            product = canonical_product(context)
    if not product:
        return []
    audience = "business" if "business" in body or "business" in urlsplit(e.url).path else "personal"
    return [Claim(FactKey(entity, product, audience, metric, tier, (bound,) if bound else ()), value, e)]


def local_notes(lines: list[str], end: int) -> str:
    notes = []
    for line in lines[end:end + 14]:
        if not line.strip():
            continue
        if START.search(line) or END.search(line) or (len(line) <= 240 and member_condition(line)):
            # A new section title belongs to the following table. A note refers back to the offer.
            if HEADING.match(line) or (section_label(line) and not re.match(r"(?:this |available |only |limited |restricted )", line, re.I)):
                break
            notes.append(line)
        else:
            break
    return "\n".join(notes)


def section_label(line: str) -> bool:
    return (0 < len(line) <= 95 and not line.startswith(("-", "[", "!", "|", "#", "_"))
            and not re.search(r"[.!?]$|https?://|\\[rn]|\d\s*%|\b(?:effective|expires)\b", line, re.I))


def extract_page(page: PageRecord, snapshot_id: str, taken_on: str) -> tuple[tuple[Claim, ...], tuple[Evidence, ...]]:
    lines = page.markdown.splitlines()
    source = classify(page)
    template = Evidence(snapshot_id, taken_on, page.url, page.title, source, (), "",
                        page.fetched_at, published(page, source, lines))
    # An explicitly dated official fee schedule applies its document date to the rows.
    doc_dates = dates("\n".join(lines[:7])) if source == "fee_schedule" else (None, None)
    headings = []
    nearby = ""
    leading_condition = None
    remaining_notes = 0
    section_dates = (None, None)
    before_table = True
    passages, claims = [], []
    i = 0
    while i < len(lines):
        raw = lines[i]
        text = raw.strip()
        if not text or text == "---":
            i += 1
            continue
        is_table_note = remaining_notes > 0
        if is_table_note:
            remaining_notes -= 1
        if match := HEADING.match(text):
            level = len(match[1])
            inherited_condition = leading_condition if headings and level > headings[-1][0] else None
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, clean(match[2])))
            nearby = ""
            heading_text = headings[-1][1]
            leading_condition = heading_text if member_condition(heading_text) else inherited_condition
            section_dates = (None, None)
            before_table = True
        path = tuple(s for _, s in headings)
        is_table = ("|" in raw and i + 1 < len(lines)
                    and TABLE_SEPARATOR.fullmatch(lines[i + 1].strip()) is not None)
        if is_table:
            header = cells(raw)
            section = nearby or (path[-1] if path else page.title)
            end = i + 2
            while end < len(lines) and lines[end].strip().startswith("|"):
                end += 1
            notes = local_notes(lines, end)
            remaining_notes = len(notes.splitlines())
            start_date, end_date = dates(notes)
            condition_text = next((ln.strip() for ln in notes.splitlines() if member_condition(ln)), None)
            condition_text = condition_text or leading_condition or (section if member_condition(section) else None)
            membership = member_condition(condition_text) if condition_text else None
            path = tuple(dict.fromkeys(s for s in (*path, section, condition_text, clean(raw)) if s))
            basis = replace(template, headings=path, effective_from=start_date or section_dates[0] or doc_dates[0],
                            effective_until=end_date or section_dates[1] or doc_dates[1])
            # PDF extraction sometimes puts the first price row into the Markdown header.
            rows = [raw, *lines[i + 2:end]] if source == "fee_schedule" else lines[i + 2:end]
            group = header[0] if header else ""
            for row_text in rows:
                row = cells(row_text)
                if not any(row):
                    continue
                evidence = replace(basis, quote=row_text)
                passages.append(evidence)
                if source == "fee_schedule":
                    if len(row) >= 2 and (fee := fee_claim(row[0], row[1], group, evidence)):
                        claims.append(fee)
                    elif len(row[0]) < 80 and not any(row[1:]):
                        group = row[0]
                else:
                    claims.extend(table_claims(header, row, section, evidence, membership))
            nearby = ""
            leading_condition = None
            section_dates = (None, None)
            before_table = False
            i = end
            continue
        if text.startswith("![") and "](" in text and text.endswith(")"):
            i += 1
            continue
        if len(text) <= 3000:
            parts = [text]
        else:
            # Preserve exact original substrings when a scrape collapses many sentences into one line.
            parts = re.findall(r".{1,1000}(?:[.!?]\s+|\s+|$)|\S+", text)
        for part in parts:
            if not part.strip():
                continue
            start_date, end_date = dates(part) if re.search(r"effective|expir|offer ended|valid |through", part, re.I) else (None, None)
            kind = "calculator" if re.search(r"\b(?:illustrative purposes|hypothetical example|payment example for)\b", part, re.I) else source
            evidence = replace(template, headings=path, quote=part.strip(), source_class=kind,
                               effective_from=start_date or section_dates[0] or doc_dates[0],
                               effective_until=end_date or section_dates[1] or doc_dates[1])
            passages.append(evidence)
            if ("%" in part or "$" in part or "branches" in part.lower()
                    or "routing" in part.lower() or "aba number" in part.lower()):
                claims.extend(prose_claims(evidence))
            if len(part) < 180 and before_table and (start_date or end_date):
                section_dates = (start_date or section_dates[0], end_date or section_dates[1])
        if not is_table_note and not match and section_label(text):
            nearby = clean(text)
            section_dates = (None, None)
            before_table = True
        if not is_table_note and not match and before_table and len(text) <= 240 and member_condition(text):
            leading_condition = text
        i += 1
    return tuple(claims), tuple(passages)
