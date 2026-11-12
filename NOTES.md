# Notes for the reviewer

The submission folder is the repository root. The organizer's runner supplies the `contract` module and loads `solution.py`. The runtime uses the Python 3.11 standard library. It needs no API keys, paid services, model downloads or network access.

**What counts as current.** Each ingest publishes a complete inventory. A date between captures selects the earlier capture. A page removed from the next inventory ceases to support a current answer. An omitted date selects the latest capture. For a comparison, the system resolves each endpoint independently. A later correction can revise an effective date when the source explicitly says so and the question's evidence cutoff permits it.

**How a value wins.** A rate observation keeps its entity, product, audience, metric, term, applicable range and original row. The resolver compares observations within that scope, checks the stated validity window, and considers the authority of the source. A rate schedule can establish an offer; a calculator example alone cannot. A conflict record includes the competing values, evidence and rationale. A change between dated observations carries a different explanation from a disagreement in one capture. An unresolved disagreement can produce an abstention with both sources.

**What a member sees.** Specific tier questions return the matching tier. A broader question can return a schedule or ask for a material missing qualifier. For narrative topics the engine reads branch directories, schedules, announcements and other attributed text. A lexical index provides an extractive fallback. Citations carry the original URL, capture ID and a verbatim excerpt. An undated or historic publication sometimes supports only a dated example.

**Tradeoffs.** This approach makes the evidence and decisions inspectable offline. New table layouts, unusual wording and facts spread across unrelated prose can still lead to missed answers or conflicts. The public scorer offers limited coverage of historical queries and paraphrases, and supplies no conflict key for the full site. The [test and evaluation instructions](README.md) let reviewers exercise those behaviors separately.
