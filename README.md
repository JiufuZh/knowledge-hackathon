# Knowledge Hackathon

A credit union member asking about a rate needs the rate that applied to their product, balance and date. This offline Python system answers from dated website captures, shows the evidence and explains disagreements between sources.

The unchanged organizer scorer measured **93.64% weighted accuracy** across 40 practice questions, with zero execution errors and a 0.21-second p95 answer time. [Results and limitations](RESULTS.md)

## Run the solution

Use Python 3.11. The submission lives at the repository root. From that root, run the original synthetic tests:

```shell
python -m unittest discover -s tests -v
```

Extract the organizer-provided outer ZIP to a different folder. From the participant folder containing `harness/`, replace the example path with the absolute path to this checkout:

```shell
python -X utf8 harness/run_eval.py --submission "/path/to/knowledge-hackathon" --eval eval/public_eval.jsonl
```

The runner provides the contract types, unpacks the five captures on its first run, and writes detailed results locally. To check quotes against the original pages and compare answers in reverse question order, run the following from the solution checkout:

```shell
python -X utf8 tools/audit.py --kit "/path/to/hackathon-knowledge-kit-participant"
```

## Project documents

- [Solution design](DESIGN.md) covers the architecture, agent responsibilities and implementation loop.
- [Implementation agreement](INTERFACES.md) defines the organizer's entry point and how the three modules exchange evidence.
- [Acceptance cases](VALIDATION.md) describe the synthetic tests and the measurements needed for release.
- [Architecture review](REVIEW.md) records the three reviewers' findings and their second-round decisions.
- [Logbook](LOGBOOK.md) tracks verified progress and the next decision.
- [Reviewer notes](NOTES.md) explain how the running system chooses current evidence and where its coverage is limited.

## Reproduce the starter baseline

From the participant folder, run the original starter under the same scorer:

```shell
python -X utf8 harness/run_eval.py --submission starter --eval eval/public_eval.jsonl
```

The organizer's scorer unpacks the five captures on first run. Keep the kit and the generated per-question results local because they contain website content. Our baseline on Python 3.11.9 scored 9.3% weighted accuracy across 40 public questions, with zero execution errors.
