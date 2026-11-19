#!/usr/bin/env python3
"""Mechanical gate (G1) for LaTeX manuscript sections in a paper-writing run.

Checks one or more section files, read in the order given:

  citations     every \\cite key exists in the .bib (fail); keys without a reading on record (warn)
  numbers       every reported number appears in numbers.md (fail)
  glossary      no "Do not use" variant from glossary.md appears in the prose (fail)
  references    \\ref-family targets have a \\label in the paper (warn; fail with --final)
  placeholders  [AUTHOR: ...], [PENDING ...], [CITE: ...], \\todo, TODO, XXX, ?? (info; fail with --final)
  floats        each figure/table has \\caption and \\label, and the label is referenced (warn)
  math          sentences starting with a symbol, > 2 inline formulas in a sentence, unpunctuated
                displays, numbered equations without a label or never referenced (warn)
  length        prose words against --budget (fail above 110 %, warn below 80 %)
  clarity       long sentences, long paragraphs, acronyms before definition or rarely used (warn)

Exit status: 0 when no check failed (warnings allowed), 1 when a check failed, 2 on an input error.
Standard library only. Heuristic by design: a warning is a prompt to look, not a verdict.
"""

from __future__ import annotations

import argparse
import enum
import re
import statistics
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

# Default clarity thresholds. Sentences above ~40 words and paragraphs above ~220 words are where
# readers of scientific prose start to lose the thread; both are warnings, never failures.
DEFAULT_MAX_SENTENCE_WORDS = 40
DEFAULT_MAX_PARAGRAPH_WORDS = 220
BUDGET_FAIL_RATIO = 1.10
BUDGET_WARN_RATIO = 0.80
MIN_ACRONYM_USES = 3
YEAR_RANGE = range(1900, 2100)

CITE_RE = re.compile(
    r"\\(?:no)?(?:cite|citep|citet|citealp|citeauthor|citeyear|parencite|textcite|autocite"
    r"|footcite|smartcite)\*?(?:\[[^\]]*\]){0,2}\{([^}]*)\}"
)
REF_RE = re.compile(r"\\(?:ref|cref|Cref|autoref|eqref|pageref|vref|nameref|labelcref)\*?\{([^}]*)\}")
REF_RANGE_RE = re.compile(r"\\(?:crefrange|Crefrange)\*?\{([^}]*)\}\{([^}]*)\}")
LABEL_RE = re.compile(r"\\label\{([^}]*)\}")
# listings sets its label through an option: \begin{lstlisting}[..., label={lst:x}] or \lstinputlisting[label=lst:x]{f}
OPTION_LABEL_RE = re.compile(r"\\(?:begin\{lstlisting\}|lstinputlisting)\[[^\]]*?\blabel\s*=\s*\{?([^,}\]\s]+)")


def find_labels(text: str) -> list[str]:
    """Return every label defined in ``text``, by ``\\label`` or by a listings ``label=`` option."""
    return LABEL_RE.findall(text) + OPTION_LABEL_RE.findall(text)
BIB_KEY_RE = re.compile(r"@(?!comment|string|preamble)\w+\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)
FLOAT_RE = re.compile(r"\\begin\{(figure|table|algorithm)(\*?)\}(.*?)\\end\{\1\2\}", re.DOTALL)
DISPLAY_MATH_RE = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray|displaymath|flalign)(\*?)\}.*?\\end\{\1\2\}"
    r"|\\\[.*?\\\]|\$\$.*?\$\$",
    re.DOTALL,
)
INLINE_MATH_RE = re.compile(r"(?<!\\)\$[^$]+?(?<!\\)\$|\\\(.*?\\\)", re.DOTALL)
PLACEHOLDER_RES = {
    "AUTHOR": re.compile(r"\[AUTHOR:"),
    "PENDING": re.compile(r"\[PENDING\b"),
    "CITE": re.compile(r"\[CITE:"),
    "todo": re.compile(r"\\todo\b|\bTODO\b|\bXXX\b|\?\?"),
}
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.\\])\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![A-Za-z0-9_])")
ACRONYM_RE = re.compile(r"\b([A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*?)(s?)\b")
ROMAN_RE = re.compile(r"^[IVXLC]+$")
ABBREVIATIONS = ("e.g.", "i.e.", "et al.", "Fig.", "Figs.", "Eq.", "Eqs.", "Sec.", "Secs.",
                 "vs.", "cf.", "approx.", "resp.", "Ref.", "Refs.", "No.", "Tab.", "etc.")
SENTENCE_END_RE = re.compile(r"(?<=[.!?])[\")\]]*\s+(?=[A-Z0-9\\(\"])")

# Plain-text stand-ins for removed LaTeX: lower-case words, so that they count as one word each
# and are never mistaken for acronyms.
MATH_TOKEN = "mathexpr"
DISPLAY_TOKEN = "displayeq"
REF_TOKEN = "refx"


class CheckInputError(Exception):
    """Raised when an input file is missing or cannot be parsed."""


class Level(enum.IntEnum):
    """Severity of a finding; the highest level decides the exit status."""

    PASS = 0
    INFO = 1
    WARN = 2
    FAIL = 3


@dataclass(frozen=True)
class Finding:
    """One line of the report."""

    check: str
    level: Level
    message: str


@dataclass(frozen=True)
class TexSource:
    """A section file with comments removed, keeping line numbers intact."""

    path: Path
    text: str

    def line_of(self, offset: int) -> int:
        """Return the 1-based line number of a character offset in ``text``."""
        return self.text.count("\n", 0, offset) + 1


@dataclass
class Options:
    """Validated command-line options."""

    tex: list[Path]
    paper_root: Path
    bibs: list[Path] = field(default_factory=list)
    verified_keys: Path | None = None
    numbers: Path | None = None
    glossary: Path | None = None
    budget: int | None = None
    max_sentence: int = DEFAULT_MAX_SENTENCE_WORDS
    max_paragraph: int = DEFAULT_MAX_PARAGRAPH_WORDS
    final: bool = False
    check_years: bool = False


# ----------------------------------------------------------------------------- reading


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as err:
        raise CheckInputError(f"cannot read {path}: {err}") from err


def strip_comments(text: str) -> str:
    """Remove LaTeX comments (unescaped ``%`` to end of line), keeping every newline."""
    return re.sub(r"(?<!\\)%[^\n]*", "", text)


def load_tex(path: Path) -> TexSource:
    """Read a .tex file and strip its comments."""
    return TexSource(path=path, text=strip_comments(_read(path)))


def _sub_keep_lines(pattern: re.Pattern[str], token: str, text: str) -> str:
    """Replace each match by ``token`` plus as many newlines as the match spanned."""
    return pattern.sub(lambda m: f" {token} " + "\n" * m.group(0).count("\n"), text)


def _display_closing_punctuation(display: str) -> str:
    """Return the punctuation that ends a displayed equation (``.``, ``,``, ``;``), or ``""``."""
    body = re.sub(r"\\end\{[^}]*\}\s*$|\\\]\s*$|\$\$\s*$", "", display.rstrip())
    body = re.sub(r"\\label\{[^}]*\}|\\nonumber|\\notag|\\\\|\s", "", body)
    return body[-1] if body and body[-1] in ".,;" else ""


def _replace_displays(text: str) -> str:
    """Replace displayed maths by a one-word token that keeps its closing punctuation and lines.

    Keeping the full stop matters: a display that ends a sentence must still end it, or the
    sentence before the display and the one after it are read as one.
    """
    return DISPLAY_MATH_RE.sub(
        lambda m: f" {DISPLAY_TOKEN}{_display_closing_punctuation(m.group(0))} " + "\n" * m.group(0).count("\n"),
        text,
    )


def to_plain_text(text: str) -> str:
    """Approximate the prose a reader sees, line-aligned with the source.

    Floats are removed, display maths and inline maths become one-word tokens, citations disappear,
    references become a token, and command arguments that carry text are kept.
    """
    text = FLOAT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    text = re.sub(r"\[(?:AUTHOR|PENDING|CITE)\b[^\]]*\]", "", text)
    text = _replace_displays(text)
    text = _sub_keep_lines(INLINE_MATH_RE, MATH_TOKEN, text)
    text = CITE_RE.sub("", text)
    text = REF_RANGE_RE.sub(f" {REF_TOKEN} ", text)
    text = REF_RE.sub(f" {REF_TOKEN} ", text)
    text = re.sub(r"\\(?:label|url|input|include|includegraphics|begin|end)\*?(?:\[[^\]]*\])?\{[^}]*\}", "", text)
    text = re.sub(r"\\href\{[^}]*\}", "", text)
    for _ in range(3):  # unwrap nested text-carrying commands such as \emph{\textbf{x}}
        text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[A-Za-z]+\*?", " ", text)
    text = text.replace("~", " ").replace("{", "").replace("}", "").replace("\\\\", " ")
    return text


# ----------------------------------------------------------------------------- side files


def load_bib_keys(paths: Iterable[Path]) -> set[str]:
    """Return every entry key defined in the given .bib files."""
    keys: set[str] = set()
    for path in paths:
        keys.update(BIB_KEY_RE.findall(_read(path)))
    return keys


def _table_rows(text: str) -> Iterator[list[str]]:
    """Yield the cells of every markdown table row, skipping separator rows."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        yield cells


def _is_template_cell(cell: str) -> bool:
    return not cell or cell.startswith("<") or cell in {"—", "-", "none"}


def normalise_number(token: str) -> str:
    """Canonical form for matching: no sign, no thousands separators."""
    return token.lstrip("+-−")


def _clean_numeric_text(text: str) -> str:
    text = text.replace("{,}", "").replace("\\,", "").replace("\\!", "").replace("−", "-")
    return re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", text)


def load_ledger_values(path: Path) -> set[str]:
    """Collect every number written in the second column of the numbers ledger."""
    values: set[str] = set()
    for cells in _table_rows(_read(path)):
        if len(cells) < 2 or cells[0].lower() == "id" or _is_template_cell(cells[1]):
            continue
        cleaned = re.sub(r"[_^](\{[^{}]*\}|\\?\w)", " ", _clean_numeric_text(cells[1]))
        values.update(normalise_number(m.group(0)) for m in NUMBER_RE.finditer(cleaned))
    return values


def load_forbidden_variants(path: Path) -> dict[str, str]:
    """Map each "Do not use" variant in the glossary to its preferred term."""
    variants: dict[str, str] = {}
    column: int | None = None
    for cells in _table_rows(_read(path)):
        lowered = [c.lower() for c in cells]
        if "do not use" in lowered:
            column = lowered.index("do not use")
            continue
        if column is None or len(cells) <= column or column == 0:
            continue
        if any(c.lower() in {"acronym", "symbol"} for c in cells[:1]):
            column = None
            continue
        for variant in cells[column].split(";"):
            variant = variant.strip()
            if not _is_template_cell(variant):
                variants[variant] = cells[0]
    return variants


# ----------------------------------------------------------------------------- numbers


def _blank(match: re.Match[str]) -> str:
    """Replace a match by spaces of equal length, so that offsets stay aligned with the source."""
    return re.sub(r"[^\n]", " ", match.group(0))


def extract_numbers(text: str, *, check_years: bool) -> Iterator[tuple[str, int]]:
    """Yield (number, line) for every reportable number in LaTeX source.

    Reportable: decimals, scientific notation, percentages and integers of 10 or more. Small
    integers, years (unless ``check_years``), sub- and superscripts, lengths, identifiers
    (``T1``, ``3D``, ``BraTS2021``), citation, reference and label arguments are skipped.
    """
    blank = _blank
    text = CITE_RE.sub(blank, text)
    text = REF_RANGE_RE.sub(blank, text)
    text = REF_RE.sub(blank, text)
    text = re.sub(r"\\(?:label|url|href|input|include|begin|end|cmidrule|multicolumn|multirow"
                  r"|setlength|vspace|hspace|addlinespace)\*?(?:\([^)]*\))?(?:\[[^\]]*\])?\{[^}]*\}", blank, text)
    text = re.sub(r"\\includegraphics\*?(?:\[[^\]]*\])?\{[^}]*\}", blank, text)
    text = re.sub(r"(?<=[\[{=,])\s*-?\d*\.?\d+\s*(?:cm|mm|pt|em|ex|in|bp|\\(?:line|text|column)width)", blank, text)
    text = re.sub(r"\\\\\[[^\]]*\]", blank, text)
    text = re.sub(r"[_^](\{[^{}]*\}|\\?\w)", blank, text)
    # Thousands separators are removed outright; they never span a newline, so line numbers hold.
    text = re.sub(r"(?<=\d)(?:\{,\}|\\,|\\!|,(?=\d{3}(?!\d)))(?=\d)", "", text)
    for match in NUMBER_RE.finditer(text):
        token = match.group(0)
        tail = text[match.end(): match.end() + 2]
        is_percent = tail.startswith("\\%") or tail.startswith("%")
        is_decimal = "." in token or "e" in token.lower()
        if not (is_decimal or is_percent):
            value = int(token)
            if value < 10 or (not check_years and value in YEAR_RANGE and len(token) == 4):
                continue
        yield normalise_number(token), text.count("\n", 0, match.start()) + 1


# ----------------------------------------------------------------------------- checks


def _lines(items: Iterable[str], limit: int = 12) -> str:
    items = list(items)
    shown = ", ".join(items[:limit])
    return shown + (f", … (+{len(items) - limit})" if len(items) > limit else "")


def check_citations(sources: list[TexSource], opts: Options) -> list[Finding]:
    """Cited keys must exist in the .bib; keys without a reading on record are flagged."""
    cited: list[tuple[str, str]] = []
    for src in sources:
        for match in CITE_RE.finditer(src.text):
            for key in match.group(1).split(","):
                if key.strip():
                    cited.append((key.strip(), f"{src.path.name}:{src.line_of(match.start())}"))
    if not opts.bibs:
        return [Finding("citations", Level.INFO, f"{len(cited)} citations; no --bib given, not checked")]
    bib_keys = load_bib_keys(opts.bibs)
    missing = [f"{k} ({loc})" for k, loc in cited if k not in bib_keys]
    findings = [Finding("citations", Level.FAIL, f"{len(missing)} keys not in the .bib: {_lines(missing)}")
                if missing else Finding("citations", Level.PASS, f"{len(cited)} citations, all keys in the .bib")]
    if opts.verified_keys:
        record = set(re.findall(r"[A-Za-z0-9_:\-]+", _read(opts.verified_keys)))
        unread = sorted({k for k, _ in cited if k not in record})
        if unread:
            findings.append(Finding("citations", Level.WARN,
                                    f"{len(unread)} keys without a reading on record: {_lines(unread)}"))
    return findings


def check_numbers(sources: list[TexSource], opts: Options) -> list[Finding]:
    """Every reportable number must appear in the numbers ledger."""
    if not opts.numbers:
        return [Finding("numbers", Level.INFO, "no --numbers ledger given, not checked")]
    ledger = load_ledger_values(opts.numbers)
    found = [(num, f"{src.path.name}:{line}")
             for src in sources for num, line in extract_numbers(src.text, check_years=opts.check_years)]
    missing = [f"{num} ({loc})" for num, loc in found if num not in ledger]
    if missing:
        return [Finding("numbers", Level.FAIL, f"{len(missing)} of {len(found)} numbers not in the ledger: "
                        f"{_lines(missing)}")]
    return [Finding("numbers", Level.PASS, f"{len(found)} numbers, all in the ledger")]


def check_glossary(sources: list[TexSource], plains: list[str], opts: Options) -> list[Finding]:
    """No variant marked "Do not use" may appear in the prose."""
    if not opts.glossary:
        return [Finding("glossary", Level.INFO, "no --glossary given, not checked")]
    variants = load_forbidden_variants(opts.glossary)
    hits: list[str] = []
    for src, plain in zip(sources, plains):
        for variant, term in variants.items():
            pattern = re.compile(r"\b" + r"\s+".join(map(re.escape, variant.split())) + r"\b", re.IGNORECASE)
            for match in pattern.finditer(plain):
                hits.append(f"'{match.group(0)}' → '{term}' ({src.path.name}:{plain.count(chr(10), 0, match.start()) + 1})")
    if hits:
        return [Finding("glossary", Level.FAIL, f"{len(hits)} forbidden variants: {_lines(hits)}")]
    return [Finding("glossary", Level.PASS, f"0 of {len(variants)} forbidden variants used")]


def _paper_labels_and_refs(root: Path) -> tuple[set[str], set[str]]:
    labels: set[str] = set()
    refs: set[str] = set()
    for path in root.rglob("*.tex"):
        text = strip_comments(_read(path))
        labels.update(find_labels(text))
        for match in REF_RE.finditer(text):
            refs.update(k.strip() for k in match.group(1).split(","))
        for match in REF_RANGE_RE.finditer(text):
            refs.update((match.group(1).strip(), match.group(2).strip()))
    return labels, refs


def check_references(sources: list[TexSource], labels: set[str], opts: Options) -> list[Finding]:
    """Every referenced label must be defined somewhere in the paper."""
    undefined: list[str] = []
    for src in sources:
        for match in REF_RE.finditer(src.text):
            undefined += [f"{k.strip()} ({src.path.name}:{src.line_of(match.start())})"
                          for k in match.group(1).split(",") if k.strip() and k.strip() not in labels]
    if undefined:
        level = Level.FAIL if opts.final else Level.WARN
        return [Finding("references", level, f"{len(undefined)} undefined: {_lines(undefined)}")]
    return [Finding("references", Level.PASS, "all references resolve")]


def check_placeholders(sources: list[TexSource], opts: Options) -> list[Finding]:
    """Count the placeholders a writer left for the author, the experts or the bibliography."""
    counts: dict[str, list[str]] = {name: [] for name in PLACEHOLDER_RES}
    for src in sources:
        for name, pattern in PLACEHOLDER_RES.items():
            counts[name] += [f"{src.path.name}:{src.line_of(m.start())}" for m in pattern.finditer(src.text)]
    total = sum(len(v) for v in counts.values())
    if not total:
        return [Finding("placeholders", Level.PASS, "none")]
    summary = ", ".join(f"{len(v)} {k}" for k, v in counts.items() if v)
    where = _lines(loc for v in counts.values() for loc in v)
    return [Finding("placeholders", Level.FAIL if opts.final else Level.INFO, f"{summary} — {where}")]


def check_floats(sources: list[TexSource], refs: set[str]) -> list[Finding]:
    """Figures and tables need a caption and a label, and the label must be referenced."""
    problems: list[str] = []
    count = 0
    for src in sources:
        for match in FLOAT_RE.finditer(src.text):
            count += 1
            body, loc = match.group(3), f"{match.group(1)} at {src.path.name}:{src.line_of(match.start())}"
            if "\\caption" not in body:
                problems.append(f"{loc} has no caption")
            label_match = LABEL_RE.search(body)
            if not label_match:
                problems.append(f"{loc} has no label")
            elif label_match.group(1) not in refs:
                problems.append(f"{label_match.group(1)} is never referenced")
    if problems:
        return [Finding("floats", Level.WARN, _lines(problems))]
    return [Finding("floats", Level.PASS, f"{count} floats, captioned, labelled and referenced")]


DISPLAY_BODY_RE = re.compile(
    r"\\begin\{(equation|align|gather|multline|flalign)(\*?)\}(.*?)\\end\{\1\2\}|\\\[(.*?)\\\]", re.DOTALL
)
MATH_START_INLINE_RE = re.compile(r"(?<=[.!?])[ \t]+(?:\$|\\\()")
MATH_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\\($])")
MAX_INLINE_MATH_PER_SENTENCE = 2


def _symbol_sentence_starts(name: str, prose: str) -> list[str]:
    """Locate sentences that open with inline maths.

    A line opening with maths counts as a sentence start when the previous non-blank line ends a
    sentence or a command (``.``, ``!``, ``?``, ``}``) or there is none: with one sentence per line
    this catches every case, and a line that continues a sentence ("where\\n$x$ is") is spared.
    """
    hits = [f"{name}:{prose.count(chr(10), 0, m.start()) + 1}" for m in MATH_START_INLINE_RE.finditer(prose)]
    previous = ""
    for number, line in enumerate(prose.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(("$", "\\(")) and (not previous or previous[-1] in ".!?}"):
            hits.append(f"{name}:{number}")
        if stripped:
            previous = stripped
    return hits


def check_math(sources: list[TexSource], refs: set[str]) -> list[Finding]:
    """Apply the mechanical rules of the mathematics guide to displayed and inline formulas."""
    unpunctuated: list[str] = []
    unlabelled: list[str] = []
    uncited: list[str] = []
    symbol_starts: list[str] = []
    crowded: list[str] = []
    for src in sources:
        for match in DISPLAY_BODY_RE.finditer(src.text):
            body = match.group(3) if match.group(3) is not None else match.group(4)
            loc = f"{src.path.name}:{src.line_of(match.start())}"
            core = re.sub(r"\\label\{[^}]*\}|\\nonumber|\\notag|\\\\|\s", "", body)
            if core and core[-1] not in ",.;":
                unpunctuated.append(loc)
            if match.group(1) and not match.group(2):
                labels = LABEL_RE.findall(body)
                if match.group(1) == "equation" and not labels:
                    unlabelled.append(loc)
                uncited += [f"{label} ({loc})" for label in labels if label not in refs]
        prose = _protect_abbreviations(_replace_displays(src.text))
        prose = FLOAT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), prose)
        symbol_starts += _symbol_sentence_starts(src.path.name, prose)
        position = 0
        for sentence in MATH_SENTENCE_SPLIT_RE.split(prose):
            position = prose.find(sentence, position)
            if len(INLINE_MATH_RE.findall(sentence)) > MAX_INLINE_MATH_PER_SENTENCE:
                start = position + len(sentence) - len(sentence.lstrip())
                crowded.append(f"{src.path.name}:{prose.count(chr(10), 0, start) + 1}")
            position += len(sentence)
    findings: list[Finding] = []
    for items, what in ((symbol_starts, "sentences start with a symbol"),
                        (crowded, f"sentences hold > {MAX_INLINE_MATH_PER_SENTENCE} inline formulas"),
                        (unpunctuated, "displays not punctuated as part of a sentence"),
                        (unlabelled, "numbered equations without a label (use equation* if unreferenced)"),
                        (uncited, "equation labels never referenced (unnumber them?)")):
        if items:
            findings.append(Finding("math", Level.WARN, f"{len(items)} {what}: {_lines(items)}"))
    return findings or [Finding("math", Level.PASS, "formulas follow the mechanical rules")]


def _words(text: str) -> list[str]:
    return [w for w in text.split() if re.search(r"[A-Za-z0-9]", w)]


def check_length(plains: list[str], opts: Options) -> list[Finding]:
    """Compare the prose word count (floats and display maths excluded) with the budget."""
    words = sum(len(_words(p)) for p in plains)
    if opts.budget is None:
        return [Finding("length", Level.INFO, f"{words} words (no --budget given)")]
    ratio = words / opts.budget
    message = f"{words} words, budget {opts.budget} ({ratio:.0%})"
    if ratio > BUDGET_FAIL_RATIO:
        return [Finding("length", Level.FAIL, message + " — over budget")]
    if ratio < BUDGET_WARN_RATIO:
        return [Finding("length", Level.WARN, message + " — well under budget")]
    return [Finding("length", Level.PASS, message)]


def _protect_abbreviations(text: str) -> str:
    for abbr in ABBREVIATIONS:
        text = text.replace(abbr, abbr.replace(".", "\u2024"))
    return text


def _paragraphs(plain: str) -> Iterator[tuple[int, str]]:
    """Yield (first line number, text) for each blank-line-separated paragraph."""
    line = 1
    for block in re.split(r"(\n\s*\n)", plain):
        if block.strip() and not re.fullmatch(r"\n\s*\n", block):
            lead = len(block) - len(block.lstrip("\n"))
            yield line + lead, block
        line += block.count("\n")


def check_clarity(sources: list[TexSource], plains: list[str], opts: Options) -> list[Finding]:
    """Flag long sentences and paragraphs, and acronyms used before definition or rarely."""
    long_sentences: list[str] = []
    long_paragraphs: list[str] = []
    lengths: list[int] = []
    first_use: dict[str, tuple[str, bool]] = {}
    uses: dict[str, int] = {}
    for src, plain in zip(sources, plains):
        for start_line, para in _paragraphs(plain):
            n_para = len(_words(para))
            if n_para > opts.max_paragraph:
                long_paragraphs.append(f"{src.path.name}:{start_line} ({n_para} w)")
            protected = _protect_abbreviations(para)
            bounds = list(SENTENCE_END_RE.finditer(protected))
            starts = [0] + [b.end() for b in bounds]
            ends = [b.start() for b in bounds] + [len(protected)]
            for begin, end in zip(starts, ends):
                sentence = protected[begin:end]
                n = len(_words(sentence))
                if n:
                    lengths.append(n)
                if n > opts.max_sentence:
                    first_char = begin + len(sentence) - len(sentence.lstrip())
                    line = start_line + protected.count("\n", 0, first_char)
                    long_sentences.append(f"{src.path.name}:{line} ({n} w)")
            for match in ACRONYM_RE.finditer(para):
                acronym = match.group(1)
                upper = sum(ch.isupper() for ch in acronym)
                if upper < 2 or upper / max(1, sum(ch.isalpha() for ch in acronym)) < 0.6 or ROMAN_RE.match(acronym):
                    continue
                uses[acronym] = uses.get(acronym, 0) + 1
                if acronym not in first_use:
                    before, after = para[max(0, match.start() - 1): match.start()], para[match.end(): match.end() + 2]
                    defined = before == "(" or after.startswith(")") or after.startswith(" (")
                    first_use[acronym] = (f"{src.path.name}:{start_line + para.count(chr(10), 0, match.start())}", defined)
    findings: list[Finding] = []
    if long_sentences:
        findings.append(Finding("clarity", Level.WARN,
                                f"{len(long_sentences)} sentences > {opts.max_sentence} words: {_lines(long_sentences)}"))
    if long_paragraphs:
        findings.append(Finding("clarity", Level.WARN,
                                f"{len(long_paragraphs)} paragraphs > {opts.max_paragraph} words: {_lines(long_paragraphs)}"))
    undefined = [f"{a} ({loc})" for a, (loc, ok) in first_use.items() if not ok]
    if undefined:
        findings.append(Finding("clarity", Level.WARN, "acronyms not defined at first use here (or defined in an "
                                f"earlier section; check in reading order): {_lines(undefined)}"))
    rare = [a for a, (_, ok) in first_use.items() if ok and uses[a] < MIN_ACRONYM_USES]
    if rare:
        findings.append(Finding("clarity", Level.WARN,
                                f"acronyms defined but used < {MIN_ACRONYM_USES} times (spell out?): {_lines(rare)}"))
    if lengths:
        mean = statistics.fmean(lengths)
        cv = statistics.pstdev(lengths) / mean if mean else 0.0
        findings.append(Finding("style", Level.INFO,
                                f"{len(lengths)} sentences, mean {mean:.1f} words, CV {cv:.2f}"))
    return findings or [Finding("clarity", Level.PASS, "no long sentences or paragraphs; acronyms defined")]


# ----------------------------------------------------------------------------- entry point


def parse_args(argv: list[str] | None) -> Options:
    """Parse and validate the command line."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tex", nargs="+", required=True, type=Path, help="section files, in reading order")
    parser.add_argument("--paper-root", type=Path, help="LaTeX project root (default: parent of the first file's folder)")
    parser.add_argument("--bib", nargs="*", type=Path, default=[], help=".bib file(s)")
    parser.add_argument("--verified-keys", type=Path, help="file listing cite keys with a reading (e.g. LIBRARY.md)")
    parser.add_argument("--numbers", type=Path, help="numbers.md ledger")
    parser.add_argument("--glossary", type=Path, help="glossary.md")
    parser.add_argument("--budget", type=int, help="word budget for the given files together")
    parser.add_argument("--max-sentence", type=int, default=DEFAULT_MAX_SENTENCE_WORDS)
    parser.add_argument("--max-paragraph", type=int, default=DEFAULT_MAX_PARAGRAPH_WORDS)
    parser.add_argument("--final", action="store_true", help="fail on undefined references and placeholders")
    parser.add_argument("--check-years", action="store_true", help="also check 4-digit years against the ledger")
    args = parser.parse_args(argv)
    paths = [args.verified_keys, args.numbers, args.glossary, *args.tex, *args.bib]
    missing = [str(p) for p in paths if p is not None and not p.is_file()]
    if missing:
        raise CheckInputError(f"file(s) not found: {', '.join(missing)}")
    root = args.paper_root or args.tex[0].resolve().parent.parent
    if not root.is_dir():
        raise CheckInputError(f"paper root is not a directory: {root}")
    return Options(tex=args.tex, paper_root=root, bibs=args.bib, verified_keys=args.verified_keys,
                   numbers=args.numbers, glossary=args.glossary, budget=args.budget,
                   max_sentence=args.max_sentence, max_paragraph=args.max_paragraph,
                   final=args.final, check_years=args.check_years)


def run_checks(opts: Options) -> list[Finding]:
    """Run every check and return the findings in report order."""
    sources = [load_tex(p) for p in opts.tex]
    plains = [to_plain_text(s.text) for s in sources]
    labels, refs = _paper_labels_and_refs(opts.paper_root)
    for src in sources:  # files outside the paper root still define labels and references
        labels.update(find_labels(src.text))
        refs.update(k.strip() for m in REF_RE.finditer(src.text) for k in m.group(1).split(","))
    return [
        *check_citations(sources, opts),
        *check_numbers(sources, opts),
        *check_glossary(sources, plains, opts),
        *check_references(sources, labels, opts),
        *check_placeholders(sources, opts),
        *check_floats(sources, refs),
        *check_math(sources, refs),
        *check_length(plains, opts),
        *check_clarity(sources, plains, opts),
    ]


def main(argv: list[str] | None = None) -> int:
    """Print the report and return the exit status."""
    try:
        opts = parse_args(argv)
        findings = run_checks(opts)
    except CheckInputError as err:
        print(f"check_section.py: error: {err}", file=sys.stderr)
        return 2
    names = ", ".join(p.name for p in opts.tex)
    print(f"check_section.py — {names}")
    for f in findings:
        print(f"{f.level.name:<5} {f.check}: {f.message}")
    failed = sum(f.level is Level.FAIL for f in findings)
    warned = sum(f.level is Level.WARN for f in findings)
    verdict = "FAIL" if failed else "PASS"
    print(f"SUMMARY: {verdict} ({failed} failed, {warned} warnings) → exit {1 if failed else 0}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
