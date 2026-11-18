"""Distinguish the requested effective date from the last evidence available."""
from __future__ import annotations

import calendar
import re
from dataclasses import replace
from datetime import date, timedelta

from .schema import Reply
from .identity import other_institution


_MONTHS = {name.lower(): i for i in range(1, 13)
           for name in (calendar.month_name[i], calendar.month_abbr[i])}
_MONTHS["sept"] = 9
_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE = re.compile(
    rf"\b(?:(?P<iso>\d{{4}}-\d{{2}}-\d{{2}})|"
    rf"(?P<month>{_MONTH_PATTERN})\.?"
    r"(?:\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?\b(?!\d))?"
    r"(?:,?\s+(?P<year>(?:19|20)\d{2}))?)\b", re.I)
_TIME_INTENT = re.compile(r"\b(?:as of|in|on|since|between|from|during|before|after|by|until)\s*$", re.I)
_CHANGE = re.compile(r"\b(?:chang\w*|compar\w*|difference|increase\w*|decrease\w*|"
                     r"rise|rose|fall|fell|(?:go|gone|went) (?:up|down)|vs|versus|history|timeline)\b", re.I)
_TIMELINE = re.compile(r"\bover time\b|\btimeline\b|\bhistory\b|"
                       r"\bacross (?:the |all )?(?:captures|snapshots)\b", re.I)
_DATE_RANGE = re.compile(rf"\b(?:between|from)\s+(?:\d{{4}}-\d{{2}}-\d{{2}}|{_MONTH_PATTERN})\b", re.I)
_CAPTURE = r"(?:snapshots?|captures?|crawls?|downloads?)"
_RELATIVE_CAPTURE = re.compile(rf"\b(?:original|first|initial|earliest|baseline|latest|newest|current|prior|"
                               rf"previous|preceding|last(?: two| 2)?)\s+{_CAPTURE}\b|\bbaseline\b", re.I)
_PREVIOUS = re.compile(rf"\b(?:previous|prior|preceding|last two|last 2|last)\s+(?:{_CAPTURE}|and|to)\b", re.I)
_FIRST = re.compile(r"\b(?:first|earliest|original|initial|baseline)\b", re.I)
_UNDATED_CHANGE = re.compile(r"\b(?:has|have|had)\b[^?!.]*\b(?:changed|increased|decreased|risen|fallen)\b|"
                             r"\b(?:did|does)\b[^?!.]*\b(?:change|increase|decrease|rise|fall)\b|"
                             r"\bwhat (?:changed|increased|decreased|rose|fell)\b", re.I)
_EFFECTIVE = re.compile(r"\b(?:effective|retroactiv\w*|actually applied|in effect)\b", re.I)
_CORRECTION = re.compile(r"\b(?:correct\w*|retroactiv\w*|amend\w*|restat\w*)\b", re.I)


def _dates(question, cutoff, known_through, cover_interval):
    found = []
    range_connector = r"\s+(?:and|to|through|until)\s+"
    for match in _DATE.finditer(question):
        prefix = question[:match.start()]
        month_only = not (match["day"] or match["iso"])
        before = re.search(r"\bbefore\s*$", prefix, re.I) and not re.search(r"\bon or before\s*$", prefix, re.I)
        if match["iso"]:
            target = date.fromisoformat(match["iso"])
        else:
            range_end = (found or _RELATIVE_CAPTURE.search(prefix)) and re.search(range_connector + "$", prefix, re.I)
            if not (match["year"] or match["day"] or _TIME_INTENT.search(prefix) or range_end):
                continue
            month = _MONTHS[match["month"].lower()]
            year = int(match["year"] or cutoff[:4])
            connector = re.match(range_connector, question[match.end():], re.I)
            following = _DATE.match(question, match.end() + connector.end()) if connector else None
            if not match["year"] and following and following["year"]:
                year = int(following["year"]) - (month > _MONTHS[following["month"].lower()])
            if month_only:
                if before or (cover_interval and not found and not _RELATIVE_CAPTURE.search(prefix)):
                    day = 1
                elif known_through[:7] == f"{year:04d}-{month:02d}" and not re.search(r"\bend of\s*$", prefix, re.I):
                    day = int(known_through[-2:])
                else:
                    day = calendar.monthrange(year, month)[1]
            else:
                day = int(match["day"])
            target = date(year, month, day)
        if before:
            target -= timedelta(days=1)
        found.append((match.start(), target.isoformat()))
    return found


def _mixed_endpoints(question, dated, captures, observed):
    """Bind a named capture and a written date in the order the member requests."""
    if len(captures) != 1 or not observed:
        return None
    capture = captures[0]
    position, day = dated
    explicit_first = position < capture.start()
    left, right = sorted((position, capture.start()))
    if not re.search(r"\b(?:to|and|through|until|vs|versus|with|against)\b", question[left:right], re.I):
        return None
    label = capture[0].lower().split()[0]
    if _FIRST.match(label):
        reference = observed[0]
    elif label in {"previous", "prior", "preceding"}:
        # “Previous capture to February 1” refers to the capture preceding
        # the February endpoint. At the end of a range, “previous” uses the cutoff.
        eligible = observed if explicit_first else [stamp for stamp in observed if stamp <= day]
        if len(eligible) < 2:
            return None
        reference = eligible[-2]
    elif not re.search(r"\b(?:two|2)\b", capture[0], re.I):
        reference = observed[-1]
    else:
        return None
    return (day, reference) if explicit_first else (reference, day)


def _effective_view(history, base, requested, cutoff):
    """Only an explicitly backdated correction can revise an earlier inventory."""
    seen = set()
    amendments = []
    for view in history.views:
        if view.taken_on > cutoff:
            break
        for claim in view.claims:
            proof = claim.evidence
            if ((not proof.published_on or proof.published_on <= view.taken_on)
                    and proof.effective_from and proof.effective_from <= requested
                    and (not proof.effective_until or requested <= proof.effective_until)
                    and _CORRECTION.search(" ".join((*proof.headings, proof.quote, proof.title)))):
                # A new crawl of the same notice supplies no new amendment.
                content = replace(proof, snapshot_id="", taken_on="", fetched_at="")
                identity = (claim.key, claim.value, content)
                if identity not in seen and view.taken_on > base.taken_on:
                    amendments.append(claim)
                seen.add(identity)
    return replace(base, claims=base.claims + tuple(amendments)) if amendments else base


def answer_dated(history, question, as_of, answer_view):
    if not isinstance(question, str) or not question.strip() or not history.views:
        return Reply("I don't have enough information to answer that.", confident=False)
    latest = history.views[-1].taken_on
    change = _CHANGE.search(question)
    timeline = _TIMELINE.search(question)
    interval = _DATE_RANGE.search(question)
    try:
        cutoff = date.fromisoformat(as_of).isoformat() if as_of is not None else latest
        known_through = min(cutoff, latest)
        mentions = _dates(question, cutoff, known_through, bool(timeline))
        if interval and not timeline and not change and len(mentions) >= 2:
            mentions = _dates(question, cutoff, known_through, True)
        dates = [day for _, day in mentions]
    except (ValueError, TypeError, OverflowError):
        return Reply("I couldn't identify a valid date for that question.", confident=False)

    def endpoint(wanted):
        view = history.at(min(wanted, cutoff))
        if view is None:
            return Reply("There is no website capture for that date.", confident=False)
        if other_institution(question, view):
            return Reply("I can't verify that institution's information from this website.", confident=False)
        if _EFFECTIVE.search(question):
            view = _effective_view(history, view, wanted, known_through)
        # A query like "car APR in June 2025" has a capture year, not a model year.
        # Keep dates for prose announcements, where they may identify the event.
        scoped_question = question
        if dates and re.search(r"\b(?:auto|car|vehicle|motorcycle)\b", question, re.I):
            scoped_question = _DATE.sub(" ", question)
        result = answer_view(view, scoped_question, wanted)
        if wanted > known_through and result.confident:
            announced = any(
                (e.effective_until and wanted <= e.effective_until
                 and (not e.effective_from or e.effective_from <= wanted))
                or (e.effective_from and view.taken_on < e.effective_from <= wanted)
                or (re.search(r"\b(?:announced|scheduled)\b", result.text, re.I)
                    and re.search(r"\b(?:announced|will|scheduled)\b", e.quote, re.I)
                    and _DATE.search(e.quote))
                for e in result.sources)
            if not announced:
                return Reply(f"I can't verify that later date. The last available capture "
                             f"({view.taken_on}) reported: {result.text}", result.sources, False)
            result = replace(result, text=f"As recorded on {view.taken_on}: {result.text}")
        return result

    captures = list(_RELATIVE_CAPTURE.finditer(question))
    capture_range = captures and re.search(r"\b(?:between|from|since)\b", question, re.I)
    timeline = timeline or (interval and len(dates) >= 2 and not change)
    compare = capture_range or (change and (dates or captures or _UNDATED_CHANGE.search(question)))
    if not (timeline or compare):
        return endpoint(dates[-1] if dates else cutoff)

    observed = sorted({v.taken_on for v in history.views if v.taken_on <= cutoff})
    if len(dates) == 1 and captures:
        endpoints = _mixed_endpoints(question, mentions[0], captures, observed)
        if endpoints is None:
            return Reply("Please specify the two dates or captures to compare.", confident=False)
        start, finish = endpoints
    elif dates:
        start = dates[0]
        finish = dates[-1] if len(dates) > 1 else cutoff
    elif timeline and not captures:
        start, finish = history.views[0].taken_on, cutoff
    else:
        if len(observed) < 2:
            return Reply("I need two dated captures to compare the published values.", confident=False)
        previous = _PREVIOUS.search(question) and not _FIRST.search(question)
        start = observed[-2] if previous else observed[0]
        finish = observed[-1]
    if start > finish:
        if re.search(r"\b(?:between|versus|vs)\b|\bcompar\w*\b.*\b(?:against|with)\b", question, re.I):
            start, finish = finish, start
        else:
            return Reply("Please specify the earlier and later dates to compare.", confident=False)

    if timeline:
        points = sorted({start, finish, *(stamp for stamp in observed if start < stamp < finish)})
        observations = []
        last_state = None
        for point in points:
            reply = endpoint(point)
            state = reply.text, reply.confident
            if state != last_state:
                observations.append((point, reply))
                last_state = state
        return Reply(" ".join(f"{p}: {r.text}" for p, r in observations),
                     tuple(dict.fromkeys(e for _, r in observations for e in r.sources)),
                     confident=all(r.confident for _, r in observations),
                     conflict_note="Dates identify observations. The exact effective day may fall between captures.")

    first, last = endpoint(start), endpoint(finish)
    sources = tuple(dict.fromkeys((*first.sources, *last.sources)))
    if not (first.confident and last.confident):
        return Reply(f"I can't establish both endpoints. {start}: {first.text} {finish}: {last.text}",
                     sources, confident=False)
    return Reply(f"{start}: {first.text} {finish}: {last.text}", sources,
                 conflict_note="Each value is supported by the capture available at its endpoint.")
