# Interfaces

The organizer adds the submission and harness directories to the import path and calls `solution.build()`. The adapter converts internal replies and disagreements into the organizer's `Answer`, `Source` and `Conflict` objects. [Entry point](solution.py)

| Call | Behavior |
| --- | --- |
| `ingest(snapshot)` | Accepts a snapshot ID, ISO capture date and full page list. Publishes the inventory after extraction succeeds. Identical replays are idempotent. |
| `answer(question, as_of=None)` | Returns answer text, sources, confidence and an optional conflict note. The default view is the latest capture. |
| `conflicts()` | Returns discovered disagreements and observed changes, including competing values, sources, a resolution when available, and a reason. |

`History.at(cutoff)` selects the last capture on or before a date. `FactKey` stores the institution, product, audience, measure, qualifiers and range bounds. Each `Claim` has a textual value and one `Evidence` record. Each evidence record holds one verbatim quote and its provenance. An answer can cite several records. The resolver normalizes values for comparison. [Shared records](knowledge/schema.py) · [History](knowledge/evidence.py) · [Resolver](knowledge/resolve.py)

The `as_of` argument bounds which evidence is available. A date in the question can identify the requested fact. For example, a June cutoff permits a February correction when a member asks what was effective in January. Asking what was posted in January selects the January view. A future closure notice supports a statement about the schedule. [Date handling](knowledge/temporal.py) · [Acceptance cases](VALIDATION.md)
