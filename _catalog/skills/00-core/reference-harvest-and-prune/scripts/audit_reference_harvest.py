#!/usr/bin/env python3
"""Audits cloned reference repositories to classify noise, already-extracted engines,
missing high-value capabilities, and whether each reference folder is safe to delete.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

IGNORE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".godot"}
SCRIPT_EXTS = {".py", ".go", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sh"}

# Signature-based capability detectors: (capability_id, ref_globs, target_evidence_globs, category, notes)
CAPABILITY_PROBES = (
    # Core & GitHub
    (
        "action-sha-pinning",
        ("verify-action-pins",),
        ("verify-action-pins.sh",),
        "EXTRACTED",
        "GitHub Actions 40-hex SHA pin verification ported to git-commit-and-pr-gate",
    ),
    (
        "velocity-trend-scoring",
        ("rerank.py", "freshness.py", "last30days.py"),
        ("skill_radar.py",),
        "EXTRACTED",
        "Recency-weighted velocity scoring adapted into skill-radar-and-proposals",
    ),
    (
        "secret-pattern-scanner",
        ("recon.py",),
        ("security_gate.py", "commit_gate.py"),
        "EXTRACTED",
        "Redacted secret patterns ported into backend-security-and-owasp-gate & git gate",
    ),
    (
        "clean-code-multi-lang-architecture-gate",
        ("map_structure.py", "check_boundaries.py", "check_compression.py"),
        ("map_structure.py", "check_boundaries.py", "check_compression.py"),
        "EXTRACTED",
        "21-language structural mapper, Clean Architecture boundary verifier & lossless compression checker ported to clean-code-and-architecture-gate",
    ),
    (
        "ponytail-minimal-yagni-ladder",
        ("ponytail-activate.js", "ponytail-instructions.js"),
        ("init_project.py",),
        "EXTRACTED",
        "Ponytail 7-rung minimal code philosophy distilled into init_project.py CODE_PHILOSOPHY_RULES['minimal-yagni']",
    ),
    (
        "awesome-skills-debugging-and-supply-chain",
        ("fingerprint.py", "dependency_scanner.py", "check_drizzle_migrations.py"),
        ("fingerprint.py", "find_polluter.py", "dependency_scanner.py", "check_drizzle_migrations.py"),
        "EXTRACTED",
        "Fix-loop fingerprinter, test polluter isolator, supply-chain dependency scanner & Drizzle migration gate ported into catalog skills",
    ),
    # Frontend & Agentic Web
    (
        "multi-viewport-playwright-audit",
        ("design-audit.mjs",),
        ("design-audit.mjs",),
        "EXTRACTED",
        "6-viewport Playwright audit integrated in frontend-lighthouse-and-design-audit",
    ),
    (
        "agentic-lighthouse-config",
        ("agentic-browsing-config.js",),
        ("agentic-browsing-config.js", "agentic-readiness-check.mjs"),
        "EXTRACTED",
        "33-rule agent accessibility & llms.txt/ard.json checks integrated in frontend",
    ),
    (
        "stitch-static-html-postprocess",
        ("extract_inline_html.ts", "post_process.ts"),
        (),
        "OUT_OF_SCOPE",
        "Google Stitch SaaS-only extractor (activate official Stitch plugin separately when needed)",
    ),
    (
        "brand-logo-and-svg-forge",
        ("svg_audit.py", "export_variants.py", "concept_sheet.py"),
        ("svg_audit.py", "export_variants.py", "render_png.py"),
        "EXTRACTED",
        "Dependency-free SVG auditor, Inkscape/Chrome PNG renderer, concept sheet & PWA icon exporter ported to brand-logo-and-svg-forge",
    ),
    (
        "chart-zvec-semantic-retriever",
        ("retriever.ts", "synonyms.ts"),
        ("chart_advisor.py",),
        "EXTRACTED",
        "21-type chart semantic search & G6 v5 constraints ported into frontend-dataviz-and-charts/scripts/chart_advisor.py",
    ),
    # 2D Game Art & Audio
    (
        "chroma-soft-matte-keyer",
        ("key_green.py",),
        ("soft_matte_keyer.py",),
        "EXTRACTED",
        "Soft-matte despill chroma keyer adapted into godot-2d-sprite-and-art-pipeline",
    ),
    (
        "cielab-pixel-downscale-palette",
        ("pixelkit.py",),
        ("pixel_downscale_palette.py",),
        "EXTRACTED",
        "Perceptual CIELAB k-means 1x downscaler ported into godot-2d-pixel-art-forge",
    ),
    (
        "pixelspec-code-art-renderer",
        ("render_pixelspec.py",),
        ("render_pixelspec.py",),
        "EXTRACTED",
        "Code-defined PixelSpec variant renderer ported into godot-2d-pixel-art-forge",
    ),
    (
        "godot-spriteframes-tscn-exporter",
        ("export.py",),
        ("godot_spriteframes_export.py",),
        "EXTRACTED",
        "Godot 4 .tres/.tscn + shadow strip + C# partial controller exporter integrated",
    ),
    (
        "procedural-dsp-sfx-synth",
        ("audio.py",),
        ("synth_sfx.py",),
        "EXTRACTED",
        "Procedural DSP WAV synthesizer adapted into godot-procedural-audio-and-sfx",
    ),
    (
        "wang16-seam-verified-autotile",
        ("autotile_build.py",),
        ("autotile_seam_builder.py",),
        "EXTRACTED",
        "Seam-verified Wang-16 atlas builder integrated in godot-2d-autotile-and-parallax",
    ),
    (
        "svg-bone-rig-keyframe-animator",
        ("rig_animate.py", "svg_render.py"),
        ("rig_animate.py", "svg_render.py"),
        "EXTRACTED",
        "Hierarchical SVG bone animator, two-bone IK, ground clamping & portable SVG rasterizer ported into godot-2d-rig-and-fx-animator",
    ),
    (
        "ambient-motion-baker",
        ("ambient_bake.py",),
        ("ambient_bake.py",),
        "EXTRACTED",
        "Exact-period water ripple, shimmer, foliage sway & glow loop baker ported into godot-2d-rig-and-fx-animator",
    ),
    (
        "pixel-art-qa-gate",
        ("pixel_qa.py",),
        ("pixel_qa.py",),
        "EXTRACTED",
        "Partial-alpha, off-palette, outline-gap, L-corner & onion-skin pixel QA gate ported into godot-2d-pixel-art-forge",
    ),
    (
        "2d-layout-and-nav-reachability-check",
        ("layout_build.py", "forge_nav.py", "parallax_build.py"),
        ("layout_build.py", "forge_nav.py", "parallax_build.py"),
        "EXTRACTED",
        "Spec-driven 2D map builder, periodic parallax generator & BFS reachability verifier ported into godot-2d-autotile-and-parallax",
    ),
    (
        "gameplay-video-frame-gate",
        ("film_gate.py", "qa.py", "storyboard_lint.py"),
        (),
        "OUT_OF_SCOPE",
        "Requires OpenCV + ffmpeg calibrated on Chinese explainer videos (sprite loop-seam & empty-frame QA covered natively in pixel_qa.py & audit_spritesheet_metrics.py)",
    ),
    # 3D & Blender
    (
        "blender-headless-mesh-lod-opt",
        ("generate_lods.py", "optimize_model.py"),
        ("audit_glb_assets.py",),
        "OUT_OF_SCOPE",
        "Shallow 30-line bpy snippet without CLI flags intentionally skipped; GLB draw-call & mesh QA enforced via audit_glb_assets.py",
    ),
    (
        "animation-js-libraries-codegen",
        ("timeline_builder.py", "generate_animation.py", "mesh_builder.py"),
        (),
        "OUT_OF_SCOPE",
        "Shallow JS boilerplate snippets superseded by ui-fluid-novel-system & godot-2d-rig-and-fx-animator",
    ),
    # Out of scope / Paid external services / Red-team offensive
    (
        "paid-image-video-gen-orchestrators",
        ("cli_media.py", "charpipe.py", "grok_x.py", "xai_x.py", "brightdata.py", "bird_x.py"),
        (),
        "OUT_OF_SCOPE",
        "Requires paid third-party SaaS APIs/browser cookies (Tripo3D, OpenAI/Grok/BrightData)",
    ),
    (
        "offensive-redteam-crawler-burp",
        ("osint.py", "burp-mcp.json.example", "agent.py"),
        (),
        "OUT_OF_SCOPE",
        "Offensive bug-bounty crawler/Burp tooling outside defensive dev template scope",
    ),
    (
        "ocr-go-binary-multi-llm-review",
        ("opencodereview", "ocr-acp"),
        (),
        "OUT_OF_SCOPE",
        "Standalone Go CLI/IDE extension using separate external LLM review credentials",
    ),
)


@dataclass
class RepoVerdict:
    name: str
    path: str
    size_mb: float
    total_files: int
    executable_scripts: int
    prompt_only_skills: int
    script_backed_skills: int
    extracted: list[dict[str, str]]
    valuable_pending: list[dict[str, str]]
    out_of_scope: list[dict[str, str]]
    verdict: str


def discover_repos(root: Path) -> list[Path]:
    """Find git/project repos up to depth 2 (supports grouped folders like reference/Juegos/)."""
    repos: list[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        is_repo = (child / ".git").exists() or (child / "README.md").is_file() or (child / "LICENSE").is_file() or (child / "SKILL.md").is_file()
        if is_repo:
            repos.append(child)
        else:
            # Grouped container folder (e.g. reference/Juegos/)
            sub_repos = [
                sub
                for sub in sorted(child.iterdir())
                if sub.is_dir() and not sub.name.startswith(".")
                and ((sub / ".git").exists() or (sub / "README.md").is_file() or (sub / "LICENSE").is_file())
            ]
            repos.extend(sub_repos if sub_repos else [child])
    return repos


def measure_repo(repo: Path) -> tuple[float, int, int, int, int, set[str]]:
    total_bytes = 0
    total_files = 0
    exec_scripts = 0
    basenames: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            total_files += 1
            try:
                total_bytes += fpath.stat().st_size
            except OSError:
                pass
            if fname.startswith("test_") or ".test." in fname or "tests" in Path(dirpath).parts:
                continue
            basenames.add(fname)
            if fpath.suffix.lower() in SCRIPT_EXTS:
                exec_scripts += 1

    backed = 0
    prompt_only = 0
    for smd in repo.rglob("SKILL.md"):
        if any(p in IGNORE_DIRS for p in smd.parts):
            continue
        sdir = smd.parent / "scripts"
        has_exec = sdir.is_dir() and any(f.is_file() and f.suffix.lower() in SCRIPT_EXTS for f in sdir.rglob("*"))
        if has_exec:
            backed += 1
        else:
            prompt_only += 1

    return round(total_bytes / (1024 * 1024), 2), total_files, exec_scripts, backed, prompt_only, basenames


def index_target_files(target: Path) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for p in target.rglob("*"):
        if p.is_file() and not any(part in {".git", "node_modules", "__pycache__"} for part in p.parts):
            mapping.setdefault(p.name, []).append(p.relative_to(target).as_posix())
    return mapping


def analyze_repo(repo: Path, ref_root: Path, target_files: dict[str, list[str]]) -> RepoVerdict:
    size_mb, total_files, exec_scripts, backed, prompt_only, ref_names = measure_repo(repo)
    rel_repo = repo.relative_to(ref_root).as_posix()

    extracted: list[dict[str, str]] = []
    valuable_pending: list[dict[str, str]] = []
    out_of_scope: list[dict[str, str]] = []

    for cap_id, ref_markers, target_markers, default_bucket, notes in CAPABILITY_PROBES:
        matched_ref = [m for m in ref_markers if m in ref_names or any(m in n for n in ref_names)]
        if not matched_ref:
            continue

        present_targets = [p for tm in target_markers for p in target_files.get(tm, [])]
        if default_bucket == "EXTRACTED" and present_targets:
            extracted.append({"capability": cap_id, "source": ", ".join(matched_ref), "in_target": present_targets[0], "notes": notes})
        elif default_bucket == "PARTIAL_OR_ENHANCE":
            valuable_pending.append({"capability": cap_id, "source": ", ".join(matched_ref), "status": "ENHANCE_EXISTING", "notes": notes})
        elif default_bucket == "VALUABLE_PENDING":
            valuable_pending.append({"capability": cap_id, "source": ", ".join(matched_ref), "status": "NEW_CANDIDATE", "notes": notes})
        elif default_bucket == "OUT_OF_SCOPE":
            out_of_scope.append({"capability": cap_id, "source": ", ".join(matched_ref), "notes": notes})
        else:
            # Expected target missing -> downgrade back to pending!
            valuable_pending.append({"capability": cap_id, "source": ", ".join(matched_ref), "status": "MISSING_EXPECTED", "notes": notes})

    if valuable_pending:
        verdict = "REVIEW_REMAINING"
    elif exec_scripts == 0 or (extracted and not valuable_pending):
        verdict = "SAFE_TO_DELETE"
    else:
        verdict = "SAFE_TO_DELETE" if out_of_scope else "MANUAL_CHECK"

    return RepoVerdict(
        name=repo.name,
        path=rel_repo,
        size_mb=size_mb,
        total_files=total_files,
        executable_scripts=exec_scripts,
        prompt_only_skills=prompt_only,
        script_backed_skills=backed,
        extracted=extracted,
        valuable_pending=valuable_pending,
        out_of_scope=out_of_scope,
        verdict=verdict,
    )


def render_markdown(ref_root: Path, target_root: Path, verdicts: list[RepoVerdict]) -> str:
    safe_mb = round(sum(v.size_mb for v in verdicts if v.verdict == "SAFE_TO_DELETE"), 2)
    total_mb = round(sum(v.size_mb for v in verdicts), 2)
    lines = [
        "# Reference Harvest & Prune Report",
        f"> Reference dir: `{ref_root}` ({len(verdicts)} repo(s), {total_mb} MB) | Target: `{target_root}`",
        f"> Reclaimable immediately (`SAFE_TO_DELETE`): **{safe_mb} MB**",
        "",
        "| Repo | Size | Exec Scripts | Prompt-Only Fluff | Extracted | Pending Value | Verdict |",
        "| :--- | ---: | ---: | ---: | :---: | :---: | :--- |",
    ]
    for v in verdicts:
        lines.append(
            f"| `{v.path}` | {v.size_mb} MB | {v.executable_scripts} | {v.prompt_only_skills} | {len(v.extracted)} | {len(v.valuable_pending)} | **{v.verdict}** |"
        )

    lines.extend(["", "## Detailed Gap & Extraction Status"])
    for v in verdicts:
        lines.append(f"\n### `{v.path}` — `{v.verdict}` ({v.size_mb} MB)")
        if v.extracted:
            lines.append("- **Already Extracted into Target:**")
            for item in v.extracted:
                lines.append(f"  - `{item['capability']}` (`{item['source']}`) -> `{item['in_target']}` — {item['notes']}")
        if v.valuable_pending:
            lines.append("- **Valuable Engines Still in Reference (Evaluate Before Deleting):**")
            for item in v.valuable_pending:
                lines.append(f"  - `[{item['status']}]` `{item['capability']}` (`{item['source']}`) — {item['notes']}")
        if v.out_of_scope:
            lines.append("- **Intentionally Skipped (Out-of-Scope / External Paid APIs):**")
            for item in v.out_of_scope:
                lines.append(f"  - `{item['capability']}` — {item['notes']}")
        if not (v.extracted or v.valuable_pending or v.out_of_scope):
            lines.append("- _No recognized reusable engines above baseline; likely safe to archive/delete._")

    safe_paths = [v.path for v in verdicts if v.verdict == "SAFE_TO_DELETE"]
    if safe_paths:
        lines.extend(["", "## Safe Cleanup Candidates (Ready to Delete Once Reviewed)", "```bash"])
        for sp in safe_paths:
            lines.append(f'rm -rf "{ref_root / sp}"')
        lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit external reference repos for noise, extracted assets, pending value, and safe cleanup.")
    parser.add_argument("--ref", default="_reference/repos", help="Reference root directory containing cloned repos")
    parser.add_argument("--target", default=".", help="Target repository or template directory to compare against")
    parser.add_argument("--out", default="-", help="Markdown output file (or '-' for stdout)")
    parser.add_argument("--json-out", help="Optional JSON report path")
    parser.add_argument("--fail-on-pending", action="store_true", help="Exit 1 if valuable engines remain unharvested")
    args = parser.parse_args()

    ref_root = Path(args.ref).resolve()
    target_root = Path(args.target).resolve()
    if not ref_root.is_dir():
        print(f"Reference directory not found: {ref_root}", file=sys.stderr)
        return 1
    if not target_root.is_dir():
        print(f"Target directory not found: {target_root}", file=sys.stderr)
        return 1

    repos = discover_repos(ref_root)
    target_files = index_target_files(target_root)
    verdicts = [analyze_repo(r, ref_root, target_files) for r in repos]

    report_md = render_markdown(ref_root, target_root, verdicts)
    if args.out == "-":
        print(report_md)
    else:
        out_p = Path(args.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(report_md, encoding="utf-8")
        print(f"Wrote reference harvest report to {out_p}")

    if args.json_out:
        jp = Path(args.json_out)
        jp.parent.mkdir(parents=True, exist_ok=True)
        pending_count = sum(len(v.valuable_pending) for v in verdicts)
        jp.write_text(
            json.dumps(
                {
                    "tool": "reference-harvest-and-prune",
                    "status": "WARN" if pending_count else "PASS",
                    "summary": {"repos": len(verdicts), "pending_valuable": pending_count},
                    "verdicts": [asdict(v) for v in verdicts],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    has_pending = any(v.valuable_pending for v in verdicts)
    return 1 if (args.fail_on_pending and has_pending) else 0


if __name__ == "__main__":
    raise SystemExit(main())
