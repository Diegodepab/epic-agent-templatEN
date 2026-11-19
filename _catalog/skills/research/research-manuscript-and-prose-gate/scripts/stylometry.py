#!/usr/bin/env python3
"""Stylometric diagnostics for the ``humanizer`` skill.

Computes the human-vs-LLM discriminating features documented in
``references/evidence-base.md`` and reports each against a target band, so a
rewrite can be aimed at measurements rather than at impressions.

Three modes:

* ``analyse``  - profile one file or a directory of files.
* ``baseline`` - profile an author corpus and emit calibration targets.
* ``compare``  - diff two versions, including an information-preservation
  check over numbers, citations, and cross-references.

Standard library only: the skill must run in environments without network
access or package installation.

All rates are heuristic proxies computed without a POS tagger or parser. They
are designed to be informative in rank order and in relative change against a
baseline; they are not linguistically exact counts. Matched instances are
reported under ``--verbose`` so that every flag can be inspected.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

__version__ = "5.0.0"

LOGGER = logging.getLogger("humanizer.stylometry")

TEXT_SUFFIXES = frozenset({".md", ".txt", ".tex", ".markdown", ".rst"})
MATTR_WINDOW = 50
MIN_TOKENS_FOR_STABLE_METRICS = 120


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class HumanizerError(Exception):
    """Base class for every error raised by this module."""


class InputError(HumanizerError):
    """Raised when the requested input cannot be read or contains no prose."""


class BaselineError(HumanizerError):
    """Raised when a baseline file is malformed or incompatible."""


# --------------------------------------------------------------------------- #
# Lexicons
# --------------------------------------------------------------------------- #

FUNCTION_WORDS: frozenset[str] = frozenset("""
a an the this that these those
i we you he she it they me him her us them my our your his its their
mine ours yours hers theirs myself ourselves itself themselves
of to in on at by for with from into onto upon about above below under over
between among across through during before after within without against
toward towards beyond beside behind near per via than as off out up down
along around beneath despite except inside outside since throughout till
until unto amid amongst
and or but nor yet so because although though while whereas if unless
once when where whether why how what which who whom whose that
is are was were be been being am has have had do does did done
can could may might must shall should will would ought need dare let
not no never nor only just also too very more most much many few less least
all any both each either neither every other another same such some one two
there here then now well even still again further already almost quite
rather perhaps therefore however thus hence otherwise instead
""".split())

HEDGES: frozenset[str] = frozenset("""
may might could would seem seems seemed appear appears appeared suggest
suggests suggested indicate indicates indicated likely unlikely possibly
probably presumably arguably apparently roughly approximately largely
generally typically often sometimes somewhat relatively potentially
""".split())

BOOSTERS: frozenset[str] = frozenset("""
clearly certainly definitely undoubtedly indeed invariably always never
demonstrably conclusively establish establishes established confirm confirms
confirmed must evidently unambiguously
""".split())

SELF_MENTION: frozenset[str] = frozenset("""
we our us i my me ours
""".split())

ATTITUDE_MARKERS: frozenset[str] = frozenset("""
unexpectedly surprisingly strikingly remarkably unfortunately fortunately
counterintuitively puzzlingly disappointingly reassuringly
""".split())

# Adverbs that are stance-like but flagged as AI tells in scientific prose
# (see patterns-rhetorical.md, S8).
FLAGGED_ADVERBS: frozenset[str] = frozenset("""
importantly notably significantly crucially fundamentally essentially
ultimately particularly interestingly critically vitally profoundly
""".split())

TRANSITION_OPENERS: tuple[str, ...] = (
    "furthermore", "moreover", "additionally", "however", "notably",
    "importantly", "significantly", "consequently", "therefore", "thus",
    "nevertheless", "nonetheless", "overall", "ultimately", "subsequently",
    "meanwhile", "indeed", "accordingly", "in addition", "in conclusion",
    "in summary", "to summarize", "to summarise", "in essence", "that said",
)

# Lexical drift markers. Historical and expected to decay: see
# references/patterns-lexical.md L8. Presence is a hint, never a verdict.
DRIFT_MARKERS: frozenset[str] = frozenset("""
delve delves delving intricate intricacies interplay meticulous meticulously
testament tapestry vibrant pivotal bolster bolsters bolstered garner garnered
underscore underscores underscoring underscored realm boasts showcase
showcases showcasing leverage leverages leveraging leveraged harness
harnessing utilize utilizes utilizing utilized utilise utilising foster
fosters fostering navigate navigating unlock unlocking unleash seamless
holistic transformative multifaceted groundbreaking cutting-edge
comprehensive robust myriad plethora paradigm elevate elevating streamline
streamlining empower empowering commendable noteworthy paramount
""".split())

FILLER_PHRASES: tuple[str, ...] = (
    "it is important to note that", "it is worth noting that",
    "it should be noted that", "it is worth mentioning that",
    "it should be emphasized that", "it should be emphasised that",
    "in order to", "due to the fact that", "owing to the fact that",
    "a number of", "in today's", "in recent years",
    "has attracted significant attention", "plays a crucial role",
    "paves the way", "paving the way", "to the best of our knowledge",
    "extensive experiments", "promising results", "sheds light on",
    "at its core", "in the realm of", "in the landscape of",
    "bridge the gap", "bridging the gap", "a testament to",
)

NOMINALIZATION_SUFFIXES: tuple[str, ...] = (
    "tion", "sion", "ment", "ance", "ence", "ity", "ness", "ism",
    "ization", "isation",
)

# Words whose nominal form is the standard technical term in these domains,
# where converting to a finite verb would damage precision.
NOMINALIZATION_EXCEPTIONS: frozenset[str] = frozenset("""
function functions information solution solutions condition conditions
distribution distributions dimension dimensions equation equations
iteration iterations resolution convolution convolutions attention
position positions relation relations direction directions section
sections question questions population populations station variance
covariance correlation regression progression version versions
transformation permutation combination probability density intensity
quantity identity university community entity capacity velocity
segmentation classification registration normalization normalisation
optimization optimisation regularization regularisation quantization
tokenization augmentation ablation validation calibration
""".split())

# -ing forms that are ordinary nouns or adjectives in scientific English and
# therefore should not be counted as participial clauses.
ING_EXCEPTIONS: frozenset[str] = frozenset("""
training testing learning imaging modeling modelling sampling encoding
embedding decoding tuning scaling clustering labeling labelling pruning
weighting smoothing thresholding masking padding pooling batching indexing
during something anything nothing everything string ring spring morning
setting settings meaning findings proceedings understanding engineering
processing reasoning ranking matching mapping planning building working
being having going using following according regarding including
""".split())

LATINATE_DRIFT_PAIRS: dict[str, str] = {
    "utilize": "use", "utilise": "use", "utilizes": "uses",
    "utilizing": "using", "utilized": "used",
    "subsequently": "then", "commence": "start", "commences": "starts",
    "initiate": "start", "terminate": "end", "ascertain": "find",
    "necessitate": "require", "necessitates": "requires",
    "endeavour": "try", "endeavor": "try", "facilitate": "allow",
    "facilitates": "allows", "demonstrate": "show", "demonstrates": "shows",
    "elucidate": "explain", "augment": "increase", "aforementioned": "this",
    "methodology": "method", "individuals": "people",
}


# --------------------------------------------------------------------------- #
# Configuration and metric model
# --------------------------------------------------------------------------- #


class Flag(str, Enum):
    """Verdict for a single metric against its target band."""

    OK = "ok"
    HIGH = "high"
    LOW = "low"
    INFO = "info"


@dataclass(frozen=True)
class Band:
    """Inclusive target interval for a metric.

    ``low`` or ``high`` may be ``None`` for one-sided bands. Bands are
    heuristic defaults for scientific English prose; an author baseline
    supersedes them.
    """

    low: float | None = None
    high: float | None = None
    note: str = ""

    def classify(self, value: float) -> Flag:
        """Return the verdict for ``value`` against this band."""
        if self.low is None and self.high is None:
            return Flag.INFO
        if self.high is not None and value > self.high:
            return Flag.HIGH
        if self.low is not None and value < self.low:
            return Flag.LOW
        return Flag.OK

    def render(self) -> str:
        """Return a compact human-readable form of the band."""
        if self.low is None and self.high is None:
            return "—"
        if self.low is None:
            return f"≤ {self.high:g}"
        if self.high is None:
            return f"≥ {self.low:g}"
        return f"{self.low:g}–{self.high:g}"


@dataclass
class Metric:
    """A single measured quantity with its verdict and supporting instances."""

    key: str
    label: str
    value: float
    unit: str
    band: Band
    instances: list[str] = field(default_factory=list)

    @property
    def flag(self) -> Flag:
        """Verdict for this metric against its band."""
        return self.band.classify(self.value)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view of this metric."""
        return {
            "key": self.key,
            "label": self.label,
            "value": round(self.value, 4),
            "unit": self.unit,
            "target": self.band.render(),
            "flag": self.flag.value,
            "n_instances": len(self.instances),
        }


# Target bands. Rates suffixed "_per_kw" are per 1000 running words.
BANDS: dict[str, Band] = {
    "tokens": Band(note="document size"),
    "sentences": Band(note="document size"),
    "median_sentence_len": Band(10, 24, "tokens"),
    "sentence_len_cv": Band(low=0.40, note="unstable below ~30 sentences"),
    "burstiness_goh": Band(note="Goh-Barabasi index, reported for continuity"),
    "burstiness_fano": Band(note="variance-to-mean, reported for reference"),
    "function_word_ratio": Band(0.40, 0.55, "restore scaffolding if low"),
    "lexical_density": Band(note="= 1 - function-word ratio"),
    "mattr": Band(note="length-stabilised type-token ratio"),
    "mean_word_length": Band(high=5.6, note="characters; prefer author baseline"),
    "polysyllabic_share": Band(high=0.30, note="words with 3+ syllables"),
    "nominalization_per_kw": Band(high=60.0, note="weak absolute band; use --baseline and the 33-50% reduction rule"),
    "participial_per_kw": Band(high=10.0, note="reduce 50-80% from LLM draft"),
    "passive_per_kw": Band(note="genre-dependent; do not minimise blindly"),
    "hedge_per_kw": Band(3.0, 20.0, "stance: restore if low, unstack if high"),
    "booster_per_kw": Band(0.5, 12.0, "stance"),
    "self_mention_per_kw": Band(2.0, 35.0, "stance; genre-dependent"),
    "attitude_per_kw": Band(high=6.0, note="zero in a discussion is itself a tell"),
    "flagged_adverb_per_kw": Band(high=3.0, note="importantly/notably/etc."),
    "transition_opener_ratio": Band(high=0.35, note="share of paragraphs"),
    "drift_marker_per_kw": Band(high=2.0, note="historical marker list"),
    "filler_phrase_per_kw": Band(high=1.5, note="deletable phrases"),
    "emdash_pairs_per_para": Band(high=1.0, note="worst paragraph; convert the excess"),
    "comma_per_sentence": Band(high=2.6, note="split or use parentheses"),
    "paren_per_kw": Band(low=3.0, note="human academic prose uses these"),
    "curly_quotes": Band(high=0.0, note="paste residue; normalise"),
    "triad_per_kw": Band(high=2.0, note="rule of three"),
    "neg_parallelism": Band(high=0.0, note="'not just X, but Y'"),
    "list_line_ratio": Band(high=0.40, note="share of lines that are list items"),
    "paragraph_len_cv": Band(low=0.25, note="paragraph-length variation"),
}


# --------------------------------------------------------------------------- #
# Text normalisation
# --------------------------------------------------------------------------- #

_MASK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("code_block", re.compile(r"```.*?```", re.S)),
    ("display_math", re.compile(r"\$\$.*?\$\$", re.S)),
    ("latex_env", re.compile(r"\\begin\{(equation|align|gather|array|tabular|figure|verbatim)\*?\}.*?\\end\{\1\*?\}", re.S)),
    ("bracket_math", re.compile(r"\\\[.*?\\\]", re.S)),
    ("inline_code", re.compile(r"`[^`\n]+`")),
    ("inline_math", re.compile(r"\$[^$\n]{1,200}\$")),
    ("latex_cmd", re.compile(r"\\(?:cite|citep|citet|ref|eqref|label|autoref)\{[^}]*\}")),
    ("url", re.compile(r"https?://\S+|doi:\S+|www\.\S+")),
    ("numeric_citation", re.compile(r"\[\d+(?:[,;–-]\s*\d+)*\]")),
    ("author_citation", re.compile(r"\[[A-Z][A-Za-z.\-']+(?:\s+(?:et\s+al\.?|and|&)\s+[A-Za-z.\-']+)*,?\s*\d{4}[a-z]?(?:\s*;[^\]]+)*\]")),
)

_ABBREVIATIONS: tuple[str, ...] = (
    "e.g.", "i.e.", "cf.", "vs.", "et al.", "Fig.", "Figs.", "Eq.", "Eqs.",
    "Tab.", "Sec.", "Ref.", "Refs.", "approx.", "no.", "No.", "Dr.", "Prof.",
    "Mr.", "Ms.", "St.", "Inc.", "Ltd.", "cca.", "resp.", "min.", "max.",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[A-Z\"'(\[])")
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


@dataclass
class Document:
    """A parsed document with prose isolated from technical spans."""

    path: Path
    raw: str
    prose: str
    paragraphs: list[str]
    sentences: list[str]
    tokens: list[str]
    masked_counts: Counter

    @property
    def n_tokens(self) -> int:
        """Number of prose tokens after masking."""
        return len(self.tokens)

    @property
    def kilowords(self) -> float:
        """Token count in thousands, floored to avoid division by zero."""
        return max(self.n_tokens, 1) / 1000.0


class DocumentParser:
    """Turns raw text into a :class:`Document`.

    Masking removes code, mathematics, citations, and URLs before any counting.
    Editing those spans is out of scope for the skill, and leaving them in
    distorts every rate.
    """

    def parse(self, path: Path, raw: str) -> Document:
        """Parse ``raw`` into a :class:`Document`, or raise :class:`InputError`."""
        prose, masked = self._mask(raw)
        paragraphs = self._paragraphs(prose)
        sentences = self._sentences(prose)
        tokens = [w.lower() for w in _WORD.findall(prose)]
        if not tokens:
            raise InputError(f"{path}: no prose found after masking")
        if len(tokens) < MIN_TOKENS_FOR_STABLE_METRICS:
            LOGGER.warning(
                "%s: only %d prose tokens; rates are unstable below %d",
                path, len(tokens), MIN_TOKENS_FOR_STABLE_METRICS,
            )
        return Document(path, raw, prose, paragraphs, sentences, tokens, masked)

    @staticmethod
    def _mask(raw: str) -> tuple[str, Counter]:
        """Replace technical spans with whitespace, counting what was removed."""
        counts: Counter = Counter()
        text = raw
        for name, pattern in _MASK_PATTERNS:
            text, n = pattern.subn(" ", text)
            counts[name] = n
        # Structural lines that are not running prose. Detectors exclude these
        # too, and counting them distorts every sentence-level statistic.
        text = re.sub(r"^\s{0,3}#{1,6}\s.*$", " ", text, flags=re.M)
        table_or_list = re.compile(r"^\s*(?:\||[-*+•]\s|\d+[.)]\s|>\s|\[.+\]:).*$", re.M)
        text, n_struct = table_or_list.subn(" ", text)
        counts["structural_line"] = n_struct
        text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})?", " ", text)
        return text, counts

    @staticmethod
    def _paragraphs(prose: str) -> list[str]:
        """Split into paragraphs, dropping blocks too short to profile."""
        blocks = [b.strip() for b in re.split(r"\n\s*\n", prose)]
        return [b for b in blocks if len(_WORD.findall(b)) >= 15]

    @staticmethod
    def _sentences(prose: str) -> list[str]:
        """Segment into sentences, protecting abbreviations and decimals."""
        protected = prose
        for i, abbr in enumerate(_ABBREVIATIONS):
            protected = protected.replace(abbr, f"\x00{i}\x00")
        protected = re.sub(r"(\d)\.(\d)",
                           lambda m: f"{m.group(1)}\x01{m.group(2)}", protected)
        parts = _SENTENCE_SPLIT.split(protected.replace("\n", " "))
        restored: list[str] = []
        for part in parts:
            for i, abbr in enumerate(_ABBREVIATIONS):
                part = part.replace(f"\x00{i}\x00", abbr)
            part = part.replace("\x01", ".").strip()
            if len(_WORD.findall(part)) >= 3:
                restored.append(part)
        return restored


# --------------------------------------------------------------------------- #
# Feature extraction
# --------------------------------------------------------------------------- #


def _count_syllables(word: str) -> int:
    """Estimate syllables by counting vowel groups; a standard cheap proxy."""
    groups = re.findall(r"[aeiouy]+", word.lower())
    n = len(groups)
    if word.lower().endswith("e") and n > 1:
        n -= 1
    return max(n, 1)


def _rate(count: int, doc: Document) -> float:
    """Convert a raw count to a per-1000-word rate."""
    return count / doc.kilowords


def _metric(key: str, label: str, value: float, unit: str,
            instances: Sequence[str] = ()) -> Metric:
    """Build a :class:`Metric`, looking its band up by key."""
    return Metric(key, label, value, unit, BANDS.get(key, Band()), list(instances))


class FeatureExtractor:
    """Computes the metric bank for one document.

    Each ``_f_*`` method is a small, independent extractor returning one or
    more metrics. They are collected by :meth:`extract`, which keeps the
    orchestration flat and each extractor individually testable.
    """

    def extract(self, doc: Document) -> list[Metric]:
        """Run every extractor and return the flattened metric list."""
        extractors: tuple[Callable[[Document], Iterable[Metric]], ...] = (
            self._f_size, self._f_sentence_shape, self._f_word_shape,
            self._f_function_words, self._f_diversity, self._f_nominalization,
            self._f_participials, self._f_passive, self._f_stance,
            self._f_transitions, self._f_vocabulary, self._f_punctuation,
            self._f_rhetorical, self._f_layout,
        )
        metrics: list[Metric] = []
        for extractor in extractors:
            metrics.extend(extractor(doc))
        return metrics

    # -- size and shape ----------------------------------------------------- #

    def _f_size(self, doc: Document) -> Iterable[Metric]:
        """Document size, reported for context rather than judged."""
        yield _metric("tokens", "Prose tokens", float(doc.n_tokens), "words")
        yield _metric("sentences", "Sentences", float(len(doc.sentences)), "n")

    def _f_sentence_shape(self, doc: Document) -> Iterable[Metric]:
        """Sentence-length centre and dispersion."""
        lengths = [len(_WORD.findall(s)) for s in doc.sentences]
        if len(lengths) < 2:
            yield _metric("median_sentence_len", "Median sentence length",
                          float(lengths[0] if lengths else 0), "tokens")
            return
        mu = statistics.fmean(lengths)
        sigma = statistics.stdev(lengths)
        yield _metric("median_sentence_len", "Median sentence length",
                      float(statistics.median(lengths)), "tokens")
        # CV is the primary dispersion measure: it is positive, scale-free, and
        # directly interpretable. B_G is reported for continuity with the
        # detection literature, where it is near-always negative for sentence
        # lengths because sigma < mu; it is not banded for that reason.
        yield _metric("sentence_len_cv", "Sentence-length CV",
                      sigma / mu if mu else 0.0, "ratio")
        yield _metric("burstiness_goh", "Burstiness B_G",
                      (sigma - mu) / (sigma + mu) if (sigma + mu) else 0.0, "")
        yield _metric("burstiness_fano", "Burstiness B_F",
                      (sigma ** 2) / mu if mu else 0.0, "")

    def _f_word_shape(self, doc: Document) -> Iterable[Metric]:
        """Word length and polysyllabic share: the Latinate-drift proxy."""
        lengths = [len(t) for t in doc.tokens]
        poly = [t for t in doc.tokens if _count_syllables(t) >= 3]
        yield _metric("mean_word_length", "Mean word length",
                      statistics.fmean(lengths), "chars")
        yield _metric("polysyllabic_share", "Polysyllabic share",
                      len(poly) / doc.n_tokens, "fraction")

    def _f_function_words(self, doc: Document) -> Iterable[Metric]:
        """Function-word ratio and its complement, lexical density."""
        n_func = sum(1 for t in doc.tokens if t in FUNCTION_WORDS)
        ratio = n_func / doc.n_tokens
        yield _metric("function_word_ratio", "Function-word ratio", ratio, "fraction")
        yield _metric("lexical_density", "Lexical density (proxy)", 1 - ratio, "fraction")

    def _f_diversity(self, doc: Document) -> Iterable[Metric]:
        """Length-stabilised lexical diversity."""
        yield _metric("mattr", f"MATTR (w={MATTR_WINDOW})",
                      self._mattr(doc.tokens, MATTR_WINDOW), "fraction")

    @staticmethod
    def _mattr(tokens: Sequence[str], window: int) -> float:
        """Moving-average type-token ratio; length-stabilised diversity."""
        if len(tokens) <= window:
            return len(set(tokens)) / max(len(tokens), 1)
        ratios = [
            len(set(tokens[i:i + window])) / window
            for i in range(len(tokens) - window + 1)
        ]
        return statistics.fmean(ratios)

    # -- syntax proxies ----------------------------------------------------- #

    def _f_nominalization(self, doc: Document) -> Iterable[Metric]:
        """Suffix-based nominalization rate, excluding domain terms."""
        hits = [
            t for t in doc.tokens
            if len(t) >= 7
            and t.endswith(NOMINALIZATION_SUFFIXES)
            and t not in NOMINALIZATION_EXCEPTIONS
        ]
        yield _metric("nominalization_per_kw", "Nominalizations",
                      _rate(len(hits), doc), "per 1k words",
                      [w for w, _ in Counter(hits).most_common(15)])

    def _f_participials(self, doc: Document) -> Iterable[Metric]:
        """Count trailing and fronted participial clauses (heuristic)."""
        trailing = re.compile(r",\s+([a-z]+ing)\b")
        fronted = re.compile(r"(?:^|(?<=[.!?]\s))([A-Z][a-z]+ing)\b[^.!?]{0,120},")
        instances: list[str] = []
        for match in trailing.finditer(doc.prose):
            if match.group(1) not in ING_EXCEPTIONS:
                instances.append(doc.prose[match.start(): match.start() + 60].strip())
        for match in fronted.finditer(doc.prose):
            if match.group(1).lower() not in ING_EXCEPTIONS:
                instances.append(match.group(0)[:60].strip())
        yield _metric("participial_per_kw", "Participial clauses",
                      _rate(len(instances), doc), "per 1k words", instances[:15])

    def _f_passive(self, doc: Document) -> Iterable[Metric]:
        """Count be-passives; reported without a band because genre decides."""
        pattern = re.compile(
            r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?(\w+(?:ed|en))\b")
        hits = [m.group(0) for m in pattern.finditer(doc.prose.lower())]
        yield _metric("passive_per_kw", "Be-passives", _rate(len(hits), doc),
                      "per 1k words", [w for w, _ in Counter(hits).most_common(10)])

    # -- stance and register ------------------------------------------------ #

    def _f_stance(self, doc: Document) -> Iterable[Metric]:
        """Interactional metadiscourse: hedges, boosters, self-mention, attitude."""
        counts = Counter(doc.tokens)
        for key, label, lexicon in (
            ("hedge_per_kw", "Hedges", HEDGES),
            ("booster_per_kw", "Boosters", BOOSTERS),
            ("self_mention_per_kw", "Self-mention", SELF_MENTION),
            ("attitude_per_kw", "Attitude markers", ATTITUDE_MARKERS),
            ("flagged_adverb_per_kw", "Flagged adverbs", FLAGGED_ADVERBS),
        ):
            hits = {w: counts[w] for w in lexicon if counts[w]}
            total = sum(hits.values())
            top = [f"{w}×{n}" for w, n in sorted(hits.items(), key=lambda kv: -kv[1])[:10]]
            yield _metric(key, label, _rate(total, doc), "per 1k words", top)

    def _f_transitions(self, doc: Document) -> Iterable[Metric]:
        """Share of paragraphs whose sentences open with a transition adverb."""
        openers: list[str] = []
        for para in doc.paragraphs:
            for sentence in re.split(r"(?<=[.!?])\s+", para):
                lowered = sentence.strip().lower()
                for opener in TRANSITION_OPENERS:
                    if lowered.startswith(opener):
                        openers.append(sentence.strip()[:50])
                        break
        denominator = max(len(doc.paragraphs), 1)
        yield _metric("transition_opener_ratio", "Transition openers",
                      len(openers) / denominator, "per paragraph", openers[:15])

    def _f_vocabulary(self, doc: Document) -> Iterable[Metric]:
        """Historical drift markers and deletable filler phrases."""
        counts = Counter(doc.tokens)
        drift = {w: counts[w] for w in DRIFT_MARKERS if counts[w]}
        yield _metric("drift_marker_per_kw", "Drift markers",
                      _rate(sum(drift.values()), doc), "per 1k words",
                      [f"{w}×{n}" for w, n in sorted(drift.items(), key=lambda kv: -kv[1])])
        lowered = doc.prose.lower()
        fillers = [(p, lowered.count(p)) for p in FILLER_PHRASES if p in lowered]
        yield _metric("filler_phrase_per_kw", "Filler phrases",
                      _rate(sum(n for _, n in fillers), doc), "per 1k words",
                      [f"{p}×{n}" for p, n in fillers])

    # -- punctuation and rhetoric ------------------------------------------- #

    def _f_punctuation(self, doc: Document) -> Iterable[Metric]:
        """Em-dash, comma, parenthesis, and quotation-mark budgets."""
        # The budget rule is per paragraph, so report the worst paragraph:
        # a document mean hides one paragraph built entirely out of asides.
        def dashes(text: str) -> int:
            """Count em dashes, in Unicode and in LaTeX triple-hyphen form."""
            return text.count("\u2014") + len(re.findall(r"(?<!-)---(?!-)", text))

        per_para = [dashes(p) / 2 for p in doc.paragraphs] or [dashes(doc.prose) / 2]
        yield _metric("emdash_pairs_per_para", "Em-dash pairs (worst para)",
                      max(per_para), "pairs")
        yield _metric("comma_per_sentence", "Commas",
                      doc.prose.count(",") / max(len(doc.sentences), 1), "per sentence")
        yield _metric("paren_per_kw", "Parenthetical pairs",
                      _rate(doc.prose.count("("), doc), "per 1k words")
        curly = sum(doc.raw.count(c) for c in "\u201c\u201d\u2018\u2019")
        yield _metric("curly_quotes", "Curly quotes", float(curly), "count")

    def _f_rhetorical(self, doc: Document) -> Iterable[Metric]:
        """Rule-of-three coordinations and negative parallelism."""
        triads = re.findall(r"\b(\w+), (\w+),? and (\w+)\b", doc.prose)
        yield _metric("triad_per_kw", "Three-item coordinations",
                      _rate(len(triads), doc), "per 1k words",
                      [", ".join(t) for t in triads[:12]])
        neg = re.compile(
            r"(not (?:just|only|merely|simply)\b[^.!?]{0,90}?\b(?:but|it'?s|it is|rather)\b"
            r"|(?:is|are|was|were)n'?t (?:just|only|merely|simply)\b"
            r"|less about\b[^.!?]{0,60}?\band more about\b)", re.I)
        hits = [m.group(0)[:80] for m in neg.finditer(doc.prose)]
        yield _metric("neg_parallelism", "Negative parallelism",
                      float(len(hits)), "count", hits)

    def _f_layout(self, doc: Document) -> Iterable[Metric]:
        """List share and paragraph-length variation."""
        lines = [ln for ln in doc.raw.splitlines() if ln.strip()]
        list_lines = [ln for ln in lines
                      if re.match(r"^\s*(?:[-*+•]|\d+[.)])\s+", ln)]
        yield _metric("list_line_ratio", "List lines",
                      len(list_lines) / max(len(lines), 1), "fraction")
        sizes = [len(_WORD.findall(p)) for p in doc.paragraphs]
        cv = (statistics.stdev(sizes) / statistics.fmean(sizes)
              if len(sizes) > 1 and statistics.fmean(sizes) else 0.0)
        yield _metric("paragraph_len_cv", "Paragraph-length CV", cv, "ratio")


# --------------------------------------------------------------------------- #
# Information-preservation ledger
# --------------------------------------------------------------------------- #

# A number may follow a dash, so both ends of "0.84-0.88", "0.84\u20130.88" and
# "12--18" are captured. A leading sign (ASCII "-", "+", or U+2212 minus) is
# taken only when it is not itself preceded by a digit or a dash, so a range
# separator never becomes a spurious negative sign.
_NUMBER = re.compile(
    r"(?<![\w.])(?:(?<![\d\-\u2013\u2014\u2212])[-+\u2212])?\d[\d,]*(?:\.\d+)?\s*%?"
)
_MINUS = "\u2212"
_CITE_KEY = re.compile(r"\\cite[a-z]*\{([^}]*)\}")
_AUTHOR_YEAR = re.compile(r"[A-Z][A-Za-z.\-']+(?:\s+et\s+al\.?)?,?\s*\(?\b(19|20)\d{2}\b")
_XREF = re.compile(r"(?:§|Sec\.?|Section|Fig\.?|Figure|Table|Eq\.?|Equation|Appendix)\s*~?\s*[A-Z]?\d+(?:\.\d+)*")


@dataclass
class Ledger:
    """Extracted information atoms used to verify that a rewrite lost nothing."""

    numbers: Counter
    citations: Counter
    crossrefs: Counter

    @classmethod
    def from_text(cls, text: str) -> "Ledger":
        """Extract numbers, citation keys, and cross-references from ``text``."""
        numbers = Counter(
            re.sub(r"[\s,]", "", m.group(0)).replace(_MINUS, "-")
            for m in _NUMBER.finditer(text)
        )
        citations: Counter = Counter()
        for match in _CITE_KEY.finditer(text):
            citations.update(k.strip() for k in match.group(1).split(",") if k.strip())
        citations.update(m.group(0).strip() for m in _AUTHOR_YEAR.finditer(text))
        crossrefs = Counter(re.sub(r"\s+", " ", m.group(0)) for m in _XREF.finditer(text))
        return cls(numbers, citations, crossrefs)

    def diff(self, other: "Ledger") -> dict[str, dict[str, list[str]]]:
        """Return items lost from ``self`` and added in ``other``, per category."""
        result: dict[str, dict[str, list[str]]] = {}
        for name, before, after in (
            ("numbers", self.numbers, other.numbers),
            ("citations", self.citations, other.citations),
            ("crossrefs", self.crossrefs, other.crossrefs),
        ):
            result[name] = {
                "lost": sorted((before - after).elements()),
                "added": sorted((after - before).elements()),
            }
        return result


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

_SYMBOL: dict[Flag, str] = {
    Flag.OK: "ok", Flag.HIGH: "HIGH", Flag.LOW: "LOW", Flag.INFO: "--",
}


class Reporter:
    """Renders analysis results as a table or as JSON."""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def table(self, path: Path, metrics: Sequence[Metric],
              baseline: dict[str, float] | None = None) -> str:
        """Render one document's metrics as a fixed-width table."""
        lines = [f"\n=== {path} ===",
                 f"{'metric':<28}{'value':>10}{'target':>14}{'flag':>7}"
                 + ("   baseline" if baseline else "")]
        lines.append("-" * (59 + (11 if baseline else 0)))
        for metric in metrics:
            row = (f"{metric.label:<28}{metric.value:>10.3f}"
                   f"{metric.band.render():>14}{_SYMBOL[metric.flag]:>7}")
            if baseline is not None and metric.key in baseline:
                delta = metric.value - baseline[metric.key]
                row += f"   {baseline[metric.key]:>7.3f} ({delta:+.2f})"
            lines.append(row)
            if self.verbose and metric.instances:
                for item in metric.instances[:8]:
                    lines.append(f"    · {item}")
        return "\n".join(lines)

    @staticmethod
    def summary(metrics: Sequence[Metric]) -> list[str]:
        """Return the flagged metric labels, worst-first by category."""
        return [f"{m.label} ({_SYMBOL[m.flag]}, {m.value:.2f})"
                for m in metrics if m.flag in (Flag.HIGH, Flag.LOW)]


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


class Analyzer:
    """Top-level entry point: reads inputs, extracts features, aggregates."""

    def __init__(self) -> None:
        self.parser = DocumentParser()
        self.extractor = FeatureExtractor()

    def analyse_path(self, target: Path) -> dict[Path, list[Metric]]:
        """Analyse a file or every text file in a directory."""
        results: dict[Path, list[Metric]] = {}
        for path in self._iter_inputs(target):
            try:
                doc = self.parser.parse(path, path.read_text(encoding="utf-8"))
            except (InputError, UnicodeDecodeError) as exc:
                LOGGER.warning("skipping %s: %s", path, exc)
                continue
            results[path] = self.extractor.extract(doc)
        if not results:
            raise InputError(f"no analysable text found at {target}")
        return results

    @staticmethod
    def _iter_inputs(target: Path) -> Iterator[Path]:
        """Yield the text files implied by a file or directory target."""
        if not target.exists():
            raise InputError(f"path does not exist: {target}")
        if target.is_file():
            yield target
            return
        for path in sorted(target.rglob("*")):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                yield path

    @staticmethod
    def aggregate(results: dict[Path, list[Metric]]) -> dict[str, float]:
        """Mean of each metric across documents; the calibration baseline."""
        buckets: dict[str, list[float]] = {}
        for metrics in results.values():
            for metric in metrics:
                buckets.setdefault(metric.key, []).append(metric.value)
        return {k: statistics.fmean(v) for k, v in buckets.items()}


def load_baseline(spec: str) -> dict[str, float]:
    """Load a baseline from a JSON file, or compute one from a text path."""
    path = Path(spec)
    if not path.exists():
        raise BaselineError(f"baseline not found: {spec}")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BaselineError(f"malformed baseline JSON: {exc}") from exc
        values = data.get("baseline", data)
        if not isinstance(values, dict):
            raise BaselineError("baseline JSON must map metric keys to numbers")
        return {k: float(v) for k, v in values.items() if isinstance(v, (int, float))}
    return Analyzer().aggregate(Analyzer().analyse_path(path))


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line interface."""
    parser = argparse.ArgumentParser(
        prog="stylometry.py",
        description="Stylometric diagnostics for the humanizer skill.",
        epilog="Rates are heuristic proxies; prefer --baseline calibration.",
    )
    parser.add_argument("target", type=Path, nargs="?",
                        help="file or directory to analyse")
    parser.add_argument("--baseline", metavar="PATH",
                        help="author corpus or baseline.json to calibrate against")
    parser.add_argument("--emit-baseline", action="store_true",
                        help="print the aggregate profile as a baseline JSON")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), type=Path,
                        help="diff two versions and check information preservation")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="list matched instances under each flagged metric")
    return parser


def _run_compare(before: Path, after: Path, as_json: bool) -> int:
    """Run the ledger diff.

    Returns exit code 1 if any number, citation, or cross-reference was lost
    or added: the contract forbids both deletion and invention.
    """
    ledger_before = Ledger.from_text(before.read_text(encoding="utf-8"))
    ledger_after = Ledger.from_text(after.read_text(encoding="utf-8"))
    diff = ledger_before.diff(ledger_after)
    lost = any(v["lost"] for v in diff.values())
    added = any(v["added"] for v in diff.values())
    failed = lost or added
    if as_json:
        print(json.dumps({"diff": diff, "passed": not failed}, indent=2))
    else:
        print(f"\n=== ledger: {before.name} -> {after.name} ===")
        for category, entry in diff.items():
            print(f"{category:<12} lost={len(entry['lost']):<4} added={len(entry['added'])}")
            for item in entry["lost"][:20]:
                print(f"    LOST  {item}")
            for item in entry["added"][:20]:
                print(f"    ADDED {item}")
        reasons = [r for r, hit in (("lost", lost), ("added", added)) if hit]
        print("\nledger check: "
              + (f"FAIL - information {' and '.join(reasons)}" if failed else "PASS"))
    return 1 if failed else 0


def _run_analysis(args: argparse.Namespace) -> int:
    """Run the profiling path of the CLI."""
    analyzer = Analyzer()
    results = analyzer.analyse_path(args.target)
    baseline = load_baseline(args.baseline) if args.baseline else None

    if args.emit_baseline:
        print(json.dumps({"version": __version__,
                          "baseline": {k: round(v, 4)
                                       for k, v in analyzer.aggregate(results).items()}},
                         indent=2))
        return 0

    if args.json:
        payload = {
            "version": __version__,
            "documents": {
                str(path): {
                    "metrics": [m.to_dict() for m in metrics],
                    "flagged": Reporter.summary(metrics),
                }
                for path, metrics in results.items()
            },
        }
        print(json.dumps(payload, indent=2))
        return 0

    reporter = Reporter(verbose=args.verbose)
    for path, metrics in results.items():
        print(reporter.table(path, metrics, baseline))
        flagged = reporter.summary(metrics)
        print("\nflagged: " + (", ".join(flagged) if flagged else "none"))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    args = build_parser().parse_args(argv)
    try:
        if args.compare:
            return _run_compare(*args.compare, as_json=args.json)
        if args.target is None:
            build_parser().error("a target path is required unless --compare is used")
        return _run_analysis(args)
    except HumanizerError as exc:
        LOGGER.error("%s", exc)
        return 2
    except BrokenPipeError:
        # Downstream pager or `head` closed the pipe; not an error condition.
        # Redirect stdout to devnull so the interpreter's flush at exit is quiet.
        import os
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
