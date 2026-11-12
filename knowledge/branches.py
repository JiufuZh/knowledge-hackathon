"""Branch directory entries, dated announcements, and explicitly labeled schedules."""
from __future__ import annotations

import re
from typing import NamedTuple

from .prose import DATE, LINK, Document, blocks, cited, literal_link, narrative, parsed_date, plain, refuse
from .schema import Reply

DAY = r"(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
SCHEDULE = re.compile(r"^\s*(" + DAY + r"\b.*?(?:\d(?::\d\d)?\s*[ap]\.?m\.?|closed|noon|ATM only))\s*$", re.I)
ADDRESS = re.compile(r"^\s*\d+[ \t][^\n]{2,110}?,\s*[^\d\n,]+,\s*[A-Za-z]{2},?\s+[0-9]{5}(?:-\d{4})?\s*$", re.M)
BRANCH_GENERIC = set("""a all alternate alternatives am an and any are as at atm avenue available bank banking
branch branches by can close closed closes closing closure credit current currently days date dates day did do does will
drive drivethrough driveup through thru up during exact for from full general generally get give go has have
hour hours i if in information is it its keep know lab lane learning lobby local location locations me member
members monday morning most my near no of office offices on open opened opening or our please provide rd
regular road same saturday schedule schedules service should show still st street sunday tell the their there
they this time times to today typical union until us what when where which window with work would you your
how many address addresses find could named located postal mailing week weekday weekdays weekend friday tuesday
wednesday thursday pm specific operating opening business tell repeat give take instead list listings enumerate directory nearest closest locations names
around across ones available both see every please network which throughout offer""".split())


def branch_terms(question, site):
    q = re.sub(r"['’]s\b|\([^)]*\)|(?:as of|in|on)\s+(?:[A-Za-z]+\s+)?20\d\d.*", "", question.lower())
    tokens = set(re.findall(r"[a-z]+", q)) - BRANCH_GENERIC
    for doc in site.docs[:1]:
        tokens.difference_update(re.findall(r"[a-z]+", doc.page.url.split("//")[-1].split("/")[0]))
    return tokens


def has_name(terms, line):
    return all(re.search(r"\b" + re.escape(t) + r"\b", line, re.I) for t in terms)


class Schedule(NamedTuple):
    doc: Document
    branch: str
    days: tuple[str, ...]
    quote: str


def _saturday_schedule(days):
    row = next((day for day in days if day.lower().startswith("sat")), "")
    return re.sub(r"[^a-z0-9]+", " ", row.casefold())


_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _covers_weekday(row, target_day):
    # A weekday can fall inside a printed range (e.g. Monday–Friday).
    days = [_WEEKDAYS.index(day.lower()[:3]) for day in re.findall(DAY + r"\b", row, re.I)]
    return bool(days and min(days) <= target_day <= max(days))


def directory(view, site, on, question, terms):
    if re.search(r"locator|nearest|closest|near me|find (?:a |my )?(?:branch|atm)|branch and atm", question, re.I):
        options = []
        for d in site.visible(on):
            if d.archive:
                continue
            for link in LINK.finditer(d.body):
                if re.search(r"branch.{0,12}atm|(?:location|branch|atm) (?:finder|locator)", link[1], re.I):
                    dest = literal_link(d, link)
                    if dest:
                        self_link = dest.split("#")[0].rstrip("/") == d.page.url.rstrip("/")
                        options.append((self_link, d, link.group(), dest))
        if options:
            _, doc, quote, dest = max(options, key=lambda e: e[0])
            return cited(view, doc, quote, dest)
        return refuse()
    enumerate_locations = bool(re.search(r"\blist\b|\bwhich branches\b|\ball (?:the )?(?:branch|location)|\bwhere are (?:your |the |all )?branches\b",question,re.I))
    if not terms and not enumerate_locations:
        return refuse("Which branch or city would you like the address for?")
    candidates = []
    for d in site.visible(on):
        if d.archive:
            continue
        for addr in ADDRESS.finditer(d.body):
            prev = d.body[max(0, addr.start()-450):addr.start()].strip()
            context = re.split(r"(?m)^#{1,6} ",prev)[-1].strip().splitlines()
            label = " ".join(line.strip() for line in context if line.strip())
            is_branch = re.search(r"\bbranch\b",label,re.I) or ("branch" in d.page.title.lower() and len(context)<2)
            if is_branch and not re.search(r"surcharge.free atm|atm.only",label,re.I) and has_name(terms, label+" "+addr[0]+" "+d.page.title):
                candidates.append((d, addr[0].strip(), label))
    if enumerate_locations and candidates:
        entries = {}
        for d, addr, label in candidates:
            entries.setdefault(addr.casefold(),(d,addr,label))
        ordered = sorted(entries.values(),key=lambda item:item[1].casefold())
        parts = [f"{label}: {addr}" for _,addr,label in ordered]
        return Reply("The directory shows these branch entries: "+"; ".join(parts)+". The captured listing may be partial.",
                     tuple(d.evidence(view,addr) for d,addr,_ in ordered))
    if len({a.casefold() for _, a, _ in candidates}) == 1:
        doc, address, _ = candidates[0]
        return cited(view, doc, address, address)
    if candidates:
        return refuse("Several branch addresses match. Which street or neighborhood do you mean?")
    return refuse()


def schedules(view, site, on, question, terms):
    drive = bool(re.search(r"drive|drive[- ]?(?:up|thru|through)", question, re.I))
    heading = r"drive[- ]?(?:up|through|thru)(?: window)?" if drive else "lobby"
    label = re.compile(r"(?im)^[#* \t]*" + heading + r"(?: hours)?[ :*\t]*(?=\r?$|"+DAY+r"\b)")
    options = []
    for doc in site.visible(on):
        for m in label.finditer(doc.body):
            days = []
            # Keep the heading with its lines. A drive-up row cannot fill a lobby gap.
            for line in doc.body[m.end():].lstrip().splitlines():
                if not line.strip():
                    continue
                row = SCHEDULE.match(plain(line))
                if not row:
                    break
                days.append((row[1], line.strip()))
            if not days:
                continue
            intro = doc.body[:m.start()]
            # Directories can publish schedules for several named offices on one page.
            prior_headings = re.findall(r"(?im)^#{1,5}\s+([^\n]*(?:branch|office|location)[^\n]*)$",intro)
            local = prior_headings[-1] if prior_headings else ""
            subject = local if local and not doc.archive else doc.page.title + " " + intro[:1500]
            if not has_name(terms, subject):
                continue
            # Limit city extraction to the article dateline preceding this schedule.
            city = re.search(r"(?m)^([A-Z][A-Z .'-]{2,40}),\s*[A-Z][A-Za-z. ]{1,24}[—–-]", intro)
            name = city[1].strip().title() if city else local or doc.page.title.split("|")[0].strip()
            start = doc.body.find(days[0][1], m.end())
            end = doc.body.find(days[-1][1], start) + len(days[-1][1])
            options.append(Schedule(doc, name, tuple(r[0] for r in days), doc.body[m.start():end].strip()))
    if not options:
        return refuse("I couldn't verify published hours for that branch in this capture.")
    options.sort(key=lambda entry: (not entry.doc.archive, entry.doc.published, entry.branch), reverse=True)
    primary = options[0]
    if terms:
        first = primary.doc
        peers = [entry for entry in options
                 if (entry.doc.archive, entry.doc.published) == (first.archive, first.published)]
        if len({entry.days for entry in peers}) > 1:
            return refuse("Published schedules differ for that location; please confirm its hours with the branch.",
                          [entry.doc.evidence(view, entry.quote) for entry in peers[:2]])
    # Distinct examples illustrate variation without treating a single release as universal.
    selected = [primary]
    if not terms:
        different = [entry for entry in options[1:] if entry.days != primary.days]
        if different:
            primary_saturday = _saturday_schedule(primary.days)
            primary_days = set(primary.days)
            def contrast(other):
                return (_saturday_schedule(other.days) != primary_saturday, len(set(other.days) - primary_days))
            selected.append(max(different, key=contrast))
    requested_day = re.search(r"\b(" + DAY + r")\b", question, re.I)
    target_day = _WEEKDAYS.index(requested_day[1].lower()[:3]) if requested_day else None
    parts = []
    for doc, name, days, quote in selected:
        if target_day is not None:
            days = tuple(row for row in days if _covers_weekday(row, target_day))
            if not days:
                return refuse("There is no published schedule for that day in this capture.")
        subject = f"{name}, announced {doc.published or view.taken_on}" if doc.archive else name
        parts.append(f"{subject}: " + "; ".join(days) + ".")
    preface = ("Published drive-up hours" if drive else "Published lobby hours") + " vary by branch. " if not terms else ""
    conclusion = " Which branch do you use?" if not terms else ""
    if len(selected) == 1 and primary.doc.archive:
        conclusion += " I couldn't verify a more recent schedule for that branch."
    return Reply(preface + " ".join(parts) + conclusion,
                 tuple(entry.doc.evidence(view, entry.quote) for entry in selected))


def branch_count(view, site, on):
    pattern = r"\b(\d+)\s+(?:full[- ]service\s+)?branch(?:es| (?:office(?: locations?)?|locations?))\b"
    choices = narrative(site, on, pattern)
    records = []
    for doc, quote in choices:
        m = re.search(pattern, quote, re.I)
        subject = plain(quote[:m.start()]).split(". ")[-1].lower()
        # Exclude other banks, national statistics and subsets of the union.
        org = doc.page.url.split("//")[-1].split("/")[0].split(".")
        own_name = org[-2] if len(org) >= 2 else org[0]
        subject_matches = re.search(r"\b(we|our)\b",subject) or own_name in subject
        if subject.startswith(("it has","it operates")):
            subject_matches = own_name in plain(quote[:m.start()]).lower()
        counting_verb = re.search(r"\b(?:operates?|has|have|maintains?|runs?|is home to)\b",subject)
        if not subject_matches or not counting_verb:
            continue
        rank = (not doc.archive, doc.published)
        records.append((rank, m[1], doc, quote))
    if not records:
        return refuse()
    best = max(r[0] for r in records)
    peers = [r for r in records if r[0] == best]
    if len({r[1] for r in peers}) != 1:
        return refuse("The available descriptions disagree on the branch count.", [r[2].evidence(view,r[3]) for r in peers[:2]])
    _, count, doc, span = peers[0]
    match = re.search(pattern,span,re.I)
    start = span.rfind(". ",0,match.start()) + 2 if ". " in span[:match.start()] else 0
    stop = span.find(". ",match.end())
    sentence = span[start:stop+1 if stop>=0 else len(span)].strip()
    return cited(view,doc,sentence, f"The credit union reports {count} branch locations.")


def announcement(view, site, on, question, terms):
    if not terms:
        return refuse()
    alternate = bool(re.search(r"where|alternative|instead|full.service|other branch",question,re.I))
    action = re.compile(r"(?:full.service branches (?:at|in)|(?:instead|alternatively).{0,80}branch|(?:nearest|alternative) branches)" if alternate else
                        r"\b(?:will close|closes|(?:is |was )?scheduled to close|closed(?: permanently)?(?: on| as of)?|permanently clos\w*|closure (?:on|date))\b", re.I)
    options = []
    for d in site.visible(on):
        if not has_name(terms, d.body + " " + d.page.title) or not action.search(d.body):
            continue
        heading = d.page.title
        for line in blocks(d.body):
            if line.startswith("#"):
                heading = plain(line)
                continue
            for clause in re.split(r"(?<=[.!?;])\s+|\s+(?:and|while|but)\s+(?=[^,.;!?]{1,75}\b(?:closes|will close|is scheduled to close)\b)", line):
                m = action.search(clause)
                if not m:
                    continue
                actor = plain(clause[:m.start()])
                # "This location" may refer back to a single named branch heading.
                # The name of a different explicitly specified subject always wins.
                anaphoric = bool(re.fullmatch(r"(?:this|that|the) (?:office|branch|location)|it",actor,re.I))
                if not has_name(terms, actor) and not (
                        anaphoric and has_name(terms,heading) and
                        not re.search(r"\bbranches\b|\blocations\b",heading,re.I)):
                    continue
                if alternate or DATE.search(clause[m.end():]):
                    options.append((d.published,d,clause,m.end()))
    if not options:
        return refuse()
    _, doc, quote, start = max(options, key=lambda r:r[0])
    if alternate:
        return cited(view, doc, quote)
    when = DATE.search(quote[start:])[0]
    desc = f"The branch was scheduled to close on {when}."
    if parsed_date(when) > on:
        desc = f"The announced closure date is {when}."
    return cited(view,doc,quote,desc)


def answer_branch(view, site, on, question):
    q = question.lower()
    terms = branch_terms(q,site)
    if re.search(r"(how many|number of|count of) (?:\w+[ -]){0,3}(?:branches|branch (?:offices|locations))",q):
        return branch_count(view,site,on)
    if re.search(r"hours|lobby|drive[- ]?(?:through|thru|up)|what time",q):
        return schedules(view,site,on,q,terms)
    if re.search(r"alternative|full.service|still open|clos(?:e|ing|ure)|instead",q) and not re.search(r"closest",q):
        return announcement(view,site,on,q,terms)
    if re.search(r"address|locator|nearest|closest|where|located|find|\blist\b|which branches|all branches",q):
        return directory(view,site,on,q,terms)
    return None
