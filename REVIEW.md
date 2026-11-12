# Architecture review

Three distinct OpenAI models independently reviewed the proposal. Each received the design and a brief covering the organizer's contract. Their feedback concerned the proposed design. Implementation and performance still require direct verification.

| Reviewer | Initial finding | Change accepted on re-review |
| --- | --- | --- |
| GPT-6-astra | A historical lookup, a retroactive correction and a comparison across two dates need different evidence. | Separate what the system could know from when a fact applied. Resolve and cite each endpoint. Filter out expired and out-of-tier claims before considering authority. |
| GPT-6.1-terra | Three agents could implement incompatible types or rely on state that is unavailable on the grader's worker thread. | Specify the organizer's types, freeze the internal interfaces before parallel work and use immutable completed inventories. Test a fresh process, repeated calls and worker-thread execution. |
| GPT-6.1-sol | An underspecified product may still support a useful list of tiers. Public repeat checks tell us little about paraphrases. | Distinguish useful conditional answers from unsupported completeness. Test paraphrases alongside nearly identical questions that change a material condition. Track accuracy regressions separately from speed. |

All three requested changes in round one and returned **proceed** after reading the revised design, interfaces and acceptance cases. The remaining documentation suggestion was incorporated as a link to the authoritative date rules in [the interface agreement](INTERFACES.md).

## Convergence checkpoint

The project owner selected a local agent simulation for the Jev checkpoint. Codex compared the review findings with the revised agreement and fixtures. The outcome was **ready for owner confirmation**. Each original blocker has a written rule, a test case and a reviewer recheck. Outstanding empirical questions include extraction coverage, conflict quality and generalization beyond the public set.

`mode=agent_simulation`, `model=Codex (GPT-6)`, `jev_called=false`, `probability=null`, `confidence=null`, `needs_review=true` (owner confirmation before implementation).

## Implementation review

The owner confirmed the design. Three agents built ingestion, resolution, and member answers. Two additional agents performed the required code review and simplification.

| Role | Outcome |
| --- | --- |
| Dedicated code reviewer | Reproduced six defects through the organizer's entry point. Fixes covered routing-number ownership and conflict citations, branch-specific closure dates, foreign-institution rates, product-specific links, future-dated publications, and a timeline that reversed direction. The reviewer reran the original cases. |
| Dedicated code simplifier | Refactored four modules for member answers, branch schedules and passage retrieval. Removed redundant lookup structures and clarified rankings and fallback selection. An A/B run compared all fields of all 40 public answers. Text, confidence, notes and citations matched exactly. |
| Independent acceptance tester | Initially passed 23 of 26 original scenarios. After fixes, all 26 passed. The three initial failures involved foreign institutions, new-member eligibility, and a link to the wrong product. |

The [regression suite](tests) contains reproductions of the release defects. The [acceptance cases](VALIDATION.md) describe the broader behaviors these checks protect.

After simplification, the dedicated code reviewer repeated all six original reproductions successfully. The final local checkpoint used the owner's selected simulation mode (`jev_called=false`, `probability=null`, `confidence=null`). Its release decision references the measured [clean-checkout results](RESULTS.md).
