---
name: research-paper-and-literature
description: Fetches legal open-access PDFs (arXiv, DOI, Unpaywall), extracts 1-indexed physical PDF pages, verifies verbatim quotes against source PDFs into quotes.verify.json, and gates literature review synthesis.md documents so every claim rests on a verified quote citation. Use when reading scientific papers, extracting state-of-the-art baselines, or building verifiable literature reviews. Not for web scraping or code formatting.
---

# Research Paper and Literature Verification

Ground every literature claim, baseline metric, and state-of-the-art comparison in verifiable PDF page citations rather than model memory. Treat scripts under `scripts/` as black boxes: run `--help` first instead of reading script internals.

## Decision Tree

- **Need to obtain a paper legally and extract real 1-indexed PDF pages?** -> Run `paper_tools.py fetch` (pass `--email "$RESEARCH_CONTACT_EMAIL"` when querying Unpaywall) followed by `paper_tools.py extract <pdf> --out <dir>`
- **Extracted quotes from a paper into `quotes.md`?** -> Run `paper_tools.py verify <pdf> <quotes.md>` to emit `quotes.verify.json` proving every verbatim quote exists on the cited physical page
- **Writing or auditing a multi-paper `synthesis.md` or evidence matrix?** -> Run `check_synthesis.py <review_dir>` to verify every citation (`[@citekey, p. N, Q#]`), block uncited claims, and reject citations to `ACCESS_BLOCKED.md` papers
- **Want the full folder convention (`papers/<citekey>/`, `quotes.md`, `synthesis.md`)?** -> Read `references/reading-and-synthesis-protocol.md`

## What Lives Where

| Artifact | Purpose | Output / Gate |
|---|---|---|
| `scripts/paper_tools.py` | Legal paper fetch, 1-indexed PDF extraction (`pymupdf`), verbatim quote verifier & highlighter | Extracted pages + `quotes.verify.json` |
| `scripts/check_synthesis.py` | Zero-dependency gate enforcing verified `[@citekey, p. N, Q#]` citations across `synthesis.md` | Exit `0` / `1` + uncited claim report |
| `references/reading-and-synthesis-protocol.md` | Folder layout, quote ID schema (`Q1..Qn`), `REUSED.md` links, and anti-hallucination rules | Verifiable literature review workflow |

## Commands

```bash
python3 .agents/skills/research-paper-and-literature/scripts/paper_tools.py --help
python3 .agents/skills/research-paper-and-literature/scripts/check_synthesis.py --help
python3 .agents/skills/research-paper-and-literature/scripts/paper_tools.py extract paper.pdf --out papers/smith2025
python3 .agents/skills/research-paper-and-literature/scripts/paper_tools.py verify paper.pdf papers/smith2025/quotes.md
python3 .agents/skills/research-paper-and-literature/scripts/check_synthesis.py literature/sota-review
```
