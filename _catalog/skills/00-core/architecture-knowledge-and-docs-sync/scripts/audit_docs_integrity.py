#!/usr/bin/env python3
"""Audits documentation role separation, relative links, Mermaid blocks, and ADR sync."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

CORE_DOCS = ("README.md", "docs/ARCHITECTURE.md", "docs/USER_GUIDE.md", "AGENTS.md")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#\s]+)")
MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
SUPPORTED_MERMAID = (
    "flowchart ",
    "graph ",
    "sequenceDiagram",
    "stateDiagram",
    "classDiagram",
    "erDiagram",
    "xychart-beta",
)


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int | None
    detail: str


def normalize_paragraph(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def check_cross_doc_duplication(root: Path) -> list[Finding]:
    """Detect substantial paragraph duplication across core docs."""
    findings: list[Finding] = []
    seen_hashes: dict[str, tuple[str, str]] = {}

    for rel in CORE_DOCS:
        p = root / rel
        if not p.is_file():
            continue
        blocks = re.split(r"\n\s*\n", p.read_text(encoding="utf-8", errors="replace"))
        for block in blocks:
            stripped = block.strip()
            if stripped.startswith(("#", "|", "```", ">")) or len(stripped) < 110:
                continue
            norm = normalize_paragraph(stripped)
            digest = hashlib.sha256(norm.encode()).hexdigest()[:16]
            if digest in seen_hashes:
                prev_doc, snippet = seen_hashes[digest]
                if prev_doc != rel:
                    findings.append(
                        Finding(
                            "HIGH",
                            "doc-duplication",
                            rel,
                            None,
                            f"Duplicates paragraph already in `{prev_doc}`: `{snippet[:60]}...`",
                        )
                    )
            else:
                seen_hashes[digest] = (rel, stripped)
    return findings


def check_links_and_mermaid(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    md_files = [root / r for r in CORE_DOCS if (root / r).is_file()]
    adr_dir = root / "docs" / "adr"
    if adr_dir.is_dir():
        md_files.extend(sorted(adr_dir.glob("*.md")))

    for md in md_files:
        text = md.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in LINK_RE.finditer(line):
                target = match.group(1)
                if target.startswith(("http://", "https://", "mailto:", "file://", "conversation://")):
                    continue
                resolved = (md.parent / target).resolve()
                if not resolved.exists():
                    findings.append(
                        Finding(
                            "HIGH",
                            "broken-link",
                            md.relative_to(root).as_posix(),
                            lineno,
                            f"Relative link target does not exist: `{target}`",
                        )
                    )

        for block_match in MERMAID_BLOCK_RE.finditer(text):
            body = block_match.group(1).strip()
            if not body:
                continue
            first_line = body.splitlines()[0].strip()
            if not any(first_line.startswith(prefix) for prefix in SUPPORTED_MERMAID):
                findings.append(
                    Finding(
                        "MEDIUM",
                        "mermaid-diagram-type",
                        md.relative_to(root).as_posix(),
                        None,
                        f"Unsupported Mermaid header `{first_line}` (use flowchart/sequence/state/class/er)",
                    )
                )
    return findings


def check_adr_index(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    adr_dir = root / "docs" / "adr"
    readme = adr_dir / "README.md"
    if not adr_dir.is_dir() or not readme.is_file():
        return findings

    index_text = readme.read_text(encoding="utf-8", errors="replace")
    for adr in sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        if adr.name == "0000-template.md":
            continue
        if adr.name not in index_text:
            findings.append(
                Finding(
                    "HIGH",
                    "adr-index-drift",
                    "docs/adr/README.md",
                    None,
                    f"ADR `{adr.name}` is not linked in docs/adr/README.md index table",
                )
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit docs role separation, links, Mermaid, and ADR sync.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--json-out", help="Optional normalized JSON output path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings: list[Finding] = []
    findings.extend(check_cross_doc_duplication(root))
    findings.extend(check_links_and_mermaid(root))
    findings.extend(check_adr_index(root))

    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]
    print(f"[docs-audit] root={root.name} findings={len(findings)} blocking={len(blocking)}")
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        print(f"  {f.severity:8s} [{f.rule}] {loc}: {f.detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "docs-integrity-and-role-auditor",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "score": max(0, 100 - len(findings) * 15),
                    "summary": {"findings": len(findings), "blocking": len(blocking)},
                    "findings": [asdict(f) for f in findings],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
