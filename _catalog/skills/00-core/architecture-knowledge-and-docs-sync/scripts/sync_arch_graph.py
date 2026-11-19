#!/usr/bin/env python3
"""Extracts high-level code blocks, key exported roles, and real dependency edges
into docs/ARCHITECTURE.md (between ARCH_GRAPH markers) and detects architectural drift.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

START_MARKER = "<!-- ARCH_GRAPH:START -->"
END_MARKER = "<!-- ARCH_GRAPH:END -->"

IGNORE_DIRS = {
    ".git",
    ".agents",
    "_catalog",
    "_reference",
    "node_modules",
    ".venv",
    "venv",
    ".godot",
    "__pycache__",
    "dist",
    "build",
    "out",
    "bin",
    "obj",
    "tests",
    "test",
}
SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".svelte", ".astro", ".cs"}
TS_EXPORT_RE = re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|interface|type)\s+([A-Za-z0-9_]+)", re.MULTILINE)
TS_IMPORT_RE = re.compile(r"""from\s+['"](\.[^'"]+)['"]""")
CS_CLASS_RE = re.compile(r"\b(?:public|internal)\s+(?:partial\s+)?(?:class|interface|struct|record)\s+([A-Za-z0-9_]+)")


@dataclass
class BlockStats:
    block_id: str
    path: str
    files: int = 0
    lines: int = 0
    exports: list[str] = field(default_factory=list)
    depends_on: set[str] = field(default_factory=set)


def resolve_block(rel_path: Path) -> str:
    """Group source files into readable high-level functional blocks."""
    parts = rel_path.parts
    if not parts:
        return "root"
    if parts[0] in {"src", "backend", "frontend", "Scripts", "app"}:
        if len(parts) >= 3:
            # Skip single src/<pkg>/ wrapper depth when nested (e.g. src/pkg/domain -> domain)
            if parts[0] in {"src", "backend"} and len(parts) >= 4:
                return f"{parts[0]}/{parts[2]}"
            return f"{parts[0]}/{parts[1]}"
        return parts[0]
    return parts[0]


def scan_python(source: str) -> tuple[list[str], list[str]]:
    exports: list[str] = []
    imports: list[str] = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source)
    except SyntaxError:
        return [], []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            exports.append(node.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
    return exports, imports


def build_architecture_graph(root: Path) -> tuple[dict[str, BlockStats], dict[str, str]]:
    blocks: dict[str, BlockStats] = {}
    file_entries: list[tuple[Path, str, list[str], list[str]]] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS and not d.startswith("."))
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            if fpath.suffix not in SOURCE_EXTS or fname.startswith("test_"):
                continue
            rel = fpath.relative_to(root)
            block_name = resolve_block(rel)
            text = fpath.read_text(encoding="utf-8", errors="replace")

            if fpath.suffix == ".py":
                exps, imps = scan_python(text)
            elif fpath.suffix == ".cs":
                exps = CS_CLASS_RE.findall(text)
                imps = re.findall(r"using\s+([A-Za-z0-9_.]+);", text)
            else:
                exps = TS_EXPORT_RE.findall(text)
                imps = TS_IMPORT_RE.findall(text)

            st = blocks.setdefault(block_name, BlockStats(block_id=re.sub(r"[^a-zA-Z0-9_]", "_", block_name), path=block_name))
            st.files += 1
            st.lines += len(text.splitlines())
            for e in exps:
                if e not in st.exports:
                    st.exports.append(e)
            file_entries.append((rel, block_name, exps, imps))

    # Resolve block-to-block dependencies by matching module/folder leaf tokens in imports
    block_tokens = {b: b.split("/")[-1].lower() for b in blocks if len(b.split("/")[-1]) >= 3}
    for _rel, src_block, _exps, imps in file_entries:
        for imp in imps:
            imp_low = imp.lower()
            for target_block, leaf in block_tokens.items():
                if target_block != src_block and re.search(rf"(?:^|[./]){re.escape(leaf)}(?:$|[./])", imp_low):
                    blocks[src_block].depends_on.add(target_block)

    meta = {"blocks": str(len(blocks)), "files": str(sum(b.files for b in blocks.values()))}
    return blocks, meta


def render_arch_section(blocks: dict[str, BlockStats]) -> str:
    if not blocks:
        return (
            f"{START_MARKER}\n"
            "_No source code modules scanned yet. Run `sync_arch_graph.py --write` once code is added._\n"
            f"{END_MARKER}"
        )

    lines = [
        START_MARKER,
        "### Block Dependency Graph (Auto-Generated from Code)",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for name in sorted(blocks):
        b = blocks[name]
        lines.append(f'    {b.block_id}["{b.path} ({b.files}f, {b.lines}L)"]')
    has_edges = False
    for name in sorted(blocks):
        b = blocks[name]
        for dep in sorted(b.depends_on):
            if dep in blocks:
                lines.append(f"    {b.block_id} --> {blocks[dep].block_id}")
                has_edges = True
    if not has_edges and len(blocks) == 1:
        b = next(iter(blocks.values()))
        lines.append(f'    {b.block_id} --> Out["Outputs / CLI / Runtime"]')
    lines.extend(
        [
            "```",
            "",
            "### High-Level Functional Blocks",
            "",
            "| Block | Files / LOC | Key Public Symbols & Roles | Depends On |",
            "| :--- | :---: | :--- | :--- |",
        ]
    )
    for name in sorted(blocks):
        b = blocks[name]
        syms = ", ".join(f"`{s}`" for s in b.exports[:6]) or "_Module entrypoints_"
        deps = ", ".join(f"`{d}`" for d in sorted(b.depends_on)) or "—"
        lines.append(f"| `{b.path}` | {b.files} / {b.lines}L | {syms} | {deps} |")
    lines.append(END_MARKER)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync docs/ARCHITECTURE.md live knowledge graph with real source modules.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--arch-file", default="docs/ARCHITECTURE.md", help="Target ARCHITECTURE.md path")
    parser.add_argument("--write", action="store_true", help="Update ARCH_GRAPH block inside ARCHITECTURE.md")
    parser.add_argument("--check-drift", action="store_true", help="Fail exit 1 if ARCHITECTURE.md graph is stale")
    parser.add_argument("--json-out", default=".agents/arch_graph.json", help="Write compact machine graph JSON (or '' to skip)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    arch_path = root / args.arch_file
    blocks, meta = build_architecture_graph(root)
    rendered_block = render_arch_section(blocks)

    if args.json_out:
        jp = root / args.json_out if not Path(args.json_out).is_absolute() else Path(args.json_out)
        jp.parent.mkdir(parents=True, exist_ok=True)
        graph_json = {
            "summary": meta,
            "blocks": {
                k: {
                    "files": v.files,
                    "lines": v.lines,
                    "exports": v.exports[:12],
                    "depends_on": sorted(v.depends_on),
                }
                for k, v in sorted(blocks.items())
            },
        }
        jp.write_text(json.dumps(graph_json, indent=2) + "\n", encoding="utf-8")

    if not arch_path.is_file():
        if args.check_drift:
            print(f"FAIL [arch-drift] Missing {arch_path}", file=sys.stderr)
            return 1
        print(rendered_block)
        return 0

    existing = arch_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL)

    if args.check_drift:
        match = pattern.search(existing)
        if not match:
            print("FAIL [arch-drift] Missing ARCH_GRAPH markers in docs/ARCHITECTURE.md. Run `--write`.", file=sys.stderr)
            return 1
        if match.group(0).strip() != rendered_block.strip():
            print("FAIL [arch-drift] docs/ARCHITECTURE.md knowledge graph is out of sync with code. Run `--write`.", file=sys.stderr)
            return 1
        print(f"[arch-sync] UP TO DATE ({meta['blocks']} blocks, {meta['files']} files)")
        return 0

    if args.write:
        if pattern.search(existing):
            updated = pattern.sub(rendered_block, existing)
        else:
            updated = existing.rstrip() + "\n\n---\n\n## 6. Live Module Knowledge Graph\n\n" + rendered_block + "\n"
        arch_path.write_text(updated, encoding="utf-8")
        print(f"[arch-sync] Updated {arch_path} ({meta['blocks']} blocks, {meta['files']} files)")
    else:
        print(rendered_block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
