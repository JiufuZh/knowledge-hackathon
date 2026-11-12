# Implementation agreement

## Organizer boundary

The organizer imports a root `solution.py` and calls `build()` once. Ingestion runs sequentially in capture order. The grader calls `answer` from a worker thread, repeats a sample, and can call `conflicts()` after all snapshots. Import `Answer`, `Source` and `Conflict` from the grader-provided top-level `contract` module. The grader already adds the submission and harness directories to its import path. Python 3.11 and its standard library suffice.

| Call | Input | Result |
| --- | --- | --- |
| `ingest(snapshot)` | `snapshot_id`, ISO date `taken_on`, list of pages with `url, title, markdown, fetched_at` | `None`; publish the complete inventory after indexing succeeds. |
| `answer(question, as_of=None)` | Member's text and optional ISO calendar date | `Answer(text, sources, confident, conflict_note)`; abstain on unsupported scope, invalid cutoff or empty history. |
| `conflicts()` | No date argument | Full-history `list[Conflict(topic, values, sources, resolution, reason)]`. Preserve the connection between each distinct value and its evidence. |

Each supporting `Source` carries its original `url`, `snapshot_id` and a succinct verbatim `quote`. Internal evidence can retain multiple spans and provide more than one source when a row needs a separate heading, header or footnote to establish its meaning.

## Internal boundary

| Owner | Shared inputs and outputs |
| --- | --- |
| S3 | `FactKey(entity, product, audience, measure, qualifiers)` uses normalized strings and ordered qualifier pairs. Represent ranges with an axis, normalized unit, lower/upper bounds and inclusivity. `Evidence` holds snapshot ID and date, URL, class, title, heading path, exact spans and any publication/effective dates. `Claim` holds key, normalized value and evidence. `Inventory` holds membership, claims and passages. `History.add(snapshot)`, `History.at(cutoff)`, `History.between(start,end)` expose dated views. |
| S4 | `resolve(claims, requested_scope, effective_on)` returns a `Decision` with status (supported, insufficient, or disputed), winning claims, competing claims and a reason. `discover_conflicts(history)` returns qualified same-time disagreements and comparable changes on successive observations. Carry the distinction in the contract's reason field. |
| S5 | `answer_member(history, question, as_of)` owns intent parsing and response construction. It passes the question's resolved scope to S4 and renders the decision with S3's evidence. It can enumerate verified members of a tiered result, compare dated views, answer from a supported passage, or explain a refusal. |

Use the full URL, title, parser version and content digest when reusing parsed work that depends on those inputs. Attach capture membership and provenance anew for every observation. Each completed view is read-only. A reader sees a complete view even if a later ingest fails. Re-ingesting an identical snapshot is idempotent. Equal-authority ties keep both candidates; make output order deterministic by stable key, date, URL and span. Tests should exercise the adapter using the supplied harness from a separate directory.

## Rules reviewers can falsify

1. Treat `as_of` as a hard upper bound on what the system could know. For a plain historical lookup, use the last capture on or before the question's date, subject to the cutoff. With a June cutoff, “posted in March” uses the March view. “Effective in March” can use a June correction that explicitly covers March. With a March cutoff, a question about June receives only a clearly labeled announcement known by March or an abstention. Month-only “as of” uses calendar month end. Use capture calendar dates as supplied, with no conversion through the machine's local time zone.
2. For comparisons, select each endpoint independently within the cutoff and cite both. A gap bounds the observation of a change. A missing page gives no evidence about the day a policy ended. A new number in a new term or audience is a separate fact.
3. Filter by entity, requested measure, tier and applicability window before ranking authority. Resolve overlapping ranges at the requested point. Unknown bounds and ambiguous metrics cannot decide a conflict. Derive whether a boundary is inclusive from the site's text. Cite equal peers and abstain if the applicable evidence remains incompatible.
4. For lists, enumerate from the applicable canonical section and check scope and coverage. Return known members with an explicit limitation if completeness is unsupported. Never present a partial list as exhaustive. A missing qualifier can be answered conditionally when every applicable tier is known, or clarified when it changes the answer.
5. Keep stale values out of current-value answer text. Put the rationale in `conflict_note` and alternatives in `conflicts()`. A member explicitly asking what changed or which statements disagree can receive dated, labeled alternatives supported by separate citations.
