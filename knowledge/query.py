"""Answer member questions from published observations of one site."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from .branches import answer_branch
from .identity import organization_names, other_institution, routing_entries
from .prose import LINK, blocks, cited, literal_link, narrative, plain, refuse, site_for
from .rates import answer_rates
from .schema import Reply
from .search import search_passages
from .temporal import answer_dated


def answer_member(history, question, as_of=None):
    return answer_dated(history, question, as_of, answer_view)


def routing(view, site, on, question):
    if other_institution(question, view):
        return refuse()
    candidates = []
    for doc in site.visible(on):
        if doc.archive or not re.search(r"\brouting\b|\bABA\b", doc.body, re.I):
            continue
        names = organization_names(doc.page.url, doc.page.title)
        for value, quote in routing_entries(doc.body, names):
            candidates.append((value, doc.evidence(view, quote)))
    if not candidates:
        return refuse()
    values = dict(candidates)
    if len(values) != 1:
        return refuse("The published routing numbers disagree. Please confirm the number with the credit union.",
                      values.values())
    value = next(iter(values))
    sources = tuple(dict.fromkeys(proof for _, proof in candidates))
    return Reply(f"The published routing number is {value}.", sources[:4])


def membership(view, site, on, q):
    wants_eligibility = re.search(
        r"eligib|qualif|who|can (?:i|someone) (?:join|become)|requirement|live|work|residen", q
    )
    options = []
    for doc in site.visible(on):
        if doc.archive:
            continue
        headings = re.finditer(
            r"(?im)^#{1,5}\s+[^\n]*(?:eligible to join|membership eligibil|who (?:can|may) join|eligible for membership)[^\n]*",
            doc.body,
        )
        sections = (doc.body[h.end():].partition("\n#")[0] for h in headings)
        section = next((text for text in sections if text.strip()), "")
        if wants_eligibility:
            sources = re.findall(r"(?m)^\s*[-*]\s+(.+)", section)
            if not sources:
                paragraph = next((line for line in blocks(section) if len(line) > 15), "")
                sources = [paragraph] if paragraph else []
            text = "\n".join(plain(line) for line in sources)
            if not text:
                continue
            evidence = [doc.evidence(view, line) for line in sources]
            # A charter map often needs its accompanying written description.
            if "charter area" in text.lower():
                places = narrative(site, on, r"serves (?:residents|people|members) in [^.!?\n]{0,100}(?:counties|communities)[^.!?\n]{4,110}")
                if places:
                    description, line = places[0]
                    place = re.search(r"serves (?:residents|people|members) in ([^.!?\n]+)", line, re.I)
                    if place:
                        text += f" The published service area covers {plain(place[1])}."
                        evidence.append(description.evidence(view, place[0]))
            return Reply(text, tuple(evidence))
        for link in LINK.finditer(doc.body):
            if not re.fullmatch(r"(?:become (?:a |an? )?member|(?:join|apply) (?:now|today|online|the credit union|[A-Z][\w-]+))", link[1], re.I):
                continue
            target = literal_link(doc, link)
            if target:
                rank = (bool(section), bool(re.search(r"become a member|apply", link[1], re.I)))
                options.append((rank, doc, link[0], target))
    if options:
        _, doc, quote, target = max(options, key=lambda row: row[0])
        return cited(view, doc, quote, "Apply online at " + target)
    return refuse()


def rate_page(view,site,on,q):
    families = {"certificate":r"certificate|\bcds?\b","mortgage":r"mortgage|home loan","auto":r"auto|vehicle",
                "checking":r"checking","savings":r"savings","credit card":r"credit card"}
    requested = next((name for name, regex in families.items() if re.search(regex,q)),None)
    if requested is None:
        return refuse()
    pattern = families[requested]
    def named_families(text):
        return {name for name, regex in families.items() if re.search(regex, text, re.I)}

    candidates = []
    for d in site.visible(on):
        if d.archive or not re.search(pattern,d.body,re.I) or "/calculator" in d.path:
            continue
        for link in LINK.finditer(d.body):
            if not re.search(r"rates?|yields?",link[1],re.I):
                continue
            target=literal_link(d,link)
            if not target:
                continue
            self_anchor = "#" in target and target.split("#")[0].rstrip("/") == d.page.url.rstrip("/")
            labels = named_families(link[1])
            destination = urlsplit(target)
            targets = named_families(re.sub(r"[-_/]+", " ", destination.path+" "+destination.fragment))
            # A certificate can be published on a broader savings page. A link explicitly
            # labeled for mortgages, or pointing to a mortgage section, cannot support it.
            allowed = {requested, "savings"} if requested == "certificate" else {requested}
            if (labels and requested not in labels) or (targets and not (targets & allowed)):
                continue
            headings = list(re.finditer(r"(?m)^#{1,6}\s+([^\n]+)", d.body[:link.start()]))
            section = headings[-1][1] if headings else d.page.title
            via_section = bool(re.search(pattern, section, re.I))
            if not (requested in labels or requested in targets or via_section):
                continue
            if "business" in q and "business" not in (d.path+" "+target+" "+section).lower():
                continue
            audience = ("business" in q) == ("business" in d.path)
            rank = (audience, self_anchor, requested in labels, via_section)
            proof = [d.evidence(view,link[0])]
            if via_section and headings:
                proof.append(d.evidence(view,headings[-1][0]))
            candidates.append((rank, target, tuple(proof)))
    if candidates:
        _, target, proof = max(candidates,key=lambda row:row[0])
        return Reply(target,proof)
    return refuse()


def wallet(view, site, on, q):
    options = narrative(
        site, on, r"(?:add|use).{0,65}(?:debit|credit|cards?).{0,95}(?:[A-Za-z]+ Pay|mobile wallet)",
        rank=lambda doc, line: (bool(re.search(r"mobile.payments|wallet", doc.path)),
                                len(re.findall(r"\b\w+ Pay\b", line))),
    )
    if not options:
        return refuse()
    doc, quote = options[0]
    named = re.search(r"\b(\w+) pay\b",q,re.I)
    if named and not re.search(re.escape(named[1])+r" Pay\b",quote,re.I):
        return refuse("I couldn't verify support for that wallet in the published card information.")
    lines = [quote]
    if re.search(r"set up|how (?:can|do|to)|default",q):
        steps = [line for line in blocks(doc.body) if re.search(r"^#{1,5}\s*(?:\*\*)?\d+[:.]|set .*card as your default",line,re.I)]
        lines.extend(steps[:5])
    return Reply(" ".join(plain(s) for s in lines),tuple(doc.evidence(view,s) for s in lines))


def student(view,site,on):
    candidates = [d for d in site.visible(on) if not d.archive and re.search(r"student loans?",d.page.title,re.I)]
    for doc in candidates:
        intro=next((line for line in blocks(doc.body) if not line.startswith(("#","[")) and re.search(r"education|college|student|repayment",line,re.I)),None)
        if not intro:
            continue
        details = [s for s in blocks(doc.body) if not s.startswith(("#","[")) and re.search(r"defer full payments|origination fees",s,re.I)]
        quotes = [intro]+details[:2]
        return Reply("Student loans: "+" ".join(map(plain,quotes)),tuple(doc.evidence(view,s) for s in quotes))
    return refuse()


def update_details(view, site, on):
    rows = narrative(site, on, r"(?:change|update|correct) your (?:personal|contact|account) (?:information|details)")
    for doc, quote in rows:
        if re.search(r"log(?:ging)?\s*in|call|contact us|profile",quote,re.I):
            excerpt = re.split(r"(?<=[.!?])\s+", quote)
            result = " ".join(excerpt[:2])
            return cited(view,doc,result)
    return refuse()


def named_program(view,site,on,q):
    # Named programs often contain a registered mark or a deliberately unusual spelling.
    names = re.findall(r"\b[a-z]+(?:\$|®|™)[a-z]*",q,re.I)
    if not names:
        return None
    for name in names:
        rows = narrative(
            site, on, re.escape(name), topic=re.escape(name),
            rank=lambda doc, line: bool(re.search(r"provides|offers|helps|allows|assistance", line, re.I)
                                        and re.search(r"\$\d", line)),
        )
        if rows:
            doc, quote = rows[0]
            return cited(view, doc, quote)
    return refuse()


def recognition(view, site, on, q):
    issuer = (re.search(r"(?:from|by) ([a-z][a-z-]*)", q, re.I)
              or re.search(r"\b([a-z][a-z-]*) (?:recognition|rankings?|award)", q, re.I))
    if not issuer:
        return None
    name = re.escape(issuer[1])
    awards = r"(?:rank|recogni[sz]|named|award)"
    pattern = name + r".{0,130}" + awards + "|" + awards + r".{0,100}" + name
    rows = narrative(
        site, on, pattern, topic=name, editorial=True,
        rank=lambda doc, line: bool(re.search(r"\btimes?\b", line, re.I)
                                    and re.search(r"credit union|bank", doc.page.title, re.I)),
    )
    if rows:
        doc, quote = rows[0]
        return cited(view, doc, quote)
    return refuse()


def volunteer(view, site, on, q):
    measure = (r"\b\d+[\s*]+(?:[\w'-]+\s+){0,3}employees?[\s*]+"
               r"(?:used|took|utili[sz]ed|claimed|took advantage of)\s+"
               r"[^.!?\n]{0,120}(?:volunteer time off|paid volunteer leave|\bVTO\b)")
    rows = narrative(site, on, measure, editorial=True)
    year = re.search(r"\b(20\d\d)\b", q)
    wanted_year = year[1] if year else None
    if not wanted_year and "last year" in q:
        wanted_year = str(int(on[:4]) - 1)
    available = {}
    for doc, quote in rows:
        event_year = re.search(r"\b(20\d\d)\b", quote)
        if event_year:
            available.setdefault(event_year[1], (doc, quote))
            if not wanted_year or wanted_year == event_year[1]:
                return cited(view, doc, quote)
    if wanted_year and available:
        latest_year = max(available)
        doc, quote = available[latest_year]
        count = re.search(r"\b(\d+) (?:[\w'-]+\s+){0,3}employees?\b", plain(quote), re.I)
        if count:
            return refuse(
                f"I couldn't verify a figure for {wanted_year}. The most recent figure I found was "
                f"{count[1]} employees in {latest_year}.", [doc.evidence(view, quote)]
            )
    return refuse()


def answer_view(inventory, question, effective_on):
    q = question.casefold()
    on = str(effective_on or inventory.taken_on)
    site = site_for(inventory)
    if re.search(r"\b(?:routing|aba) (?:number|code)|transit number",q):
        return routing(inventory,site,on,question)
    if re.search(r"\bbranch(?:es)?\b|\batm\b|\blobby\b|drive[- ]?(?:up|thru|through)",q):
        reply=answer_branch(inventory,site,on,q)
        if reply is not None:
            return reply
    if re.search(r"\bjoin\b|\bmembership\b|become (?:a|an?) .*member",q) and not re.search(r"rate|fee|minimum|bonus",q):
        return membership(inventory,site,on,q)
    if re.search(r"\b(?:link|url|website)\b|where (?:can|do) i (?:see|view|find|check)",q) and re.search(r"rate|apy|apr",q):
        return rate_page(inventory,site,on,q)
    if re.search(r"\bwallet\b|mobile payments?|\b\w+ pay\b",q) and re.search(r"card|wallet|contactless|mobile pay",q):
        return wallet(inventory,site,on,q)
    if re.search(r"student|university|college",q) and re.search(r"loan|financ|borrow",q) and not re.search(r"rate|apr|how much|limit|fee|eligible",q):
        return student(inventory,site,on)
    if re.search(r"update|change|correct",q) and re.search(r"contact (?:information|info|details)|personal information|my (?:mailing address|phone number|email address)",q):
        return update_details(inventory,site,on)
    if re.search(r"recognition|recogni[sz]ed|award|ranking",q):
        reply=recognition(inventory,site,on,q)
        if reply is not None:
            return reply
    if re.search(r"volunteer|paid time off",q) and re.search(r"employees?|staff",q) and re.search(r"how many|number",q):
        return volunteer(inventory,site,on,q)
    if re.search(r"program|grant",q):
        reply=named_program(inventory,site,on,q)
        if reply is not None:
            return reply
    reply = answer_rates(inventory, question, effective_on)
    if reply is not None:
        return reply
    return search_passages(inventory, question, effective_on)
