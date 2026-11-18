# Interfaces

The organizer adds the submission and harness directories to the import path and calls `solution.build()`. The adapter converts internal replies and disagreements into the organizer's `Answer`, `Source` and `Conflict` objects. [Entry point](solution.py)

| Call | Behavior |
| --- | --- |
| `ingest(snapshot)` | Accepts a snapshot ID, ISO capture date and full page list. Publishes the inventory after extraction succeeds. Identical replays are idempotent. |
| `answer(question, as_of=None)` | Returns answer text, sources, confidence and an optional conflict note. The default view is the latest capture. |
| `conflicts()` | Returns discovered disagreements and observed changes, including competing values, sources, a resolution when available, and a reason. |

`History.at(cutoff)` selects the last capture on or before a date. `FactKey` stores the institution, product, audience, measure, qualifiers and range bounds. Each `Claim` has a textual value and one `Evidence` record. Each evidence record holds one verbatim quote and its provenance. An answer can cite several records. The resolver normalizes values for comparison. [Shared records](knowledge/schema.py) · [History](knowledge/evidence.py) · [Resolver](knowledge/resolve.py)

The `as_of` argument bounds which evidence is available. A date in the question can identify the requested fact. For example, a June cutoff permits a February correction when a member asks what was effective in January. The resolver considers the original schedule and any explicit amendments available by June. An official schedule retains priority over a newsroom correction. Among equally authoritative amendments, the most recently observed revision wins. Recapturing an unchanged notice preserves its original observation date. Asking what was posted in January selects the January view. A future closure notice supports a statement about the schedule. [Date handling](knowledge/temporal.py)

A month-only lookup uses the last day covered by the evidence window in that month. For an exact day beyond that window, the answer identifies what the last capture supports and whether it covers that day. “Before March 3” excludes March 3, and “before March” excludes all of March. A change question without dates compares the first and latest available captures. “Since the previous capture” compares the last two available by the cutoff. A range can combine a named capture with a date, such as “from the first capture to February 1.” A bare date interval or timeline also shows observed changes between its endpoints. [Temporal examples](tests/test_temporal.py) · [Acceptance cases](VALIDATION.md)
