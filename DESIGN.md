# Proposed solution

The system answers credit union members from the captures available on a requested date. A reviewer can run it offline with the original kit on Python 3.11. The public repository holds original code, synthetic tests and aggregate measurements.

## Contract and ownership

| Slice | Owner | Boundary |
| --- | --- | --- |
| S3 | Ingestion agent | `knowledge/evidence.py` and `knowledge/extract.py` produce immutable observations, dated inventories and searchable passages. |
| S4 | Resolution agent | `knowledge/resolve.py` groups comparable claims, selects evidence and explains conflicts. |
| S5 | Answer agent | `knowledge/query.py` parses member intent and renders supported answers, lists and refusals. |
| S6 | Integrator | Root `solution.py` exports `build()`; the returned object implements `ingest(snapshot)`, `answer(question, as_of=None)` and `conflicts()`. Use the grader's `contract` types at this boundary. |

The [implementation agreement](INTERFACES.md) defines the handoffs. Freeze one importable version of those shared types as the first implementation step. Each agent owns its module and synthetic tests. The integrator owns the adapter, combined tests and final measurements.

## Ingestion and time

Each snapshot is the entire site visible on its capture date. Store membership by snapshot, reuse parsing for identical content, and retain original URLs and raw text spans for citations. Resolve relative links against their page URL. Extract nearby headings, plain-text section labels, table headers, row and column labels, footnotes, list items and paragraphs. For table rows carry the product, metric, unit, qualifying ranges and boundaries, value and its supporting text. Keep the source class and any explicit validity window. Use an in-memory inverted index over section and claim terms.

Use the latest capture by default. The [date and comparison rules](INTERFACES.md#rules-reviewers-can-falsify) define the knowledge cutoff and how to select the view for a posted value, a fact's effective date, or a comparison. Before the first observation, abstain. After the last observation, indicate the observation date for time-sensitive facts. A published future event can answer a later-date question if the source states the event and its date. Never infer that a scheduled event actually occurred. Distinguish the capture date, page fetch timestamp, page publication date and effective dates on individual facts.

## Resolution and answers

A comparable key contains entity or branch, product and audience, requested measure, term, balance/amount range and other applicable selectors such as model year. Normalize units and aliases while preserving the original text. Partition simultaneous contradictory values from changes between observations. Record both types with typed reasons and source snapshots; successive identical evidence is one logical history. Compare current candidates for the same key by direct applicability, explicit validity and topic-specific authority. Examples include an active product rate table over a calculator, a branch's dated closure notice over generic hours, and an official schedule over editorial anecdotes. Return an unresolved conflict if equally credible sources disagree.

Parse intent, date, qualifiers and singular/list/comparison requests. Retrieve within the selected inventory, then require agreement between the requested entity, measure and qualifiers and the selected evidence. Rank passages for prose questions about eligibility, process, locations and links. A relevant page alone cannot support an unstated number or relationship. Render one resolved value per requested tier, complete scoped lists, or `confident=False` with the missing qualifier or evidence. Cite the original URL, snapshot and supporting quote. Keep competing values and the selection rationale in the conflict record. Explicit uncertainty should be understandable to a member.

## Ralph loop and acceptance

For each slice, record a reproducible failure, make one general change, rerun its regression and the affected integration checks, and update the logbook. Keep expected answers and scorer files outside the runtime. If the same failure persists after two different fixes, inspect the evidence chain and revise the hypothesis. If a fix sacrifices another supported behavior, reopen the slice.

Use the [review fixtures](VALIDATION.md) to test reasoning independently of public question wording. Run the unmodified organizer harness from an external kit on a fresh checkout. Require zero execution errors, ingestion within 30 minutes, every answer within 60 seconds and target p95 at most 2 seconds. Compare weighted accuracy against the starter and report category denominators, regressions and unresolved misses. Ship `requirements.txt`, `NOTES.md`, commands and a verified commit after integration.
