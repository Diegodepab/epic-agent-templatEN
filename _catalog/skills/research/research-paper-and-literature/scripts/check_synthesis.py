#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Gate for a literature review's synthesis.md: every claim must rest on a verified quote.

Usage: ``uv run --script check_synthesis.py <review_dir>``. Citations have the form
``[@citekey, p. N, Q3]`` and may be grouped: ``[@a, p. 2, Q1; @b, p. 7, Q4]``. A paper read in another
review is linked by ``papers/<citekey>/REUSED.md`` containing a line ``path: <folder>``.

Checks:
1. every citation resolves to an existing quote, verified in a fresh ``quotes.verify.json`` with no
   duplicate IDs and no failed notes cross-check, on the cited page;
2. every sentence under Answers, Agreement and conflict, Gaps and Plausibility carries a citation or
   ``[INF]`` (gap sentences may cite the search log instead);
3. bare quote IDs in the evidence-matrix cells exist and are verified for that column's paper;
4. a quoted excerpt next to a citation ("…") occurs in the cited quote's text.
Exit 0 when all pass; 1 otherwise. Papers read but never cited are warnings.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

BRACKET = re.compile(r"\[([^\[\]]*@[^\[\]]*)\]")
QID = re.compile(r"(?<![\w-])Q\d+[a-z]?(?![\w-])")
PAGE = re.compile(r"\bpp?\.\s*(\d+)")
QUOTE_HEADER = re.compile(r"^#{2,4}\s*(Q[\w.-]+)\b")
PAGE_FIELD = re.compile(r"^\s*[-*]\s*page\s*:\s*(\d+)", re.I)
EXCERPT = re.compile(r"[\"“]([^\"”]{8,})[\"”]")
PROSE_SECTIONS = ("answers", "agreement", "gaps", "plausibility")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[*])")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.translate(str.maketrans({"“": '"', "”": '"', "’": "'", "–": "-", "−": "-"}))
    return " ".join(re.sub(r"[\"'`*]", "", text).split())


@dataclass
class PaperState:
    folder: Path | None
    quote_pages: dict[str, int | None] = field(default_factory=dict)
    quote_text: dict[str, str] = field(default_factory=dict)
    failed: set[str] = field(default_factory=set)
    problems: list[str] = field(default_factory=list)


def resolve_folder(review: Path, key: str) -> Path | None:
    folder = review / "papers" / key
    reused = folder / "REUSED.md"
    if reused.is_file():
        m = re.search(r"^\s*path\s*:\s*(.+?)\s*$", reused.read_text(encoding="utf-8"), re.M)
        return Path(m.group(1)).expanduser() if m else None
    return folder if folder.is_dir() else None


def load_paper(review: Path, key: str) -> PaperState:
    folder = resolve_folder(review, key)
    st = PaperState(folder)
    if folder is None or not folder.is_dir():
        st.problems.append("no paper folder (papers/<key>/ or REUSED.md path)")
        return st
    quotes, verify = folder / "quotes.md", folder / "quotes.verify.json"
    if (folder / "ACCESS_BLOCKED.md").is_file() and not (folder / "notes.md").is_file():
        st.problems.append("paper is BLOCKED (never read); it cannot be cited as evidence")
    if not quotes.is_file():
        st.problems.append("no quotes.md")
        return st
    current = None
    for line in quotes.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            m = QUOTE_HEADER.match(line)
            current = m.group(1) if m else None
            if current:
                st.quote_pages[current], st.quote_text[current] = None, ""
        elif current and (m := PAGE_FIELD.match(line)):
            st.quote_pages[current] = int(m.group(1))
        elif current and line.lstrip().startswith(">"):
            st.quote_text[current] += " " + line.lstrip()[1:]
    if not verify.is_file():
        st.problems.append("quotes never verified (no quotes.verify.json)")
        return st
    if quotes.stat().st_mtime > verify.stat().st_mtime + 1:
        st.problems.append("stale verification: quotes.md changed after quotes.verify.json")
    data = json.loads(verify.read_text(encoding="utf-8"))
    st.failed = {f["qid"] for f in data.get("failures", [])}
    if data.get("duplicate_ids"):
        st.problems.append(f"duplicate quote IDs: {data['duplicate_ids']}")
    notes = data.get("notes") or {}
    for k in ("cited_but_missing", "cited_but_unverified", "numbers_not_in_quotes"):
        if notes.get(k):
            st.problems.append(f"its notes failed verification ({k}: {notes[k]})")
    if not notes:
        st.problems.append("verify was run without --notes; re-run it with --notes notes.md")
    return st


def check_qid(st: PaperState, key: str, q: str, page: int | None, where: str) -> list[str]:
    if q not in st.quote_pages:
        return [f"{where}: {q} does not exist in {key}/quotes.md"]
    if q in st.failed:
        return [f"{where}: {q} failed verification"]
    if page is not None and st.quote_pages[q] not in (None, page):
        return [f"{where}: page {page} but {q} is on page {st.quote_pages[q]}"]
    return []


def sections(text: str) -> list[tuple[str, int, str]]:
    """(lower-cased level-2 heading, line number, line) for every line under each ## heading."""
    out, head = [], ""
    for i, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            head = line[3:].strip().casefold()
        out.append((head, i, line))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate for a literature review's synthesis.md: verify every claim rests on a verified quote."
    )
    parser.add_argument("review_dir", type=Path, help="Literature review directory containing synthesis.md and papers/")
    args = parser.parse_args()
    review = args.review_dir.expanduser().resolve()
    synth = review / "synthesis.md"
    if not synth.is_file():
        print(f"ERROR: {synth} not found")
        return 1
    text = synth.read_text(encoding="utf-8")
    papers: dict[str, PaperState] = {}
    errors: list[str] = []
    n_cites = 0
    cited: set[str] = set()

    def paper(key: str) -> PaperState:
        return papers.setdefault(key, load_paper(review, key))

    in_comment = False
    matrix_cols: list[str] = []
    for head, lineno, line in sections(text):
        if "<!--" in line:
            in_comment = True
        if in_comment:
            in_comment = "-->" not in line
            continue
        # 1. bracketed citations (+ 4. excerpts next to them)
        for m in BRACKET.finditer(line):
            for part in m.group(1).split(";"):
                part = part.strip()
                km = re.match(r"@([\w:.-]+)", part)
                if not km:
                    continue
                key, qids = km.group(1), QID.findall(part)
                pm = PAGE.search(part)
                page = int(pm.group(1)) if pm and len(qids) == 1 else None
                st, where = paper(key), f"synthesis.md:{lineno} [{part}]"
                n_cites += 1
                cited.add(key)
                errors += [f"{where}: {p}" for p in st.problems]
                if not qids:
                    errors.append(f"{where}: no quote ID; cite a verified quote (Qn)")
                for q in qids:
                    errors += check_qid(st, key, q, page, where)
                tail = line[m.end():m.end() + 300]
                ex = EXCERPT.search(tail)
                if ex and len(qids) == 1 and qids[0] in st.quote_text \
                        and norm(ex.group(1).strip(" .…")) not in norm(st.quote_text[qids[0]]):
                    errors.append(f"{where}: excerpt \"{ex.group(1)[:60]}\" is not in {qids[0]}'s text")
        # 3. evidence matrix: bare quote IDs resolved against the column's paper
        if head.startswith("evidence matrix") and line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if not matrix_cols:
                matrix_cols = [c.strip("`@ ") for c in cells]
                continue
            for col, cell in zip(matrix_cols[1:], cells[1:], strict=False):
                for q in QID.findall(cell):
                    if "[@" in cell:
                        continue
                    st = paper(col)
                    cited.add(col)
                    where = f"synthesis.md:{lineno} matrix[{cells[0]} × {col}]"
                    errors += [f"{where}: {p}" for p in st.problems] + check_qid(st, col, q, None, where)
        # 2. uncited prose in the evidence sections
        if any(head.startswith(s) for s in PROSE_SECTIONS) and line.strip() \
                and not line.lstrip().startswith(("|", "#", "**Certainty", "<!--")):
            body = re.sub(r"^\s*[-*]\s+|\*\*[^*]+\*\*\s*", "", line)
            for sentence in SENTENCE_SPLIT.split(body):
                words = re.findall(r"[A-Za-z]{2,}", sentence)
                supported = "[@" in sentence or "[INF]" in sentence or (
                    head.startswith("gaps") and re.search(r"search-log|quer(y|ies) #", sentence))
                if len(words) >= 5 and not supported:
                    errors.append(f"synthesis.md:{lineno}: uncited sentence: \"{sentence.strip()[:80]}\"")

    errors = list(dict.fromkeys(errors))
    included = {p.name for p in (review / "papers").iterdir()
                if p.is_dir() and ((p / "notes.md").is_file() or (p / "REUSED.md").is_file())} \
        if (review / "papers").is_dir() else set()
    print(f"citations: {n_cites} · papers cited: {len(cited)} · errors: {len(errors)}")
    for e in errors:
        print(f"ERROR  {e}")
    for k in sorted(included - cited):
        print(f"WARN   included but never cited in the synthesis: {k}")
    return 1 if errors or not n_cites else 0


if __name__ == "__main__":
    sys.exit(main())
