#!/usr/bin/env python3
"""Scaffold a compliant, Gemini-optimized script-backed Antigravity skill."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

PY_SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
"""Deterministic execution engine for {name}."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def run(target: Path) -> dict[str, object]:
    """Execute the deterministic check/tool wrapper and return normalized report."""
    findings: list[dict[str, object]] = []
    return {{
        "tool": "{name}",
        "status": "FAIL" if findings else "PASS",
        "score": 100 if not findings else 0,
        "summary": {{"target": str(target), "findings": len(findings)}},
        "findings": findings,
    }}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run {name}.")
    parser.add_argument("--target", default=".", help="Target file or directory")
    parser.add_argument("--json-out", help="Optional JSON report path")
    args = parser.parse_args()

    report = run(Path(args.target))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")

    print(f"[{name}] status={{report['status']}} findings={{report['summary']['findings']}}")
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

SKILL_MD_TEMPLATE = """---
name: {name}
description: {description}
---

# {title}

## Decision Tree

- **Audit / Check:** Run `scripts/run.py --target <path>` and inspect normalized JSON findings.
- **Inspect Flags First:** Treat `scripts/run.py` as a black box; run `--help` before reading source code.

## What Lives Where

| Artifact | Purpose | Output |
|---|---|---|
| `scripts/run.py` | Deterministic CLI engine / tool wrapper | Normalized JSON report + exit `0`/`1` |

## Commands

```bash
python3 .agents/skills/{name}/scripts/run.py --help
python3 .agents/skills/{name}/scripts/run.py --target src/ --json-out .agents/report.json
```
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a Gemini-compliant script-backed skill.")
    parser.add_argument("--name", required=True, help="Skill name in kebab-case")
    parser.add_argument("--dest", required=True, help="Parent category directory, e.g. _catalog/skills/backend")
    parser.add_argument("--description", required=True, help="Third-person YAML description with `Use when ... Not for ...`")
    args = parser.parse_args()

    if not KEBAB_RE.match(args.name):
        print(f"Skill name `{args.name}` must be kebab-case.", file=sys.stderr)
        return 1

    skill_dir = Path(args.dest) / args.name
    if skill_dir.exists():
        print(f"Skill directory already exists: {skill_dir}", file=sys.stderr)
        return 1

    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    title = " ".join(part.capitalize() for part in args.name.split("-"))
    (skill_dir / "SKILL.md").write_text(
        SKILL_MD_TEMPLATE.format(name=args.name, description=args.description, title=title),
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "run.py").write_text(PY_SCRIPT_TEMPLATE.format(name=args.name), encoding="utf-8")
    print(f"Scaffolded compliant skill at {skill_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
