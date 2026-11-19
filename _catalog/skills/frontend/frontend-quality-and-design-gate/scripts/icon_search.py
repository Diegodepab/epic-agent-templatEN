#!/usr/bin/env python3
"""BM25 semantic icon search over the bundled icons.csv dataset."""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data" / "icons.csv"


def tokenize(text: str) -> list[str]:
    return [t for t in re.sub(r"[^a-z0-9\s-]", " ", text.lower()).split() if len(t) > 1]


def search_icons(query: str, limit: int = 8) -> list[dict[str, str]]:
    with DATA_FILE.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    docs = [tokenize(" ".join(row.values())) for row in rows]
    n_docs = len(docs)
    avgdl = sum(len(d) for d in docs) / max(1, n_docs)

    df: Counter[str] = Counter()
    for doc in docs:
        for tok in set(doc):
            df[tok] += 1

    q_tokens = tokenize(query)
    scored: list[tuple[float, dict[str, str]]] = []
    k1, b = 1.5, 0.75

    for row, doc in zip(rows, docs):
        tf = Counter(doc)
        doc_len = len(doc)
        score = 0.0
        for tok in q_tokens:
            if tok not in tf:
                continue
            idf = math.log((n_docs - df[tok] + 0.5) / (df[tok] + 0.5) + 1.0)
            freq = tf[tok]
            score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * doc_len / avgdl))
        if score > 0:
            scored.append((score, row))

    scored.sort(key=lambda item: -item[0])
    return [row for _, row in scored[:limit]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Search consistent SVG icons from icons.csv.")
    parser.add_argument("query", help="Semantic icon query, e.g. 'analytics chart dashboard'")
    parser.add_argument("-n", "--limit", type=int, default=8)
    args = parser.parse_args()

    results = search_icons(args.query, args.limit)
    if not results:
        print(f"No icons matched `{args.query}`.")
        return 0

    for idx, row in enumerate(results, start=1):
        name = row.get("Icon Name") or row.get("Name") or next(iter(row.values()), "")
        cat = row.get("Category", "")
        import_code = row.get("Import Code", "")
        best_for = row.get("Best For", "")
        print(f"{idx}. {name} [{cat}] — {best_for} | {import_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
