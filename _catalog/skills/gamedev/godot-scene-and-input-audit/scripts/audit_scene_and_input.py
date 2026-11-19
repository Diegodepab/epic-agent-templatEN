#!/usr/bin/env python3
"""Audits Godot 4 2D physics collision masks, C# frame-independent loops, UI focus, saves, and shaders."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

NODE_HEADER_RE = re.compile(r'^\[node\s+name="([^"]+)"\s+type="([^"]+)"')
PHYSICS_TYPES = {"CharacterBody2D", "Area2D", "RigidBody2D", "StaticBody2D", "AnimatableBody2D"}
INTERACTIVE_UI_TYPES = {"Button", "TextureButton", "HSlider", "VSlider", "CheckBox", "CheckButton", "LineEdit", "OptionButton"}

FRAME_DEPENDENT_LERP_RE = re.compile(r"(?:Mathf\.)?Lerp\([^;]+,\s*0\.\d+f?\s*\)")
PER_FRAME_GC_ALLOC_RE = re.compile(r"\bnew\s+(?:List|Dictionary|HashSet|Queue|Stack)\s*<")
PER_FRAME_LINQ_RE = re.compile(r"\.(?:Where|Select|ToList|ToArray|OrderBy|GroupBy)\s*\(")
PER_FRAME_GETNODE_RE = re.compile(r"\bGetNode(?:OrNull)?\s*(?:<[^>]+>)?\s*\(")
ATOMIC_SAVE_MARKERS = (".tmp", "Replace", "RenameAbsolute", "Rename")
VERSION_SAVE_MARKERS = ("SchemaVersion", "SaveVersion", "schema_version", "version")


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    line: int | None
    detail: str


def parse_physics_layers(root: Path) -> dict[int, str]:
    layers: dict[int, str] = {}
    pg = root / "project.godot"
    if not pg.is_file():
        return layers
    in_layers = False
    for line in pg.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.strip()
        if clean.startswith("["):
            in_layers = clean == "[layer_names]"
            continue
        if in_layers and clean.startswith("2d_physics/layer_"):
            k, _, v = clean.partition("=")
            idx = int(k.split("_")[-1])
            layers[idx] = v.strip().strip('"')
    return layers


def _bitmask_names(mask: int, layer_names: dict[int, str]) -> list[str]:
    names: list[str] = []
    for bit in range(1, 33):
        if mask & (1 << (bit - 1)):
            names.append(layer_names.get(bit, f"L{bit}"))
    return names


def audit_tscn(path: Path, root: Path, layer_names: dict[int, str]) -> tuple[list[Finding], list[str]]:
    rel = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    matrix_rows: list[str] = []

    current_name = ""
    current_type = ""
    node_line = 1
    props: dict[str, str] = {}

    def flush_node() -> None:
        if not current_type:
            return
        if current_type in PHYSICS_TYPES:
            layer_val = int(props.get("collision_layer", "1"))
            mask_val = int(props.get("collision_mask", "1"))
            l_str = ",".join(_bitmask_names(layer_val, layer_names)) or "none"
            m_str = ",".join(_bitmask_names(mask_val, layer_names)) or "none"
            matrix_rows.append(f"{rel}::{current_name} ({current_type}) layer=[{l_str}] mask=[{m_str}]")
            if layer_names and layer_val == 1 and mask_val == 1 and "collision_layer" not in props:
                findings.append(
                    Finding(
                        "MEDIUM",
                        "default-collision-layer",
                        rel,
                        node_line,
                        f"`{current_name}` ({current_type}) still uses implicit default layer=1/mask=1 despite named layers",
                    )
                )
        if current_type in INTERACTIVE_UI_TYPES and props.get("focus_mode") == "0":
            findings.append(
                Finding(
                    "HIGH",
                    "ui-gamepad-focus-disabled",
                    rel,
                    node_line,
                    f"Interactive control `{current_name}` sets `focus_mode = 0` (unreachable via keyboard/gamepad)",
                )
            )

    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("[node "):
            flush_node()
            props = {}
            m = NODE_HEADER_RE.match(stripped)
            current_name = m.group(1) if m else ""
            current_type = m.group(2) if m else ""
            node_line = lineno
        elif stripped.startswith("["):
            flush_node()
            current_type = ""
            props = {}
        elif current_type and "=" in stripped:
            k, _, v = stripped.partition("=")
            props[k.strip()] = v.strip()

    flush_node()
    return findings, matrix_rows


def audit_cs_gameplay_and_saves(path: Path, root: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    findings: list[Finding] = []

    in_process = False
    in_frame_loop = False
    for lineno, line in enumerate(lines, start=1):
        code_line = line.split("//", 1)[0]
        if re.search(r"\boverride\s+void\s+_Process\s*\(", code_line):
            in_process = True
            in_frame_loop = True
        elif re.search(r"\boverride\s+void\s+_PhysicsProcess\s*\(", code_line):
            in_process = False
            in_frame_loop = True
        elif re.search(r"\boverride\s+void\s+_(Ready|Input|UnhandledInput|ExitTree|EnterTree)\s*\(", code_line):
            in_process = False
            in_frame_loop = False

        if in_process and "MoveAndSlide(" in code_line:
            findings.append(
                Finding(
                    "CRITICAL",
                    "physics-in-process",
                    rel,
                    lineno,
                    "`MoveAndSlide()` called inside `_Process()`; move physics simulation to `_PhysicsProcess(double delta)`",
                )
            )

        if in_frame_loop:
            if PER_FRAME_GC_ALLOC_RE.search(code_line):
                findings.append(
                    Finding(
                        "HIGH",
                        "per-frame-gc-alloc",
                        rel,
                        lineno,
                        "Heap collection allocated inside `_Process`/`_PhysicsProcess`; cache and `.Clear()` collection fields instead",
                    )
                )
            if PER_FRAME_LINQ_RE.search(code_line):
                findings.append(
                    Finding(
                        "HIGH",
                        "per-frame-linq-alloc",
                        rel,
                        lineno,
                        "LINQ query executed per frame inside `_Process`/`_PhysicsProcess` (causes GC pressure); use a `for`/`foreach` loop",
                    )
                )
            if PER_FRAME_GETNODE_RE.search(code_line):
                findings.append(
                    Finding(
                        "HIGH",
                        "per-frame-getnode",
                        rel,
                        lineno,
                        "`GetNode()` called per frame inside `_Process`/`_PhysicsProcess`; cache node reference in `_Ready()`",
                    )
                )

        if FRAME_DEPENDENT_LERP_RE.search(line):
            findings.append(
                Finding(
                    "HIGH",
                    "framerate-dependent-lerp",
                    rel,
                    lineno,
                    "Constant factor in `Lerp()` depends on FPS; use `1.0f - Mathf.Exp(-decay * (float)delta)`",
                )
            )

    writes_user_save = "user://" in text and any(w in text for w in ("FileAccess.Open", "WriteAllText", "ModeFlags.Write", "ResourceSaver.Save"))
    if writes_user_save:
        if not any(m in text for m in ATOMIC_SAVE_MARKERS):
            findings.append(
                Finding(
                    "HIGH",
                    "non-atomic-save",
                    rel,
                    None,
                    "Save writer writes directly to `user://` without atomic `.tmp` + rename pattern (corruption risk on crash)",
                )
            )
        if not any(v in text for v in VERSION_SAVE_MARKERS):
            findings.append(
                Finding(
                    "MEDIUM",
                    "unversioned-save-schema",
                    rel,
                    None,
                    "Save payload lacks explicit `SchemaVersion` / `SaveVersion` field for forward migrations",
                )
            )
    return findings


def audit_gdshader(path: Path, root: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "SCREEN_TEXTURE" in line and "hint_screen_texture" not in text:
            findings.append(
                Finding(
                    "HIGH",
                    "godot3-screen-texture",
                    rel,
                    lineno,
                    "`SCREEN_TEXTURE` is deprecated in Godot 4; declare `uniform sampler2D screen_texture : hint_screen_texture;`",
                )
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Godot 4 physics masks, C# loops, UI focus, saves, and shaders.")
    parser.add_argument("--root", default=".", help="Godot project root")
    parser.add_argument("--json-out", help="Optional normalized JSON output path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"Root not found: {root}", file=sys.stderr)
        return 1

    layer_names = parse_physics_layers(root)
    findings: list[Finding] = []
    matrix: list[str] = []

    for tscn in sorted(root.rglob("*.tscn")):
        if ".godot" in tscn.parts:
            continue
        f_list, rows = audit_tscn(tscn, root, layer_names)
        findings.extend(f_list)
        matrix.extend(rows)

    for cs in sorted(root.rglob("*.cs")):
        if ".godot" in cs.parts or "obj" in cs.parts or "bin" in cs.parts:
            continue
        findings.extend(audit_cs_gameplay_and_saves(cs, root))

    for shader in sorted(root.rglob("*.gdshader")):
        if ".godot" in shader.parts:
            continue
        findings.extend(audit_gdshader(shader, root))

    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]
    print(f"[godot-scene-input] physics_nodes={len(matrix)} findings={len(findings)} blocking={len(blocking)}")
    if matrix:
        print("  Collision Matrix:")
        for row in matrix[:12]:
            print(f"    {row}")
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        print(f"  {f.severity:8s} [{f.rule}] {loc}: {f.detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "godot-scene-and-input-audit",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "summary": {"physics_nodes": len(matrix), "findings": len(findings), "blocking": len(blocking)},
                    "findings": [asdict(f) for f in findings],
                    "collision_matrix": matrix,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
