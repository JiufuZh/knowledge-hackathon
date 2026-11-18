# System design

**Ingestion.** Each capture is a complete inventory. The system reuses extraction for unchanged pages from the preceding ingest, then attaches the new capture ID and fetch time. A failed ingest leaves the previous inventory available to readers. Markdown sections, plain-text labels, headers, rows and local footnotes supply context for structured claims. [History](knowledge/evidence.py) · [Extraction](knowledge/extract.py)

**Time.** A lookup selects the latest capture available by the requested date. A removed page can still support an earlier answer. Comparisons resolve both endpoints. Timelines visit intermediate captures, which matters when a rate changes and later returns to its original value. A later source can establish a retroactive correction only when the knowledge cutoff permits it. [Temporal queries](knowledge/temporal.py) · [Temporal tests](tests/test_temporal.py)

**Conflicts.** The resolver compares claims by institution, product, audience, measure and qualifying terms. Current branch schedules are compared by named branch, lobby or drive-up service, and weekday. Archived announcements can answer a dated question but do not establish a current schedule. The resolver checks eligibility and effective dates, keeps the evidence for unresolved disagreements and cites both dates when a value changes. [Resolution](knowledge/resolve.py) · [Rate and fee answers](knowledge/rates.py) · [Branch schedules](knowledge/branches.py)

**Member answers.** The answer layer interprets the question, selects the applicable evidence and returns a value, scoped list, clarification or abstention. Branch-specific and other narrative handlers read the selected capture. A lexical index built on demand searches eligible prose passages when the specialized handlers have no answer for the intent. [Query routing](knowledge/query.py) · [Branch answers](knowledge/branches.py) · [Passage search](knowledge/search.py)

The [contract](INTERFACES.md) defines what the organizer calls. The [acceptance cases](VALIDATION.md) link these design choices to executable checks.
