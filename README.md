# Knowledge Hackathon

A credit union member asking about a rate needs the rate that applied to their product, balance and date. This project builds an offline Python system that answers from dated website captures, shows the evidence and explains disagreements between sources.

## Project documents

- [Solution design](DESIGN.md) covers the architecture, agent responsibilities and implementation loop.
- [Implementation agreement](INTERFACES.md) defines the organizer's entry point and how the three modules exchange evidence.
- [Acceptance cases](VALIDATION.md) describe the synthetic tests and the measurements needed for release.
- [Architecture review](REVIEW.md) records the three reviewers' findings and their second-round decisions.
- [Logbook](LOGBOOK.md) tracks verified progress and the next decision.

## Reproduce the starter baseline

Use Python 3.11 and an organizer-provided participant kit. Extract the outer ZIP to a local folder outside the checkout. From the folder that contains `harness/`, run:

```shell
python -X utf8 harness/run_eval.py --submission starter --eval eval/public_eval.jsonl
```

The organizer's scorer unpacks the five captures on first run. Keep the kit and the generated per-question results local because they contain website content. Our baseline on Python 3.11.9 scored 9.3% weighted accuracy across 40 public questions, with zero execution errors.
