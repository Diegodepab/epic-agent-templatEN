#!/usr/bin/env python3
"""Reproducible functional evaluation harness for Antigravity/Gemini skills.

Executes real trigger checks, valid inputs, invalid defect detection, malformed
error handling, read-only invariants, missing-dependency honesty, and clean
false-positive guards inside isolated temporary workspaces (never mutating repo files).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class CaseResult:
    skill: str
    case_id: str
    kind: str
    status: str  # PASS | FAIL | SKIP
    duration_ms: int
    detail: str
    returncode: int | None = None


def parse_frontmatter_desc(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return ""
    for line in m.group(1).splitlines():
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip()
    return ""


def snapshot_tree_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            hashes[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def materialize_synthetic_assets(work: Path, generators: list[str]) -> None:
    if not generators:
        return
    if "green_strip" in generators or "plate_png" in generators:
        from PIL import Image, ImageDraw

        if "green_strip" in generators:
            im = Image.new("RGBA", (64, 32), (0, 220, 0, 255))
            d = ImageDraw.Draw(im)
            d.rectangle([8, 6, 23, 29], fill=(200, 60, 40, 255))
            d.rectangle([40, 4, 55, 29], fill=(200, 60, 40, 255))
            (work / "assets").mkdir(parents=True, exist_ok=True)
            im.save(work / "assets/green_strip.png")
        if "plate_png" in generators:
            plate = Image.new("RGBA", (32, 32), (40, 80, 120, 255))
            plate.save(work / "plate.png")
    if "glb_valid" in generators or "glb_heavy" in generators:
        def write_glb(path: Path, n_prims: int) -> None:
            prims = [{"attributes": {"POSITION": 0}} for _ in range(n_prims)]
            doc = {"asset": {"version": "2.0"}, "meshes": [{"primitives": prims}], "materials": [{}], "images": [{}]}
            raw = json.dumps(doc).encode("utf-8")
            while len(raw) % 4 != 0:
                raw += b" "
            hdr = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(raw))
            chk = struct.pack("<II", len(raw), 0x4E4F534A)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(hdr + chk + raw)

        if "glb_valid" in generators:
            write_glb(work / "valid.glb", 1)
        if "glb_heavy" in generators:
            write_glb(work / "heavy.glb", 250)
    if "slime_copy" in generators:
        src = TEMPLATE_ROOT / "_catalog/skills/gamedev/godot-2d-pixel-art-forge/examples/slime.pixelspec.json"
        shutil.copy2(src, work / "slime.pixelspec.json")


def materialize_files(work: Path, files: dict[str, object]) -> None:
    for rel, content in files.items():
        dst = work / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = content if isinstance(content, str) else json.dumps(content, indent=2) + "\n"
        dst.write_text(text, encoding="utf-8")


def eval_triggers(skill_name: str, skill_dir: Path, spec: dict[str, object]) -> CaseResult:
    t0 = time.monotonic()
    desc = parse_frontmatter_desc(skill_dir / "SKILL.md").lower()
    positive_scope, _, _not_for_scope = desc.partition("not for")
    pos = [str(k).lower() for k in spec.get("positive_keywords", [])]
    neg = [str(k).lower() for k in spec.get("negative_keywords", [])]
    missing_pos = [k for k in pos if k not in positive_scope]
    leaked_neg = [k for k in neg if k in positive_scope]
    ms = round((time.monotonic() - t0) * 1000)
    if missing_pos or leaked_neg:
        detail = f"missing_pos={missing_pos} leaked_neg={leaked_neg}"
        return CaseResult(skill_name, "triggers", "triggers", "FAIL", ms, detail)
    return CaseResult(skill_name, "triggers", "triggers", "PASS", ms, f"matched {len(pos)} positive keyword(s)")


def run_command_case(skill_name: str, skill_dir: Path, case: dict[str, object]) -> CaseResult:
    case_id = str(case["id"])
    kind = str(case["kind"])
    t0 = time.monotonic()

    req_bin = case.get("requires_bin")
    if isinstance(req_bin, str) and not shutil.which(req_bin):
        return CaseResult(skill_name, case_id, kind, "SKIP", 0, f"Required binary `{req_bin}` not in PATH")

    req_mod = case.get("requires_python_mod")
    if isinstance(req_mod, str):
        probe = subprocess.run([sys.executable, "-c", f"import {req_mod}"], capture_output=True, check=False)
        if probe.returncode != 0:
            return CaseResult(skill_name, case_id, kind, "SKIP", 0, f"Required Python module `{req_mod}` not installed")

    with tempfile.TemporaryDirectory(prefix="agy-eval-") as tmp:
        work = Path(tmp)
        materialize_synthetic_assets(work, list(case.get("generators", [])))  # type: ignore[arg-type]
        files = case.get("files", {})
        if isinstance(files, dict):
            materialize_files(work, files)

        pre_hashes = snapshot_tree_hashes(work) if case.get("check_read_only") else {}

        raw_cmd = [str(tok).replace("{SKILL}", str(skill_dir)).replace("{ROOT}", str(TEMPLATE_ROOT)).replace("{WORK}", str(work)) for tok in case["cmd"]]  # type: ignore[index]
        if raw_cmd[0] == "python3":
            raw_cmd[0] = sys.executable

        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env_overrides = case.get("env", {})
        if isinstance(env_overrides, dict):
            for k, v in env_overrides.items():
                env[str(k)] = str(v)

        proc = subprocess.run(raw_cmd, cwd=work, env=env, capture_output=True, text=True, check=False, timeout=45)
        combined = proc.stdout + "\n" + proc.stderr
        ms = round((time.monotonic() - t0) * 1000)

        errors: list[str] = []
        if "expect_rc" in case:
            if proc.returncode != int(case["expect_rc"]):  # type: ignore[arg-type]
                errors.append(f"expected rc={case['expect_rc']}, got {proc.returncode}")
        elif case.get("expect_nonzero") and proc.returncode == 0:
            errors.append("expected non-zero exit code, got 0")

        for sub in case.get("expect_in", []):  # type: ignore[attr-defined]
            if str(sub) not in combined:
                errors.append(f"missing expected text `{sub}`")
        for sub in case.get("forbid_in", []):  # type: ignore[attr-defined]
            if str(sub) in combined:
                errors.append(f"forbidden text `{sub}` found in output")
        if case.get("forbid_traceback", True) and "Traceback (most recent call last):" in combined:
            errors.append("unhandled Python Traceback emitted")
        for rel_out in case.get("expect_files", []):  # type: ignore[attr-defined]
            if not (work / str(rel_out)).exists():
                errors.append(f"expected output artifact missing: `{rel_out}`")
        file_checks = case.get("expect_file_contains", {})
        if isinstance(file_checks, dict):
            for rel_out, needles in file_checks.items():
                out_path = work / str(rel_out)
                if not out_path.exists():
                    errors.append(f"expected output artifact missing for text check: `{rel_out}`")
                    continue
                body = out_path.read_text(encoding="utf-8", errors="replace")
                for needle in needles:
                    if str(needle) not in body:
                        errors.append(f"missing `{needle}` in `{rel_out}`")

        if case.get("check_read_only"):
            post_hashes = snapshot_tree_hashes(work)
            mutated = [k for k, v in pre_hashes.items() if post_hashes.get(k) != v]
            extra = sorted(set(post_hashes) - set(pre_hashes) - set(case.get("allow_created", [])))  # type: ignore[arg-type]
            if mutated or extra:
                errors.append(f"unexpected workspace mutation: mutated={mutated} extra={extra}")

        status = "FAIL" if errors else "PASS"
        detail = "; ".join(errors) if errors else f"ok ({ms}ms)"
        if errors:
            detail += f" | tail={combined.strip()[-160:]!r}"
        return CaseResult(skill_name, case_id, kind, status, ms, detail, proc.returncode)


def discover_skills(catalog_dir: Path) -> dict[str, Path]:
    return {p.parent.name: p.parent.resolve() for p in sorted(catalog_dir.rglob("SKILL.md"))}


def load_suites(suites_dir: Path) -> dict[str, dict[str, object]]:
    loaded: dict[str, dict[str, object]] = {}
    for jf in sorted(suites_dir.glob("*.json")):
        raw = json.loads(jf.read_text(encoding="utf-8"))
        for skill_name, spec in raw.items():
            if skill_name in loaded:
                raise SystemExit(f"Duplicate eval suite definition for `{skill_name}` in {jf}")
            loaded[skill_name] = spec
    return loaded


def format_markdown(results: list[CaseResult], missing_suites: list[str], elapsed_ms: int) -> str:
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    lines = [
        "# Skill Functional Evaluation Summary",
        f"> Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} | Duration: {elapsed_ms} ms | PASS={counts['PASS']} | FAIL={counts['FAIL']} | SKIP={counts['SKIP']}",
        "",
    ]
    if missing_suites:
        lines.append(f"**Missing eval suites (`{len(missing_suites)}`):** {', '.join(missing_suites)}")
        lines.append("")
    lines.extend(["| Skill | Case | Kind | Status | Time (ms) | Evidence / Detail |", "| :--- | :--- | :--- | :---: | ---: | :--- |"])
    order = {"FAIL": 0, "SKIP": 1, "PASS": 2}
    for r in sorted(results, key=lambda x: (order.get(x.status, 9), x.skill, x.case_id)):
        lines.append(f"| `{r.skill}` | `{r.case_id}` | `{r.kind}` | **{r.status}** | {r.duration_ms} | {r.detail.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute isolated functional evaluations across catalog skills.")
    parser.add_argument("--catalog", default=str(TEMPLATE_ROOT / "_catalog/skills"), help="Catalog skills directory")
    parser.add_argument("--suites", default=str(TEMPLATE_ROOT / "evals/suites"), help="Eval JSON suites directory")
    parser.add_argument("--skill", action="append", default=[], help="Filter to specific skill name(s)")
    parser.add_argument("--json-out", help="Write reproducible JSON eval report ('-' for stdout)")
    parser.add_argument("--md-out", help="Write Markdown eval summary report")
    parser.add_argument("--fail-on-skip", action="store_true", help="Exit 1 if any case returns SKIP")
    args = parser.parse_args()

    t_start = time.monotonic()
    skills_map = discover_skills(Path(args.catalog))
    suites = load_suites(Path(args.suites))
    selected = sorted(args.skill) if args.skill else sorted(skills_map.keys())

    missing_suites = [s for s in selected if s not in suites]
    results: list[CaseResult] = []
    for s in selected:
        if s not in skills_map:
            results.append(CaseResult(s, "lookup", "meta", "FAIL", 0, f"Skill not found under {args.catalog}"))
            continue
        if s not in suites:
            results.append(CaseResult(s, "suite", "meta", "FAIL", 0, f"No eval suite defined under {args.suites}"))
            continue
        spec = suites[s]
        sdir = skills_map[s]
        if "triggers" in spec:
            results.append(eval_triggers(s, sdir, spec["triggers"]))  # type: ignore[arg-type]
        for case in spec.get("cases", []):  # type: ignore[attr-defined]
            results.append(run_command_case(s, sdir, case))

    elapsed_ms = round((time.monotonic() - t_start) * 1000)
    fails = [r for r in results if r.status == "FAIL"]
    skips = [r for r in results if r.status == "SKIP"]
    passes = [r for r in results if r.status == "PASS"]

    print(f"[skill-evals] skills={len(selected)} cases={len(results)} PASS={len(passes)} FAIL={len(fails)} SKIP={len(skips)} ({elapsed_ms}ms)")
    for r in fails:
        print(f"  FAIL [{r.skill}/{r.case_id}] {r.detail}", file=sys.stderr)
    for r in skips:
        print(f"  SKIP [{r.skill}/{r.case_id}] {r.detail}")

    if args.json_out:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summary": {"skills": len(selected), "cases": len(results), "pass": len(passes), "fail": len(fails), "skip": len(skips)},
            "missing_suites": missing_suites,
            "results": [asdict(r) for r in results],
        }
        rendered = json.dumps(payload, indent=2) + "\n"
        if args.json_out == "-":
            print(rendered)
        else:
            out = Path(args.json_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(rendered, encoding="utf-8")

    if args.md_out:
        md_path = Path(args.md_out)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(format_markdown(results, missing_suites, elapsed_ms), encoding="utf-8")

    if fails or missing_suites or (args.fail_on_skip and skips):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
