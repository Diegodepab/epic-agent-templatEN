# Scientific Paper Reading & Literature Synthesis Protocol

## 1. Per-Paper Evidence Folder (`papers/<citekey>/`)

Each paper read in a state-of-the-art study lives in its own folder:
- `source.json`: provenance emitted by `paper_tools.py fetch` (URL, SHA-256, license, retrieval date).
- `quotes.md`: verbatim quotes extracted with physical 1-indexed PDF page numbers:
  ```markdown
  ### Q1
  - page: 4
  > "Exact verbatim excerpt from the PDF."
  ```
- `quotes.verify.json`: cryptographic/text proof produced by `paper_tools.py verify <pdf> quotes.md`.
- `notes.md`: structured summary (problem, method, datasets, baselines, hyperparameters, limitations).
- `ACCESS_BLOCKED.md`: written when no legal full-text copy is available. **Never cite an `ACCESS_BLOCKED` paper as evidence** (`check_synthesis.py` blocks it).
- `REUSED.md`: links a paper already verified in another review via `path: ../other-review/papers/<citekey>`.

## 2. Verifiable Synthesis (`synthesis.md`)

1. Cite exact verified quotes using `[@citekey, p. N, Q3]` (or grouped `[@a, p. 2, Q1; @b, p. 7, Q4]`).
2. Mark explicit researcher inferences with `[INF]` so synthesis reasoning never disguises itself as a direct paper quote.
3. Under `## Answers`, `## Agreement and conflict`, `## Gaps`, and `## Plausibility`, every sentence of >=5 words must carry a verified citation or `[INF]`.
4. Populate an `## Evidence Matrix` table referencing verified `Q#` IDs per paper column.
5. Gate the review with `check_synthesis.py <review_dir>` before using any claim in experiment design or manuscript prose.
