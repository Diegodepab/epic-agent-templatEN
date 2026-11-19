#!/usr/bin/env python3
"""Logical symbol map, task context-pack, and external reference-repo digester.

1. Default mode: extracts classes, functions, signatures, exports, and internal
   imports via Python AST and TS/JS/C# parsers into `.agents/REPO_MAP.md`.
2. `--digest-reference <path>`: distills cloned reference repos into concise
   dossiers under `_reference/digests/<repo>.md` (license, footprint, runnable
   engines vs prompt-only skills, and top public symbols) without context bloat.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_IGNORES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    ".godot",
    "__pycache__",
    "_reference",
    "_catalog",
    "dist",
    "build",
    "out",
    "bin",
    "obj",
    ".next",
    ".svelte-kit",
    ".astro",
    ".agents",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

SUPPORTED_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".svelte", ".astro", ".cs"}
ENGINE_EXTS = {".py", ".go", ".mjs", ".cjs", ".js", ".ts", ".sh", ".rs"}

TS_EXPORT_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?(function|class|const|type|interface|enum)\s+([A-Za-z0-9_]+)\s*(\([^)]*\))?",
    re.MULTILINE,
)
TS_FUNC_RE = re.compile(r"^\s*(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*(\([^)]*\))", re.MULTILINE)
TS_IMPORT_RE = re.compile(r"""from\s+['"](\.[^'"]+)['"]""")

CS_CLASS_RE = re.compile(
    r"^\s*(?:public|internal|private|protected)?\s*(?:partial\s+|sealed\s+|abstract\s+|static\s+)*"
    r"(class|interface|struct|record|enum)\s+([A-Za-z0-9_<>]+)",
    re.MULTILINE,
)
CS_METHOD_RE = re.compile(
    r"^\s*(?:public|protected|internal)\s+(?:override\s+|virtual\s+|static\s+|async\s+)*"
    r"([A-Za-z0-9_<>\[\]?]+)\s+([A-Za-z0-9_]+)\s*(\([^)]*\))",
    re.MULTILINE,
)


@dataclass
class FileSummary:
    rel_path: str
    symbols: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    line_count: int = 0
    hotness: int = 0
    relevance: int = 0


def _format_args(args: ast.arguments) -> str:
    names = [a.arg for a in args.posonlyargs + args.args if a.arg not in {"self", "cls"}]
    if args.vararg:
        names.append(f"*{args.vararg.arg}")
    names.extend(a.arg for a in args.kwonlyargs)
    if args.kwarg:
        names.append(f"**{args.kwarg.arg}")
    joined = ", ".join(names[:5]) + (", ..." if len(names) > 5 else "")
    return f"({joined})"


def extract_python(source: str) -> tuple[list[str], list[str]]:
    import warnings

    symbols: list[str] = []
    imports: list[str] = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source)
    except SyntaxError:
        return ["[syntax-error]"], []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            symbols.append(f"{prefix} {node.name}{_format_args(node.args)}")
        elif isinstance(node, ast.ClassDef):
            methods = [
                f"{m.name}{_format_args(m.args)}"
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("_")
            ]
            m_str = f" [{', '.join(methods[:6])}]" if methods else ""
            symbols.append(f"class {node.name}{m_str}")
        elif isinstance(node, ast.ImportFrom) and node.module and (node.level > 0 or "." in node.module):
            imports.append(node.module)
    return symbols, sorted(set(imports))[:5]


def extract_ts_js(source: str) -> tuple[list[str], list[str]]:
    symbols: list[str] = []
    seen: set[str] = set()
    for kind, name, sig in TS_EXPORT_RE.findall(source):
        sig_clean = re.sub(r"\s+", " ", sig).strip() if sig else ""
        entry = f"export {kind} {name}{sig_clean}"
        if entry not in seen:
            symbols.append(entry)
            seen.add(entry)
    for name, sig in TS_FUNC_RE.findall(source):
        if name not in seen and not name.startswith("_"):
            symbols.append(f"fn {name}{re.sub(r'\s+', ' ', sig).strip()}")
            seen.add(name)
    return symbols, sorted(set(TS_IMPORT_RE.findall(source)))[:5]


def extract_csharp(source: str) -> tuple[list[str], list[str]]:
    symbols = [f"{kind} {name}" for kind, name in CS_CLASS_RE.findall(source)]
    for ret, name, sig in CS_METHOD_RE.findall(source):
        if name not in {"if", "for", "while", "switch", "catch", "using"}:
            symbols.append(f"{ret} {name}{re.sub(r'\s+', ' ', sig).strip()}")
    return symbols[:12], []


def git_hotspots(root: Path) -> dict[str, int]:
    try:
        proc = subprocess.run(
            ["git", "log", "-n", "60", "--name-only", "--pretty=format:"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except OSError:
        return {}
    if proc.returncode != 0:
        return {}
    counts: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        if line.strip():
            counts[line.strip()] = counts.get(line.strip(), 0) + 1
    return counts


def iter_source_files(root: Path, ignores: set[str]) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in ignores and not d.startswith(".git"))
        for fname in sorted(filenames):
            p = Path(dirpath) / fname
            if p.suffix in SUPPORTED_EXTS:
                files.append(p)
    return files


def build_repo_map(
    root: Path,
    ignores: set[str],
    task_query: str,
    max_files: int,
    skip_tests: bool = False,
) -> tuple[list[FileSummary], int]:
    hotspots = git_hotspots(root)
    keywords = [w.lower() for w in re.findall(r"[A-Za-z0-9_]{3,}", task_query)]
    summaries: list[FileSummary] = []

    all_files = iter_source_files(root, ignores)
    for path in all_files:
        rel = path.relative_to(root).as_posix()
        if skip_tests and (
            any(pt in {"test", "tests", "__tests__"} for pt in path.parts)
            or path.name.startswith("test_")
            or ".test." in path.name
            or ".spec." in path.name
        ):
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".py":
            symbols, imports = extract_python(source)
        elif path.suffix == ".cs":
            symbols, imports = extract_csharp(source)
        else:
            symbols, imports = extract_ts_js(source)

        if not symbols:
            continue
        item = FileSummary(rel, symbols[:12], imports, len(source.splitlines()), hotspots.get(rel, 0))
        if keywords:
            haystack = (rel + " " + " ".join(symbols)).lower()
            item.relevance = sum(3 for kw in keywords if kw in haystack) * 10 + item.hotness
        else:
            item.relevance = item.hotness
        summaries.append(item)

    summaries.sort(key=lambda s: (-s.relevance, s.rel_path))
    return summaries[:max_files], len(all_files)


def render_map_markdown(summaries: list[FileSummary], total_scanned: int, task_query: str) -> str:
    lines = [
        "# Repository Logical Symbol Map",
        f"> Scanned {total_scanned} source files | Showing top {len(summaries)} symbol-bearing modules",
    ]
    if task_query:
        lines.append(f"> Task focus filter: `{task_query}`")
    lines.append("")
    for item in summaries:
        hot_tag = f" | git-touches:{item.hotness}" if item.hotness else ""
        lines.append(f"## `{item.rel_path}` ({item.line_count}L{hot_tag})")
        for sym in item.symbols:
            lines.append(f"- `{sym}`")
        if item.imports:
            lines.append(f"- _deps:_ `{', '.join(item.imports)}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _detect_license(repo: Path) -> str:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        p = repo / name
        if p.is_file():
            head = p.read_text(encoding="utf-8", errors="replace")[:800].lower()
            for marker in ("apache license", "mit license", "gpl", "bsd", "isc", "mpl"):
                if marker in head:
                    return f"{name} ({marker.title()})"
            return name
    return "None detected"


def digest_single_reference_repo(repo: Path, out_dir: Path, max_api_files: int = 18) -> Path:
    """Create `_reference/digests/<repo>.md` with license, entrypoints, engines, and public API."""
    ext_counts: Counter[str] = Counter()
    entrypoints: list[str] = []
    backed_skills: list[tuple[str, int]] = []
    prompt_only_count = 0

    for skill_md in sorted(repo.rglob("SKILL.md")):
        if any(pt in DEFAULT_IGNORES for pt in skill_md.parts):
            continue
        scripts_dir = skill_md.parent / "scripts"
        execs = [f for f in scripts_dir.rglob("*") if f.is_file() and f.suffix in ENGINE_EXTS] if scripts_dir.is_dir() else []
        if execs:
            backed_skills.append((skill_md.parent.relative_to(repo).as_posix(), len(execs)))
        else:
            prompt_only_count += 1

    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in DEFAULT_IGNORES and not d.startswith(".git"))
        rel_dir = Path(dirpath).relative_to(repo)
        if any(p.lower() in {"test", "tests", "fixtures"} for p in rel_dir.parts):
            continue
        for fname in sorted(filenames):
            p = Path(dirpath) / fname
            if p.suffix:
                ext_counts[p.suffix.lower()] += 1
            if fname in {"pyproject.toml", "package.json", "go.mod", "Makefile", "main.py", "cli.py", "index.ts", "index.js"}:
                if len(rel_dir.parts) <= 3:
                    entrypoints.append(p.relative_to(repo).as_posix())

    api_summaries, total_src = build_repo_map(repo, DEFAULT_IGNORES | {"fixtures"}, "", max_api_files, skip_tests=True)
    exts = ", ".join(f"`{k}` ({v})" for k, v in ext_counts.most_common(6))

    lines = [
        f"# Reference Digest: `{repo.name}`",
        f"- **License:** {_detect_license(repo)}",
        f"- **Code Footprint:** {exts or 'none'} ({total_src} source files)",
        f"- **Bundled Skills Audit:** {len(backed_skills)} script-backed, {prompt_only_count} prompt-only ignored",
        "",
        "## Entrypoints & Manifests",
    ]
    for ep in entrypoints[:15]:
        lines.append(f"- `{ep}`")
    if not entrypoints:
        lines.append("- _None detected_")

    if backed_skills:
        lines.extend(["", "## Script-Backed Skills"])
        for s_rel, cnt in backed_skills[:15]:
            lines.append(f"- `[EXECUTABLE]` `{s_rel}` ({cnt} script(s))")

    lines.extend(["", f"## Public API & Key Symbols (Top {len(api_summaries)})"])
    for item in api_summaries:
        lines.append(f"- **`{item.rel_path}`** ({item.line_count}L): {', '.join(f'`{s}`' for s in item.symbols[:5])}")

    out_dir.mkdir(parents=True, exist_ok=True)
    digest_path = out_dir / f"{repo.name}.md"
    digest_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return digest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate logical REPO_MAP.md or digest _reference/repos/.")
    parser.add_argument("--root", default=".", help="Repository root directory")
    parser.add_argument("--output", default=".agents/REPO_MAP.md", help="Output markdown path (or '-' for stdout)")
    parser.add_argument("--task", default="", help="Optional task keywords to rank relevant files first")
    parser.add_argument("--max-files", type=int, default=45, help="Maximum files included in map")
    parser.add_argument("--include-reference", action="store_true", help="Include _reference/ in normal map")
    parser.add_argument("--digest-reference", help="Digest cloned reference repo(s) into _reference/digests/<repo>.md")
    parser.add_argument("--digests-dir", default="_reference/digests", help="Directory for generated reference digests")
    parser.add_argument("--ignore", action="append", default=[], help="Extra directory names to ignore")
    args = parser.parse_args()

    if args.digest_reference:
        ref_path = Path(args.digest_reference).resolve()
        if not ref_path.is_dir():
            print(f"Reference path not found: {ref_path}", file=sys.stderr)
            return 1
        repos = (
            [ref_path]
            if (ref_path / ".git").exists() or (ref_path / "README.md").exists()
            else sorted(p for p in ref_path.iterdir() if p.is_dir() and not p.name.startswith("."))
        )
        out_dir = Path(args.digests_dir)
        written = [digest_single_reference_repo(r, out_dir) for r in repos]
        for w in written:
            print(f"Digested -> {w}")
        return 0

    root = Path(args.root).resolve()
    ignores = set(DEFAULT_IGNORES) | set(args.ignore)
    if args.include_reference:
        ignores.discard("_reference")

    summaries, total = build_repo_map(root, ignores, args.task, args.max_files)
    rendered = render_map_markdown(summaries, total, args.task)

    if args.output == "-":
        print(rendered)
        return 0

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"Generated {out_path} ({len(rendered.splitlines())} lines, {len(summaries)}/{total} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
