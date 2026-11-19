#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pymupdf>=1.24"]
# ///
"""Deterministic tools for rigorous paper reading: fetch, extract, verify quotes, highlight.

Run with ``uv run --script paper_tools.py <command> ...``. Every page number this tool reports is
the 1-indexed physical page of the PDF, taken from the PDF itself, never from a model.

Exit codes: 0 success; 1 verification failures; 2 unusable PDF (scanned, empty, not a PDF);
3 access blocked (no legal full-text copy found; ask the user to download it).
"""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import pymupdf  # type: ignore[import-not-found]
except ImportError:
    pymupdf = None  # type: ignore[assignment]


def _require_pymupdf():
    if pymupdf is None:
        raise SystemExit("pymupdf is required for PDF commands. Install with: pip install pymupdf (or uv run --with pymupdf)")
    return pymupdf

USER_AGENT = "read-paper-skill/1.0 (academic research)"  # the email goes only to Unpaywall's query
MIN_PDF_BYTES = 20_000
LOW_TEXT_CHARS = 80  # a text page of a paper has well over 1,000 characters
ARXIV_DELAY_S = 3.1  # arXiv API terms: at most one request every three seconds
EXIT_OK, EXIT_VERIFY_FAIL, EXIT_BAD_PDF, EXIT_BLOCKED = 0, 1, 2, 3


class PaperToolsError(Exception):
    """Base error for paper_tools."""


class BlockedError(PaperToolsError):
    """No legal full-text copy could be obtained."""


# --------------------------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------------------------


@dataclass
class Attempt:
    source: str
    url: str
    result: str


@dataclass
class SourceRecord:
    requested: dict[str, str]
    method: str = ""
    retrieved_from: str = ""
    version_type: str = ""
    license: str = ""
    resolved: dict[str, object] = field(default_factory=dict)
    retrieved_at: str = ""
    sha256: str = ""
    bytes: int = 0
    attempts: list[Attempt] = field(default_factory=list)


def _http_get(url: str, email: str, timeout: float = 60.0, retries: int = 2) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # publishers (e.g. nature.com) set a cookie and redirect; without a jar the PDF never arrives
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    for attempt in range(retries + 1):
        try:
            with opener.open(req, timeout=timeout) as resp:  # noqa: S310 (fixed schemes)
                return resp.read(), resp.geturl()
        except urllib.error.HTTPError as err:
            # 429/503 are rate limits (arXiv, Semantic Scholar): back off instead of failing
            if err.code not in (429, 503) or attempt == retries:
                raise
            time.sleep(10 * (attempt + 1))
    raise PaperToolsError(f"unreachable: {url}")


def _is_pdf(data: bytes) -> bool:
    return data[:1024].lstrip().startswith(b"%PDF") and len(data) >= MIN_PDF_BYTES


def _try_pdf(url: str, source: str, email: str, rec: SourceRecord) -> bytes | None:
    try:
        data, final = _http_get(url, email)
    except (urllib.error.URLError, TimeoutError, ValueError) as err:
        rec.attempts.append(Attempt(source, url, f"error: {err}"))
        return None
    if not _is_pdf(data):
        rec.attempts.append(Attempt(source, url, f"not a PDF ({len(data)} bytes; landing page?)"))
        return None
    rec.attempts.append(Attempt(source, final, "ok"))
    rec.retrieved_from = final
    return data


def _arxiv_metadata(arxiv_id: str, email: str, rec: SourceRecord) -> dict[str, object]:
    url = f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}"
    try:
        data, _ = _http_get(url, email)
    except (urllib.error.URLError, TimeoutError) as err:
        rec.attempts.append(Attempt("arxiv-api", url, f"error: {err}"))
        return {}
    ns = {"a": "http://www.w3.org/2005/Atom"}
    try:
        entry = ET.fromstring(data).find("a:entry", ns)
    except ET.ParseError as err:
        rec.attempts.append(Attempt("arxiv-api", url, f"unparsable response: {err}"))
        return {}
    if entry is None or entry.find("a:title", ns) is None:
        rec.attempts.append(Attempt("arxiv-api", url, "no entry"))
        return {}
    rec.attempts.append(Attempt("arxiv-api", url, "ok"))
    return {
        "title": " ".join((entry.findtext("a:title", "", ns)).split()),
        "authors": [a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns)],
        "published": entry.findtext("a:published", "", ns),
        "updated": entry.findtext("a:updated", "", ns),
        "id_url": entry.findtext("a:id", "", ns),
    }


def _fetch_arxiv(arxiv_id: str, email: str, rec: SourceRecord) -> bytes | None:
    arxiv_id = re.sub(r"^(arxiv:|https?://arxiv\.org/(abs|pdf)/)", "", arxiv_id, flags=re.I)
    arxiv_id = arxiv_id.removesuffix(".pdf")
    rec.resolved.update(_arxiv_metadata(arxiv_id, email, rec))
    rec.resolved["arxiv_id"] = arxiv_id
    time.sleep(ARXIV_DELAY_S)
    for url in (f"https://arxiv.org/pdf/{arxiv_id}", f"https://export.arxiv.org/pdf/{arxiv_id}"):
        data = _try_pdf(url, "arxiv", email, rec)
        if data:
            version = re.search(r"v\d+$", str(rec.resolved.get("id_url", "")) or arxiv_id)
            rec.method = "arxiv"
            rec.version_type = f"preprint (arXiv {version.group() if version else 'latest'})"
            return data
        time.sleep(ARXIV_DELAY_S)
    return None


def _fetch_unpaywall(doi: str, email: str, rec: SourceRecord) -> bytes | None:
    url = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={urllib.parse.quote(email)}"
    try:
        data, _ = _http_get(url, email)
        meta = json.loads(data)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
        rec.attempts.append(Attempt("unpaywall", url.split("?")[0], f"error: {err}"))
        return None
    rec.attempts.append(Attempt("unpaywall", url.split("?")[0], f"is_oa={meta.get('is_oa')}"))
    rec.resolved.setdefault("title", meta.get("title"))
    rec.resolved.setdefault("year", meta.get("year"))
    rec.resolved.setdefault("journal", meta.get("journal_name"))
    authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in meta.get("z_authors") or []]
    rec.resolved.setdefault("authors", authors)
    locations = [meta.get("best_oa_location")] + list(meta.get("oa_locations") or [])
    seen: set[str] = set()
    for loc in filter(None, locations):
        pdf_url = loc.get("url_for_pdf")
        if not pdf_url or pdf_url in seen:
            continue
        seen.add(pdf_url)
        data = _try_pdf(pdf_url, f"unpaywall:{loc.get('host_type')}", email, rec)
        if data:
            rec.method = "unpaywall"
            rec.version_type = str(loc.get("version") or "")
            rec.license = str(loc.get("license") or "")
            return data
    return None


def _fetch_europepmc(doi: str, email: str, rec: SourceRecord) -> bytes | None:
    query = urllib.parse.quote(f'DOI:"{doi}"')
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={query}&format=json&resultType=core"
    try:
        data, _ = _http_get(url, email)
        results = json.loads(data).get("resultList", {}).get("result", [])
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
        rec.attempts.append(Attempt("europepmc", url, f"error: {err}"))
        return None
    if not results:
        rec.attempts.append(Attempt("europepmc", url, "no record"))
        return None
    hit = results[0]
    rec.attempts.append(Attempt("europepmc", url, f"pmcid={hit.get('pmcid')} oa={hit.get('isOpenAccess')}"))
    candidates = [
        u.get("url")
        for u in hit.get("fullTextUrlList", {}).get("fullTextUrl", [])
        if u.get("documentStyle") == "pdf" and "open" in str(u.get("availability", "")).lower()
    ]
    if hit.get("pmcid"):
        candidates.append(f"https://europepmc.org/articles/{hit['pmcid']}?pdf=render")
    for pdf_url in dict.fromkeys(filter(None, candidates)):  # de-duplicate, keep order
        data = _try_pdf(pdf_url, "europepmc", email, rec)
        if data:
            rec.method, rec.version_type = "europepmc", "PMC open access"
            return data
    return None


def cmd_fetch(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "paper.pdf"
    email = args.email or os.environ.get("UNPAYWALL_EMAIL", "")
    requested = {k: v for k, v in vars(args).items() if k in ("arxiv", "doi", "url", "pdf") and v}
    rec = SourceRecord(requested=requested)
    data: bytes | None = None

    if args.pdf:
        src = Path(args.pdf).expanduser().resolve()
        if not src.is_file():
            print(f"BLOCKED: local file not found: {src}", file=sys.stderr)
            return EXIT_BLOCKED
        data = src.read_bytes()
        rec.method, rec.retrieved_from = "local", str(src)
        rec.attempts.append(Attempt("local", str(src), "ok" if _is_pdf(data) else "not a PDF"))
        if not _is_pdf(data):
            print(f"BAD PDF: {src} is not a PDF or is under {MIN_PDF_BYTES} bytes", file=sys.stderr)
            return EXIT_BAD_PDF
    if data is None and args.arxiv:
        data = _fetch_arxiv(args.arxiv, email, rec)
    if data is None and args.doi:
        if email:
            data = _fetch_unpaywall(args.doi, email, rec)
        else:
            rec.attempts.append(Attempt("unpaywall", "-", "skipped: no --email / UNPAYWALL_EMAIL"))
        if data is None:
            data = _fetch_europepmc(args.doi, email, rec)
        rec.resolved.setdefault("doi", args.doi)

    if data is None and args.url:
        data = _try_pdf(args.url, "url", email, rec)
        rec.method = "url" if data else rec.method
    rec.retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if data is None:
        (out / "source.json").write_text(json.dumps(asdict(rec), indent=2, default=str))
        print("BLOCKED: no legal full-text PDF found. Attempts:", file=sys.stderr)
        for a in rec.attempts:
            print(f"  - {a.source}: {a.url} -> {a.result}", file=sys.stderr)
        print(f"Ask the user to download the PDF to: {target}", file=sys.stderr)
        return EXIT_BLOCKED

    if not (args.pdf and Path(args.pdf).resolve() == target.resolve()):
        target.write_bytes(data)
    rec.sha256 = hashlib.sha256(data).hexdigest()
    rec.bytes = len(data)
    (out / "source.json").write_text(json.dumps(asdict(rec), indent=2, default=str))
    print(json.dumps({"status": "ok", "pdf": str(target), "method": rec.method,
                      "version_type": rec.version_type, "resolved": rec.resolved}, indent=2, default=str))
    return EXIT_OK


# --------------------------------------------------------------------------------------------
# extract
# --------------------------------------------------------------------------------------------


def cmd_extract(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    _require_pymupdf()
    try:
        doc = pymupdf.open(pdf)
    except (pymupdf.FileDataError, RuntimeError) as err:
        print(f"BAD PDF: cannot open {pdf}: {err}", file=sys.stderr)
        return EXIT_BAD_PDF
    lines: list[str] = [f"<!-- fulltext of {pdf.name}; {doc.page_count} pages; "
                        "page N = 1-indexed physical PDF page -->"]
    chars: list[int] = []
    low_text_with_images: list[int] = []
    for pno, page in enumerate(doc, start=1):
        text = page.get_text("text")  # content-stream order: column-wise for LaTeX two-column PDFs
        n = len(text.strip())
        chars.append(n)
        if n < LOW_TEXT_CHARS and page.get_images():
            low_text_with_images.append(pno)
        label = page.get_label() if hasattr(page, "get_label") else ""
        lines.append(f"\n<!-- page {pno}{f' (printed label {label})' if label else ''} -->\n")
        lines.append(text.rstrip())
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")

    full = " ".join(lines).casefold()
    head = " ".join(doc[0].get_text("text").split())[:700] if doc.page_count else ""
    scanned = doc.page_count > 0 and len(low_text_with_images) >= 0.5 * doc.page_count
    stats = {
        "pdf": str(pdf),
        "pages": doc.page_count,
        "total_chars": sum(chars),
        "median_chars_per_page": sorted(chars)[len(chars) // 2] if chars else 0,
        "low_text_image_pages": low_text_with_images,
        "likely_scanned": scanned,
        "has_abstract": "abstract" in full,
        "has_references": any(k in full for k in ("references", "bibliography")),
        "has_method_or_results": any(k in full for k in ("method", "experiment", "results")),
        "metadata_title": doc.metadata.get("title", "") if doc.metadata else "",
        "metadata_author": doc.metadata.get("author", "") if doc.metadata else "",
        "first_page_head": head,
        "fulltext": str(args.out),
    }
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    if scanned or sum(chars) < 5 * LOW_TEXT_CHARS:
        print("BAD PDF: no extractable text on most pages (scanned?). Ask the user for a text PDF "
              "or OCR it before reading.", file=sys.stderr)
        return EXIT_BAD_PDF
    return EXIT_OK


# --------------------------------------------------------------------------------------------
# quote matching (shared by verify and highlight)
# --------------------------------------------------------------------------------------------

# Only quotes, brackets and sentence punctuation are stripped from token edges. Signs, comparison
# operators, %, ±, × and ∞ are CONTENT: "k < n" must never verify against a quote saying "k > n".
_EDGE_PUNCT = re.compile(r"^[\"'()\[\]{},.;:!?]+|[\"'()\[\]{},.;:!?]+$")
_INTRA_WORD_HYPHEN = re.compile(r"(?<=[^\W\d_])-(?=[^\W\d_])")
_QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                              "–": "-", "—": "-", "−": "-", "­": ""})
MIN_QUOTE_TOKENS = 6      # shorter "quotes" ("BLEU") verify against almost any paper
MIN_SEGMENT_TOKENS = 4    # every part of an elided quote must stand on its own
MAX_ELLIPSIS_GAP = 40     # tokens a "[...]" may skip; larger gaps can splice opposite claims


def norm_token(tok: str) -> str:
    """Normalise one token for matching.

    NFKC expands ligatures (``ﬁ`` -> ``fi``); NFKD then strips accents, including the detached
    spacing accents that LaTeX PDFs emit (``Fr´echet`` and ``Fréchet`` both become ``frechet``).
    Quotes and dashes are unified and case folded. Hyphens are dropped only between letters
    (compound words and line-break hyphenation); a minus sign, a range (``0.84-0.88``) or an
    exponent (``10-9``) keeps its hyphen, so a sign flip or a dropped range end never matches.
    """
    tok = unicodedata.normalize("NFKC", tok).translate(_QUOTE_CHARS)
    tok = "".join(c for c in unicodedata.normalize("NFKD", tok)
                  if unicodedata.category(c) not in ("Mn", "Sk") and not c.isspace())
    tok = _EDGE_PUNCT.sub("", tok.casefold())
    return _INTRA_WORD_HYPHEN.sub("", tok)


@dataclass
class PageTokens:
    page: int
    tokens: list[str]
    rects: list[list[pymupdf.Rect]]


def page_tokens(page: pymupdf.Page, pno: int) -> PageTokens:
    """Tokenise a page into normalised words, re-joining words hyphenated across line ends."""
    words = page.get_text("words")  # x0, y0, x1, y1, word, block, line, wno (stream order)
    toks: list[str] = []
    rects: list[list[pymupdf.Rect]] = []
    i = 0
    while i < len(words):
        w = words[i]
        text, rs = w[4], [pymupdf.Rect(w[:4])]
        nxt = words[i + 1] if i + 1 < len(words) else None
        if text.endswith(("-", "­")) and nxt is not None and (nxt[5], nxt[6]) != (w[5], w[6]):
            text, rs, i = text.rstrip("-­") + nxt[4], rs + [pymupdf.Rect(nxt[:4])], i + 1
        t = norm_token(text)
        if t:
            toks.append(t)
            rects.append(rs)
        i += 1
    return PageTokens(pno, toks, rects)


def find_run(hay: list[str], needle: list[str]) -> int:
    """Return the start index of ``needle`` as a contiguous run in ``hay``, or -1."""
    n = len(needle)
    if n == 0:
        return -1
    first = needle[0]
    for i in range(len(hay) - n + 1):
        if hay[i] == first and hay[i:i + n] == needle:
            return i
    return -1


def longest_run_fraction(hay: list[str], needle: list[str]) -> float:
    """Fraction of ``needle`` covered by its longest contiguous run present in ``hay``."""
    best, n = 0, len(needle)
    hay_str = "\x00".join(hay)
    for size in range(n, 0, -1):
        for start in range(0, n - size + 1):
            if "\x00".join(needle[start:start + size]) in hay_str:
                best = size
                break
        if best:
            break
    return best / n if n else 0.0


@dataclass
class Quote:
    qid: str
    page: int | None
    text: str
    meta: dict[str, str]


_QUOTE_HEADER = re.compile(r"^#{2,4}\s*(Q[\w.-]+)\b")
_FIELD = re.compile(r"^\s*[-*]\s*(\w[\w ]*?)\s*:\s*(.+?)\s*$")


def parse_quotes(path: Path) -> list[Quote]:
    """Parse ``### Q<id>`` blocks with ``- page: N`` fields and ``>`` quote lines."""
    quotes: list[Quote] = []
    cur: Quote | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.lstrip().startswith("#"):
            # any heading closes the current block; only "### Q<id>" opens one. Without this, text
            # under a mistyped heading would be silently appended to the previous quote.
            if cur:
                quotes.append(cur)
            m = _QUOTE_HEADER.match(raw)
            cur = Quote(m.group(1), None, "", {}) if m else None
        elif cur is None:
            continue
        elif raw.lstrip().startswith(">"):
            cur.text += " " + raw.lstrip()[1:].strip()
        elif m := _FIELD.match(raw):
            key, val = m.group(1).strip().lower(), m.group(2)
            cur.meta[key] = val
            if key == "page":
                digits = re.match(r"\d+", val)
                cur.page = int(digits.group()) if digits else None
    if cur:
        quotes.append(cur)
    for q in quotes:
        q.text = q.text.strip().strip('"“”').strip()
    return quotes


def quote_segments(text: str) -> list[list[str]]:
    """Split a quote at ellipses ([...], …, ...) into normalised token segments."""
    parts = re.split(r"\[\s*(?:\.\.\.|…)\s*\]|…|\.\.\.", text)
    segs = [[t for t in (norm_token(x) for x in p.split()) if t] for p in parts]
    return [s for s in segs if s]


@dataclass
class QuoteResult:
    qid: str
    stated_page: int | None
    status: str  # VERIFIED | WRONG_PAGE | NEAR | NOT_FOUND | NO_PAGE | EMPTY
    found_pages: list[int]
    detail: str = ""


def _locate(segs: list[list[str]], pages: list[PageTokens], idx: int) -> bool:
    """True if the quote starts on page ``idx`` and all segments follow in order.

    The quote may run over onto page idx+1, but it must begin on the stated page; otherwise a
    quote from page p+1 would wrongly verify against page p.
    """
    n_here = len(pages[idx].tokens)
    window = pages[idx].tokens + (pages[idx + 1].tokens if idx + 1 < len(pages) else [])
    pos = 0
    for k, seg in enumerate(segs):
        j = find_run(window[pos:], seg)
        if j < 0 or (k == 0 and j >= n_here) or (k > 0 and j > MAX_ELLIPSIS_GAP):
            return False
        pos += j + len(seg)
    return True


def _locate_table(tokens: list[str], pages: list[PageTokens], idx: int) -> bool:
    """True if every token of a table row occurs, in any order, within a compact window of page idx.

    Table extraction order varies between PDFs (row-wise or column-wise), so a row is checked as a
    multiset of tokens inside a window of at most ``max(4 * len(tokens), 24)`` page tokens.
    """
    hay, need = pages[idx].tokens, Counter(tokens)
    width = max(4 * len(tokens), 24)
    starts = range(0, max(1, len(hay) - len(tokens) + 1))
    return any(not need - Counter(hay[start:start + width]) for start in starts)


def _found(q: Quote, segs: list[list[str]], pages: list[PageTokens], idx: int) -> bool:
    if q.meta.get("kind", "").lower() == "table":
        return _locate_table([t for s in segs for t in s], pages, idx)
    return _locate(segs, pages, idx)


def check_quote(q: Quote, pages: list[PageTokens]) -> QuoteResult:
    segs = quote_segments(q.text)
    if not segs:
        return QuoteResult(q.qid, q.page, "EMPTY", [], "no quote text parsed")
    n_tokens = sum(len(s) for s in segs)
    is_table = q.meta.get("kind", "").lower() == "table"
    # a table row (label + cells) is short by nature; every one of its tokens must still be on the page
    min_tokens = 3 if is_table else MIN_QUOTE_TOKENS
    if n_tokens < min_tokens or (not is_table and min(len(s) for s in segs) < MIN_SEGMENT_TOKENS):
        return QuoteResult(q.qid, q.page, "TOO_SHORT", [],
                           f"{n_tokens} tokens; need >= {min_tokens}, and >= {MIN_SEGMENT_TOKENS} "
                           "per [...] segment: quote enough context to fix the meaning")
    if q.page is None:
        hits = [p.page for i, p in enumerate(pages) if _found(q, segs, pages, i)]
        return QuoteResult(q.qid, None, "NO_PAGE", hits, "add '- page: N'")
    if 1 <= q.page <= len(pages) and _found(q, segs, pages, q.page - 1):
        return QuoteResult(q.qid, q.page, "VERIFIED", [q.page])
    hits = [p.page for i, p in enumerate(pages) if _found(q, segs, pages, i)]
    if hits:
        return QuoteResult(q.qid, q.page, "WRONG_PAGE", hits, f"found on page(s) {hits}")
    flat = [t for s in segs for t in s]
    best = max(((longest_run_fraction(p.tokens, flat), p.page) for p in pages), default=(0.0, 0))
    if best[0] >= 0.8:
        return QuoteResult(q.qid, q.page, "NEAR", [best[1]],
                           f"{best[0]:.0%} of tokens match contiguously on page {best[1]}; "
                           "re-copy the exact wording")
    return QuoteResult(q.qid, q.page, "NOT_FOUND", [], f"best partial match {best[0]:.0%}")


# --------------------------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------------------------



def cmd_verify(args: argparse.Namespace) -> int:
    _require_pymupdf()
    doc = pymupdf.open(args.pdf)
    pages = [page_tokens(p, i) for i, p in enumerate(doc, start=1)]
    quotes = parse_quotes(Path(args.quotes))
    results = [check_quote(q, pages) for q in quotes]
    ok_ids = {r.qid for r in results if r.status == "VERIFIED"}
    all_ids = {q.qid for q in quotes}

    print(f"{'ID':<8} {'STATED':>6}  {'STATUS':<10} DETAIL")
    for r in results:
        stated = r.stated_page if r.stated_page is not None else "-"
        print(f"{r.qid:<8} {stated:>6}  {r.status:<10} {r.detail}")
    failures = [r for r in results if r.status != "VERIFIED"]
    duplicates = sorted({q.qid for q in quotes if [x.qid for x in quotes].count(q.qid) > 1})

    note_report: dict[str, list[str]] = {}
    if args.notes:
        text = Path(args.notes).read_text(encoding="utf-8")
        # every quote ID anywhere in the notes (citations and verdict-table cells); "Q1-venue" is not one
        cited = set(re.findall(r"(?<![\w-])Q\d+[a-z]?(?![\w-])", text))
        # every decimal or percentage stated after the header must come from a verified quote
        body = text[text.find("\n## "):] if "\n## " in text else text
        quoted = {t for q in quotes if q.qid in ok_ids for s in quote_segments(q.text) for t in s}
        numbers = {norm_token(n) for n in re.findall(r"(?<![\w.])[-−]?\d+\.\d+%?|(?<![\w.])\d+%", body)}
        note_report = {
            "cited_but_missing": sorted(cited - all_ids),
            "cited_but_unverified": sorted((cited & all_ids) - ok_ids),
            "numbers_not_in_quotes": sorted(n for n in numbers if not any(n in t for t in quoted)),
            "verified_but_uncited": sorted(ok_ids - cited),
        }
        print("\nnotes cross-check:")
        for k, v in note_report.items():
            print(f"  {k}: {', '.join(v) if v else 'none'}")

    summary = {
        "pdf": str(args.pdf), "quotes": str(args.quotes), "n_quotes": len(quotes),
        "verified": len(ok_ids), "failures": [asdict(r) for r in failures],
        "duplicate_ids": duplicates, "notes": note_report,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    Path(args.quotes).with_suffix(".verify.json").write_text(json.dumps(summary, indent=2))
    print(f"\n{len(ok_ids)}/{len(quotes)} quotes verified.")
    bad_notes = bool(note_report.get("cited_but_missing") or note_report.get("cited_but_unverified")
                     or note_report.get("numbers_not_in_quotes"))
    return EXIT_VERIFY_FAIL if failures or duplicates or bad_notes or not quotes else EXIT_OK


# --------------------------------------------------------------------------------------------
# highlight
# --------------------------------------------------------------------------------------------


def cmd_highlight(args: argparse.Namespace) -> int:
    _require_pymupdf()
    doc = pymupdf.open(args.pdf)
    pages = [page_tokens(p, i) for i, p in enumerate(doc, start=1)]
    done, skipped = [], []
    for q in parse_quotes(Path(args.quotes)):
        res = check_quote(q, pages)
        if res.status != "VERIFIED" or q.page is None:
            skipped.append(f"{q.qid} ({res.status})")
            continue
        segs = quote_segments(q.text)
        idx = q.page - 1
        spans: list[tuple[int, list[pymupdf.Rect]]] = []
        page_order = [idx] + ([idx + 1] if idx + 1 < len(pages) else [])
        pos_page, pos = 0, 0
        for seg in segs:
            placed = False
            while pos_page < len(page_order) and not placed:
                pt = pages[page_order[pos_page]]
                j = find_run(pt.tokens[pos:], seg)
                if j >= 0:
                    start = pos + j
                    rs = [r for rr in pt.rects[start:start + len(seg)] for r in rr]
                    spans.append((page_order[pos_page], rs))
                    pos, placed = start + len(seg), True
                else:
                    # the quote may continue on the next page
                    pos_page, pos = pos_page + 1, 0
            if not placed:
                break
        label = f"{q.qid}: {q.meta.get('relevance', '')}".strip(": ")
        for pidx, rects in spans:
            page = doc[pidx]  # keep a live reference: an annot on a collected page is unbound
            annot = page.add_highlight_annot([r.quad for r in rects])
            annot.set_info(title="read-paper", content=label[:500])
            annot.update()
        done.append(q.qid)
    doc.save(args.out, garbage=3, deflate=True)
    print(f"highlighted: {', '.join(done) or 'none'}")
    if skipped:
        print(f"not highlighted (not verified): {', '.join(skipped)}")
    return EXIT_OK


# --------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="obtain a legal full-text PDF into OUT/paper.pdf + OUT/source.json")
    f.add_argument("--arxiv", help="arXiv id (e.g. 1911.07023 or 1911.07023v3)")
    f.add_argument("--doi", help="DOI; tries Unpaywall (needs --email) then Europe PMC open access")
    f.add_argument("--url", help="direct PDF URL")
    f.add_argument("--pdf", help="local PDF supplied by the user")
    f.add_argument("--email", help="contact email for Unpaywall (or env UNPAYWALL_EMAIL)")
    f.add_argument("--out", required=True, help="paper folder")
    f.set_defaults(func=cmd_fetch)

    e = sub.add_parser("extract", help="PDF -> page-marked fulltext.md + identity/completeness stats")
    e.add_argument("pdf")
    e.add_argument("--out", required=True)
    e.set_defaults(func=cmd_extract)

    v = sub.add_parser("verify", help="check every quote occurs on its stated page; cross-check notes")
    v.add_argument("quotes", help="quotes.md")
    v.add_argument("--pdf", required=True)
    v.add_argument("--notes", help="notes.md whose [Qn] citations must all be verified quotes")
    v.set_defaults(func=cmd_verify)

    h = sub.add_parser("highlight", help="highlight verified quotes into an annotated copy of the PDF")
    h.add_argument("quotes")
    h.add_argument("--pdf", required=True)
    h.add_argument("--out", required=True)
    h.set_defaults(func=cmd_highlight)
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except BlockedError as err:
        print(f"BLOCKED: {err}", file=sys.stderr)
        return EXIT_BLOCKED


if __name__ == "__main__":
    sys.exit(main())
