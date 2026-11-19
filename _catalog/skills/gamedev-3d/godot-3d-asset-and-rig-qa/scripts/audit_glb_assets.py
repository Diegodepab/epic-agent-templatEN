#!/usr/bin/env python3
"""Binary glTF/GLB 3D asset auditor for Godot 4 (mesh counts, materials, textures, animations)."""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    detail: str


def read_glb_json(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("Invalid GLB magic header")
    chunk_len, chunk_type = struct.unpack("<II", data[12:20])
    if chunk_type != 0x4E4F534A:  # JSON
        raise ValueError("Missing GLB JSON chunk")
    return json.loads(data[20 : 20 + chunk_len].decode("utf-8"))


def audit_gltf_doc(doc: dict[str, object], rel: str, max_primitives: int, max_textures: int) -> tuple[list[Finding], dict[str, int]]:
    findings: list[Finding] = []
    meshes = doc.get("meshes", []) or []
    materials = doc.get("materials", []) or []
    textures = doc.get("images", []) or []
    animations = doc.get("animations", []) or []

    prim_count = sum(len(m.get("primitives", [])) for m in meshes if isinstance(m, dict))
    stats = {
        "meshes": len(meshes),
        "primitives": prim_count,
        "materials": len(materials),
        "images": len(textures),
        "animations": len(animations),
    }

    if not meshes:
        findings.append(Finding("HIGH", "empty-meshes", rel, "GLB/glTF contains zero meshes"))
    if prim_count > max_primitives:
        findings.append(
            Finding("HIGH", "excess-draw-calls", rel, f"Asset has {prim_count} primitives (limit {max_primitives}); merge meshes or bake LODs")
        )
    if len(textures) > max_textures:
        findings.append(
            Finding("MEDIUM", "excess-textures", rel, f"Asset embeds {len(textures)} textures (limit {max_textures}); pack ORM channels")
        )
    return findings, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect GLB/glTF 3D assets for Godot draw-call, material, and animation hygiene.")
    parser.add_argument("--root", default=".", help="Project root or assets folder")
    parser.add_argument("--max-primitives", type=int, default=24, help="Max primitive draw calls per asset")
    parser.add_argument("--max-textures", type=int, default=12, help="Max embedded image textures per asset")
    parser.add_argument("--json-out", help="Optional JSON report path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    assets = [p for p in sorted(root.rglob("*")) if p.is_file() and p.suffix.lower() in {".glb", ".gltf"} and ".godot" not in p.parts]
    findings: list[Finding] = []

    for asset in assets:
        rel = asset.relative_to(root).as_posix()
        try:
            doc = read_glb_json(asset) if asset.suffix.lower() == ".glb" else json.loads(asset.read_text(encoding="utf-8"))
            f_list, stats = audit_gltf_doc(doc, rel, args.max_primitives, args.max_textures)
            findings.extend(f_list)
            print(f"[3d-qa] {rel}: {stats}")
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            findings.append(Finding("CRITICAL", "corrupt-gltf", rel, str(exc)))

    blender_status = "installed" if shutil.which("blender") else "not-installed"
    blocking = [f for f in findings if f.severity in {"CRITICAL", "HIGH"}]
    print(f"[godot-3d-qa] assets={len(assets)} findings={len(findings)} blocking={len(blocking)} blender={blender_status}")
    for f in findings:
        print(f"  {f.severity:8s} [{f.rule}] {f.file}: {f.detail}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "tool": "godot-3d-asset-and-rig-qa",
                    "status": "FAIL" if blocking else ("WARN" if findings else "PASS"),
                    "summary": {"assets": len(assets), "findings": len(findings), "blender": blender_status},
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
