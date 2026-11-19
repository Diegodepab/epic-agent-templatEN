#!/usr/bin/env python3
"""Legacy file-size budget ratchet for brownfield repositories.

Prevents oversized legacy modules (> max_lines, default 350) from growing further while
allowing incremental Strangler-Fig splits. Stores frozen per-file line caps in
`.agents/size-ratchet.json` and tightens caps whenever a legacy file shrinks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".cs", ".go", ".rs", ".java", ".kt", ".rb", ".svelte"}
SKIP_DIRS = {
    ".git", ".agents", ".gemini", ".claude", ".venv", "venv", "node_modules",
    "__pycache__", ".pytest_cache", "dist", "build", "_catalog", "_reference", "migrations",
}


def scan_line_counts(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in CODE_EXTS:
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        try:
            lines = len(p.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            continue
        counts[p.relative_to(root).as_posix()] = lines
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enforce a non-increasing line-count ratchet on legacy files (>350L) during incremental refactoring."
    )
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root (default: .)")
    parser.add_argument("--ratchet-file", type=Path, default=Path(".agents/size-ratchet.json"), help="Ratchet baseline JSON path relative to --root")
    parser.add_argument("--max-lines", type=int, default=350, help="Target line cap for new/clean files (default: 350)")
    parser.add_argument("--init", action="store_true", help="Create or tighten the ratchet baseline JSON from current oversized files")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: root not found: {root}", file=sys.stderr)
        return 2

    ratchet_path = args.ratchet_file if args.ratchet_file.is_absolute() else (root / args.ratchet_file)
    counts = scan_line_counts(root)
    existing: dict[str, int] = {}
    if ratchet_path.is_file():
        data = json.loads(ratchet_path.read_text(encoding="utf-8"))
        existing = {str(k): int(v) for k, v in data.get("caps", {}).items()}

    if args.init:
        caps: dict[str, int] = {}
        for rel, n in counts.items():
            if n > args.max_lines:
                # Never loosen an existing cap; only freeze new or tighten shrunk files
                caps[rel] = min(n, existing[rel]) if rel in existing else n
        ratchet_path.parent.mkdir(parents=True, exist_ok=True)
        ratchet_path.write_text(
            json.dumps({"max_lines": args.max_lines, "caps": caps}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        out = {"tool": "clean-code-and-architecture-gate/size_ratchet", "mode": "init", "status": "PASS", "oversized_tracked": len(caps), "ratchet_file": str(ratchet_path)}
        print(json.dumps(out, indent=2) if args.json else f"[size-ratchet] baseline written: {len(caps)} oversized file(s) frozen at {ratchet_path}")
        return 0

    violations: list[dict[str, object]] = []
    improvements: list[dict[str, object]] = []
    for rel, n in counts.items():
        cap = existing.get(rel, args.max_lines)
        if n > cap:
            violations.append({"file": rel, "lines": n, "cap": cap, "delta": n - cap})
        elif rel in existing and n < existing[rel]:
            improvements.append({"file": rel, "lines": n, "old_cap": existing[rel], "saved": existing[rel] - n})

    status = "FAIL" if violations else "PASS"
    payload = {
        "tool": "clean-code-and-architecture-gate/size_ratchet",
        "mode": "check",
        "status": status,
        "max_lines": args.max_lines,
        "files_scanned": len(counts),
        "violations": violations,
        "improvements": improvements,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"[size-ratchet] status={status} files={len(counts)} violations={len(violations)} improvements={len(improvements)}")
        for v in violations:
            print(f"  FAIL  {v['file']}: {v['lines']}L exceeds cap {v['cap']}L (+{v['delta']}L)")
        for imp in improvements:
            print(f"  GOOD  {imp['file']}: shrunk from {imp['old_cap']}L to {imp['lines']}L (-{imp['saved']}L; re-run --init to tighten cap)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
