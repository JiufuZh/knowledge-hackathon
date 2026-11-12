"""Distinguish the requested effective date from the last evidence available."""
from __future__ import annotations

import calendar
import re
from dataclasses import replace
from datetime import date

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
                     r"rise|rose|fall|fell|history|timeline)\b", re.I)
_EFFECTIVE = re.compile(r"\b(?:effective|retroactiv\w*|actually applied|in effect)\b", re.I)
_CORRECTION = re.compile(r"\b(?:correct\w*|retroactiv\w*|amend\w*|restat\w*)\b", re.I)


def _dates(question, default_year):
    found = []
    for match in _DATE.finditer(question):
        if match["iso"]:
            found.append(date.fromisoformat(match["iso"]).isoformat())
            continue
        prefix = question[:match.start()]
        range_end = found and re.search(r"\b(?:and|to|through)\s*$", prefix, re.I)
        if not (match["year"] or match["day"] or _TIME_INTENT.search(prefix) or range_end):
            continue
        year = int(match["year"] or default_year)
        month = _MONTHS[match["month"].lower()]
        day = int(match["day"]) if match["day"] else calendar.monthrange(year, month)[1]
        found.append(date(year, month, day).isoformat())
    return found


def _effective_view(history, base, requested, cutoff):
    """Only an explicitly backdated correction can revise an earlier inventory."""
    changes = {}
    for view in history.views:
        if not base.taken_on < view.taken_on <= cutoff:
            continue
        candidates = {}
        for claim in view.claims:
            proof = claim.evidence
            if ((not proof.published_on or proof.published_on <= view.taken_on)
                    and proof.effective_from and proof.effective_from <= requested
                    and (not proof.effective_until or requested <= proof.effective_until)
                    and _CORRECTION.search(" ".join((*proof.headings, proof.quote, proof.title)))):
                candidates.setdefault(claim.key, []).append(claim)
        changes.update(candidates)
    if not changes:
        return base
    retained = tuple(c for c in base.claims if c.key not in changes)
    return replace(base, claims=retained + tuple(c for group in changes.values() for c in group))


def answer_dated(history, question, as_of, answer_view):
    if not isinstance(question, str) or not question.strip() or not history.views:
        return Reply("I don't have enough information to answer that.", confident=False)
    latest = history.views[-1].taken_on
    try:
        cutoff = date.fromisoformat(as_of).isoformat() if as_of is not None else latest
        dates = _dates(question, int(cutoff[:4]))
    except (ValueError, TypeError):
        return Reply("I couldn't identify a valid date for that question.", confident=False)

    def endpoint(wanted):
        view = history.at(min(wanted, cutoff))
        if view is None:
            return Reply("There is no website capture for that date.", confident=False)
        if other_institution(question, view):
            return Reply("I can't verify that institution's information from this website.", confident=False)
        if _EFFECTIVE.search(question):
            view = _effective_view(history, view, wanted, min(cutoff, latest))
        # A query like "car APR in June 2025" has a capture year, not a model year.
        # Keep dates for prose announcements, where they may identify the event.
        scoped_question = question
        if dates and re.search(r"\b(?:auto|car|vehicle|motorcycle)\b", question, re.I):
            scoped_question = _DATE.sub(" ", question)
        result = answer_view(view, scoped_question, wanted)
        if wanted > min(latest, cutoff) and result.confident:
            announced = any(
                (e.effective_until and wanted <= e.effective_until
                 and (not e.effective_from or e.effective_from <= wanted))
                or (e.effective_from and view.taken_on < e.effective_from <= wanted)
                or (re.search(r"\b(?:announced|scheduled)\b", result.text, re.I)
                    and re.search(r"\b(?:announced|will|scheduled)\b", e.quote, re.I)
                    and _DATE.search(e.quote))
                for e in result.sources)
            if dates and not announced:
                return Reply(f"I can't verify that later date. The last available capture "
                             f"({view.taken_on}) reported: {result.text}", result.sources, False)
            result = replace(result, text=f"As recorded on {view.taken_on}: {result.text}")
        return result

    timeline = re.search(r"\bover time\b|\btimeline\b|\bhistory\b|\bacross (?:the |all )?(?:captures|snapshots)\b", question, re.I)
    if timeline:
        start = dates[0] if dates else history.views[0].taken_on
        end = dates[-1] if len(dates) > 1 else cutoff
        if start > end:
            return Reply("Please specify the earlier and later dates.", confident=False)
        points = sorted({start, end, *(v.taken_on for v in history.views if start < v.taken_on < min(end, cutoff))})
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
    if _CHANGE.search(question) and dates:
        start = dates[0] if dates else history.views[0].taken_on
        finish = dates[-1] if len(dates) > 1 else cutoff
        if start > finish:
            return Reply("Please specify the earlier and later dates to compare.", confident=False)
        first, last = endpoint(start), endpoint(finish)
        sources = tuple(dict.fromkeys((*first.sources, *last.sources)))
        if not (first.confident and last.confident):
            return Reply(f"I can't establish both endpoints. {start}: {first.text} {finish}: {last.text}",
                         sources, confident=False)
        return Reply(f"{start}: {first.text} {finish}: {last.text}", sources,
                     conflict_note="Each value is supported by the capture available at its endpoint.")
    return endpoint(dates[-1] if dates else cutoff)
