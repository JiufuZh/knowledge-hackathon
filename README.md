# Knowledge Hackathon

This Python system answers credit union questions from five dated website captures. Each answer can include the original URL, capture ID and supporting quote. When the sources disagree, the system can explain which value applies or identify what it cannot verify.

## Run

Use Python 3.11. The repository root is the submission folder. The solution has no external dependencies or API keys. From the root, run the synthetic tests:

```shell
python -m unittest discover -s tests -v
```

Extract the organizer's participant kit separately. From the folder containing `harness/`, run the official scorer with the absolute path to this repository or the extracted submission ZIP:

```shell
python -X utf8 harness/run_eval.py --submission "/path/to/knowledge-hackathon" --eval eval/public_eval.jsonl
```

The harness supplies the contract module, unpacks the captures and writes detailed results locally. Replace the submission path with `starter` to reproduce the baseline. To check each emitted quote and compare responses in reverse question order, run this from the submission folder:

```shell
python -X utf8 tools/audit.py --kit "/path/to/hackathon-knowledge-kit-participant"
```

## Reviewer guide

- [Notes](NOTES.md) explain the evidence rules and tradeoffs.
- [Results](RESULTS.md) give the public score, timings and known misses.
- [Design](DESIGN.md) and [interfaces](INTERFACES.md) link behavior to the implementing modules.
- [Validation](VALIDATION.md), [reviews](REVIEW.md) and the [logbook](LOGBOOK.md) record how the solution was checked.
