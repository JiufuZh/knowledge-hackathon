# Release measurements

Tested implementation `9761e96165a8c9fc9ec9ae9c5f90547e56b14e05` on November 11, 2026, from a clean checkout in an isolated Windows Python 3.11.9 environment. The unmodified organizer harness loaded the submission from a separate participant-kit folder. Installation required no external packages.

## Public questions

The starter earned 9.30% weighted accuracy. The final implementation earned **93.64%**, or 60.4 of 64.5 weighted points. Of 40 questions, 36 received full credit, two partial credit and two zero. The scorer recorded zero execution errors and zero stale-value traps. The official p95 and maximum were both 0.21 seconds at the scorer's timing precision. All five snapshots finished ingesting in 15.8 seconds.

| Organizer category | Questions | Mean item score |
| --- | ---: | ---: |
| Branch information | 6 | 95% |
| Conflict-resolution questions | 3 | 100% |
| Current values | 3 | 100% |
| Entity attribution | 4 | 100% |
| List completeness | 4 | 75% |
| Appropriate refusal | 3 | 100% |
| Stale-value traps | 7 | 100% |
| Historical questions | 4 | 75% |
| Tier disambiguation | 6 | 100% |

Two branch-hours answers provided the expected information using different dated source pages. The offline scorer awards zero for one free-text list whose reference contains no matching tokens. A separate check matched all 12 published certificate offerings by term, variant and APY. One relative-year question expects an older workforce count. The system declines to present that count as the requested year's result.

## Independent checks

- All **54 repository tests** and **26 independent acceptance cases** passed. The dedicated code reviewer rechecked six defect reproductions after simplification. All 40 full public answer payloads were identical before and after the refactor.
- The organizer's 20 repeat checks agreed. A separate reverse-order pass reproduced the complete responses for all 40 questions. Seven synthetic paraphrases selected the same tier and evidence; changes to the account, metric or balance changed the result appropriately.
- The evidence audit validated 285,954 verbatim passages and the provenance of 6,316 structured observations. A second audit checked **890 emitted source records** across public answers and 312 reported conflicts or changes. It found zero unsupported quotes, citations after the explicit cutoff or uncited confident answers. Its first-pass and reverse-repeat p95 were 158 ms and 155 ms. Peak process memory, including the loaded kit, was 200.1 MiB.
- The organizer's small labeled conflict fixture yielded 1/1 match, precision, recall and F1 of 1.0, and the correct selected value. Its separate question set scored 4/5. The remaining question expects a fee from a page absent in the second full snapshot. The system abstains.

The full public corpus has no labeled conflict list, and its paraphrase groups each have one question. Full-corpus conflict precision, recall and hidden-set performance are unknown. [Reproduction commands](README.md)
