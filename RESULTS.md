# Release measurements

On November 17, 2026, the unchanged organizer harness tested implementation `c0e34d6150305da662edfda45b0733cc62b50b3b` from an extracted Git archive under Python 3.11.9 on Windows. The participant kit was outside the submission folder. [Reproduction commands](README.md)

## Public score

**93.64% weighted accuracy** (60.4 of 64.5 points), compared with 9.30% for the starter. Of 40 questions, 36 received full credit, two partial credit and two zero. The scorer recorded zero execution errors and zero stale-value traps. The five snapshots loaded in 23.1 seconds. Answer latency was 0.14 seconds at p95 and 0.17 seconds maximum in this run.

| Category | Questions | Mean score |
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

Two branch-hours answers gave the expected information from different dated pages. One list question has no offline matching tokens. A separate check verified all 12 certificate offerings by term, variant and APY. A question about the previous year expects an older workforce count. The system explains which year the source supports.

## Independent checks

- All **67 repository tests**, 26 independent acceptance cases and 10 boundary checks passed. Three additional comparisons verified requests combining a calendar date with a named capture.
- All 40 complete public answers matched the November 11 release, including confidence flags, notes and citations. All 20 organizer repeat checks agreed, and reversing the order reproduced all 40 complete responses.
- All 285,954 stored passages matched their original text, and all 6,316 structured observations linked to verified passages. The [audit](tools/audit.py) checked 890 emitted source records across answers and 312 reported disagreements or changes. It found zero missing quotes, uncited confident answers or citations after the explicit cutoff. In this separate run, first-pass and repeat p95 were 200 ms and 194 ms. Peak process memory including the kit was 182.4 MiB.
- The organizer's small fixture had one labeled conflict. The system found it, selected the correct value and reported no extras. It scored 4/5 on the fixture's questions. The remaining question expects a fee from a page absent in the later capture.

The public set contains one explicit date parameter, singleton paraphrase groups and no labeled conflict list for the full site. Full-site conflict precision, recall and hidden-set performance remain unknown.
