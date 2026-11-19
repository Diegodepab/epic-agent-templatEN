#!/usr/bin/env python3
"""Static analyzer for Godot 4 C# (.NET 8+) scripts.

Enforces:
- `partial` modifier on subclasses of Godot Node/Resource types (source generator requirement)
- Balanced event subscriptions (`+=` in _Ready/_EnterTree matched by `-=` in _ExitTree)
- Zero fragile hardcoded node paths (`GetNode("/root/...")` or `GetNode("../../../...")`)
- Pure C# domain isolation (files under `Domain/` or `Core/` must not `using Godot;`)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

GODOT_BASE_RE = re.compile(
    r"\b(?:public|internal)\s+(?!partial\b)(?:sealed\s+|abstract\s+)?class\s+([A-Za-z0-9_]+)\s*:\s*"
    r"(?:Godot\.)?(?:Node|Node2D|Node3D|CharacterBody2D|RigidBody2D|Area2D|StaticBody2D|"
    r"Control|CanvasLayer|Camera2D|Resource|Sprite2D|AnimatedSprite2D|Timer)\b"
)
FRAGILE_GETNODE_RE = re.compile(r"""GetNode(?:<[^>]+>)?\(\s*["'](?:/root/|\.\./\.\./)""")
EVENT_SUBSCRIBE_RE = re.compile(r"([A-Za-z0-9_.]+)\s*\+=\s*([A-Za-z0-9_]+)\s*;")
EVENT_UNSUBSCRIBE_RE = re.compile(r"([A-Za-z0-9_.]+)\s*-=\s*([A-Za-z0-9_]+)\s*;")


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int | None
    detail: str


def check_cs_file(path: Path, root: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    findings: list[Finding] = []
    parts_low = {p.lower() for p in path.parts}

    if ("domain" in parts_low or "core" in parts_low) and re.search(r"^\s*using\s+Godot\s*;", text, re.MULTILINE):
        findings.append(
            Finding("HIGH", "domain-godot-coupling", rel, None, "Pure C# Domain/Core script imports `using Godot;`")
        )

    for lineno, line in enumerate(text.splitlines(), start=1):
        m_class = GODOT_BASE_RE.search(line)
        if m_class:
            findings.append(
                Finding(
                    "CRITICAL",
                    "missing-partial-class",
                    rel,
                    lineno,
                    f"Godot script class `{m_class.group(1)}` must be declared `partial`",
                )
            )
        if FRAGILE_GETNODE_RE.search(line):
            findings.append(
                Finding(
                    "HIGH",
                    "fragile-node-path",
                    rel,
                    lineno,
                    "Avoid hardcoded `/root/` or `../../` paths in `GetNode()`; use `[Export]` or signals",
                )
            )

    subs = {(ev, handler) for ev, handler in EVENT_SUBSCRIBE_RE.findall(text)}
    unsubs = {(ev, handler) for ev, handler in EVENT_UNSUBSCRIBE_RE.findall(text)}
    if subs and "_Ready" in text:
        for ev, handler in sorted(subs - unsubs):
            findings.append(
                Finding(
                    "MEDIUM",
                    "unbalanced-event-subscription",
                    rel,
                    None,
                    f"Event subscription `{ev} += {handler}` lacks matching `-=` cleanup in `_ExitTree()`",
                )
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Godot 4 C# architecture and signal hygiene.")
    parser.add_argument("--root", default=".", help="Godot project root")
    parser.add_argument("--json-out", help="Optional normalized JSON report path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"Project directory not found: {root}", file=sys.stderr)
        return 1

    cs_files = [
        p
        for p in sorted(root.rglob("*.cs"))
        if ".godot" not in p.parts and "obj" not in p.parts and "bin" not in p.parts and "Tests" not in p.parts
    ]

    findings: list[Finding] = []
    for p in cs_files:
        findings.extend(check_cs_file(p, root))

    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]
    print(f"[godot-csharp-audit] cs_files={len(cs_files)} findings={len(findings)} blocking={len(blocking)}")
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        print(f"  {f.severity:8s} [{f.rule}] {loc}: {f.detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "godot-architecture-and-static-audit",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "summary": {"cs_files": len(cs_files), "findings": len(findings), "blocking": len(blocking)},
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
