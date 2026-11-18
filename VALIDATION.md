# Validation

Run the [commands in the README](README.md) from the submission and participant-kit folders. The repository tests use invented pages and rates. The official scorer uses the five supplied captures.

| Behavior | What the check exercises |
| --- | --- |
| [Ingestion](tests/test_evidence.py) | Replay, failed ingest, page membership, changing URLs, table headings, row qualifiers, footnotes and citation provenance. |
| [Resolution](tests/test_resolution.py) | Tier boundaries, unit and metric differences, eligibility, peer disagreements, calculator examples and fee exceptions. |
| [Time](tests/test_temporal.py) | Posted and effective dates, cutoff enforcement, comparisons, and a timeline that returns to an earlier rate. |
| [Narrative answers](tests/test_answers.py) | Routing-number ownership, closure notices, branch directories, schedule scope and unsupported counts. |
| [Passage search](tests/test_search.py) | Extractive fallback, entity changes, expired evidence and exact citation spans. |
| [Integration](tests/test_integration.py) | Paraphrases, deliberately changed qualifiers, worker-thread queries and a page removed and later reintroduced. |

For release, run the unchanged organizer harness against a clean copy. Record the public score, question count, execution errors, stale-value traps, ingest time and answer latency. The organizer allows 30 minutes for ingestion and 60 seconds per answer. Its full speed credit starts at a p95 of two seconds or less.

The [evidence audit](tools/audit.py) checks emitted citations against the original pages and repeats every public question in reverse order. The optional organizer self-test supplies a small labeled conflict fixture. [Results](RESULTS.md) records each measurement and its limits.
