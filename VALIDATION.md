# Acceptance cases

Use invented facts for these tests. Check the returned answer, confidence, qualifier selection and citation spans. Each quote must be found verbatim in the cited capture's page. Change source values and page URLs to detect memorization. Keep the organizer kit and detailed outputs local.

| Slice | Synthetic fixture | Passing behavior |
| --- | --- | --- |
| S3 | January lists a page, February removes it, March restores it at a new URL with a changed value. | January and March cite their own URLs. A mid-February lookup abstains. Endpoint comparison cites both captures and bounds when the change was observed. |
| S3 | Same bytes appear under distinct headings or URLs, then in a new capture. A table follows a plain-text section label and contains a footnote. | Every claim retains the correct section, row, column, URL and capture. Changing an adjoining footnote changes only the facts in scope. |
| S4 | January publishes 4%. February explicitly corrects January to 5%. | A January cutoff cannot see February. With February evidence, “posted in January” yields 4% from January and “effective in January” yields 5% from the explicit correction. |
| S4 | An old schedule expires, a current table covers balances at or above $10,000, a calculator uses a sample rate, and new members qualify for a dated offer. | At the exact threshold the applicable table wins. Below it the high tier cannot answer. Existing members cannot receive a new-member offer. Unknown eligibility triggers a conditional answer or clarification. |
| S4 | Two equally authoritative pages disagree on the same tier. Another page has a different measure. A later snapshot changes the agreed rate. | The peer conflict preserves both citations and remains unresolved. Distinct metrics and missing pages yield zero false conflicts. Historical movement gets a dated change reason. |
| S5 | Three balance tiers share a product. Two unrelated products share a generic “loan” label. A directory puts branches in several sections. | List each savings tier on a broad product question. Ask which loan product is wanted. Enumerate the entire applicable branch directory or explicitly qualify a partial result. |
| S5 | Seven phrasings of one lookup, followed by minimal changes of entity, member type, metric or date. | Paraphrases yield the same fact and citations. Each material qualifier change selects its own evidence or yields an honest refusal. |
| S5 | A notice forecasts a closure after the capture date. An unrelated branch retains its own schedule. | Describe the dated announcement and its branch. Without later evidence, do not claim the closure was observed. |
| S6 | Clean Python 3.11 process, external harness, answer in a worker thread, repeat and reverse query order, replay a snapshot. | Contract types and answer content remain stable. No data bleed across questions. Replaying input does not duplicate conflicts. No network access or API keys required. |

## Evidence for a release

Record Python version, commit, capture and question counts, weighted accuracy, per-category counts and scores, repeat agreement, organizer p95 and maximum answer time, total ingestion time, and separately measured cold/warm timings and peak memory. Compare against the starter and the last passing candidate. Document each remaining miss with its cause locally. A speed change cannot silently regress a previously supported answer. As an engineering target, aim for at least 85% public weighted accuracy plus all synthetic invariants; a miss triggers another loop or an explicit scope decision. The organizer specifies no minimum accuracy.

The public set has 40 questions, one explicit date parameter, and no multi-question paraphrase groups. It provides no full-corpus conflict gold. Report synthetic conflict precision/recall against labeled fixtures, manually audit a sample of real conflicts locally, and distinguish paraphrase consistency from exact repeats. One free-text list item has no offline matching criterion. An independent completeness test covers that behavior. Hidden consistency and conflict performance remain unmeasured.
