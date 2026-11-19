#!/usr/bin/env python3
"""Zero-dependency Gemini/Antigravity project initializer & selective skill router.

Supports:
- 5-step interactive questionnaire, CLI flags, or conversational Bot Mode
- `--from-spec _reference/SPEC.md` spec-driven bootstrap
- Modular scope composition (`--scope frontend,api,db,ml-gpu,profiling`)
- Infrastructure topology (`--infra single-node|split-cpu-gpu`)
- Strict 2D vs 3D game skill separation (`--dim 2d|3d`, default `2d`)
- Granular documentation selection (`--docs user-guide,adr,agent-guide,benchmarks,es` & `--doc-level`)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

PLACEHOLDER_LINE_RE = re.compile(r"\{\{([A-Z0-9_]+)(?:[^}]*)\}\}")
BOOTSTRAP_BLOCK_RE = re.compile(
    r"\n*<!-- TEMPLATE_BOOTSTRAP_INTERVIEW:START -->.*?<!-- TEMPLATE_BOOTSTRAP_INTERVIEW:END -->\n*",
    re.DOTALL,
)

STACK_BADGES = {
    "web-frontend": (
        "[![TypeScript](https://img.shields.io/badge/TypeScript-5%2B-3178C6.svg)](https://www.typescriptlang.org/)\n"
        "[![Node.js](https://img.shields.io/badge/Node.js-22%2B-339933.svg)](https://nodejs.org/)"
    ),
    "python-cli": (
        "[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)\n"
        "[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)\n"
        "[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)"
    ),
    "python-backend": (
        "[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)\n"
        "[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)\n"
        "[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)"
    ),
    "multi-module": (
        "[![Python](https://img.shields.io/badge/Backend-Python%203.12%2B-blue.svg)](https://www.python.org/)\n"
        "[![Frontend](https://img.shields.io/badge/Frontend-Node.js%2022%2B-339933.svg)](https://nodejs.org/)"
    ),
    "ml-gpu": (
        "[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)\n"
        "[![PyTorch](https://img.shields.io/badge/PyTorch-CUDA%20%7C%20CPU-%23EE4C2C.svg)](https://pytorch.org/)\n"
        "[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)"
    ),
    "gamedev-godot": (
        "[![Godot](https://img.shields.io/badge/Godot-4.x-478CBF.svg)](https://godotengine.org/)\n"
        "[![.NET](https://img.shields.io/badge/.NET-8.0-512BD4.svg)](https://dotnet.microsoft.com/)"
    ),
}

CORE_ALWAYS_SKILLS = [
    "00-core/long-context-state-manager",
    "00-core/anti-laziness-and-evidence-verifier",
    "00-core/repo-map-and-context-pack",
    "00-core/architecture-knowledge-and-docs-sync",
    "00-core/clean-code-and-architecture-gate",
    "00-core/systematic-debugging-and-rca",
    "github/git-commit-and-pr-gate",
]

VALID_SCOPES = ("frontend", "api", "db", "ml-gpu", "profiling")
INFRA_MODES = ("single-node", "split-cpu-gpu")
DOC_OPTION_KEYS = ("user-guide", "adr", "agent-guide", "benchmarks", "es")


def slugify_package(name: str) -> str:
    pkg = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    if not pkg or pkg[0].isdigit():
        pkg = f"app_{pkg}"
    return pkg


def available_stacks(catalog_dir: Path) -> list[str]:
    stacks_dir = catalog_dir / "stacks"
    return sorted(p.parent.name for p in stacks_dir.glob("*/stack.json")) if stacks_dir.is_dir() else []


def load_catalog_index(catalog_dir: Path) -> dict[str, dict[str, object]]:
    cat_file = catalog_dir / "catalog.json"
    if not cat_file.is_file():
        return {}
    entries = json.loads(cat_file.read_text(encoding="utf-8")).get("skills", [])
    by_name: dict[str, dict[str, object]] = {}
    for ent in entries:
        sid = str(ent["id"])
        by_name[sid] = ent
        by_name[Path(sid).name] = ent
    return by_name


INTERACTIVE_HINTS: dict[str, dict[str, str]] = {
    "code_style": {
        "minimal-yagni": "Ponytail minimal: simplest working solution, stdlib first, low LOC",
        "clean-ddd": "Clean Architecture & DDD: pure domain core, inward dependencies, explicit ports",
        "functional-dod": "Functional & Data-Oriented: stateless pipelines, immutable data, explicit contracts",
    },
    "kind": {
        "app-system": "Web app, API service, DB, or ML/GPU system (compose modular scope below)",
        "library-cli": "Installable Python CLI tool or library (zero web/DB/game bloat)",
        "game": "Godot 4.x + C# (.NET 8+) game project with isolated Domain/",
    },
    "scope": {
        "frontend": "Web UI / SaaS / Landing + frontend quality, Lighthouse & aesthetic skills",
        "api": "Backend REST/API layer + .env web-api + OpenAPI contract & security gates",
        "db": "Database/Redis config + SQL/Alembic/Drizzle migration gate",
        "ml-gpu": "Portable cuda/mps/cpu device.py + GPU telemetry & profiling skills",
        "profiling": "Runtime p50/p95 latency, cProfile/tracemalloc & log-leak auditing",
    },
    "infra": {
        "single-node": "Everything runs on one development/host machine",
        "split-cpu-gpu": "Multi-machine CPU + remote GPU/DB nodes (split Compose profiles, no localhost)",
    },
    "ui_style": {
        "minimalist": "Linear / Apple / Retriever 4-phase workflow (dark charcoal or warm light)",
        "neobrutalist": "Gumroad / Figma bold borders, hard 0px offset shadows, high contrast",
        "bento": "Apple WWDC / Framer modular grid cards and layered subtle surfaces",
        "glassmorphic": "visionOS / Raycast translucent panels, controlled blur, 1px borders",
        "enterprise": "Stripe / Atlassian dense data hierarchy, calm slate/navy tables",
        "editorial": "Medium / Substack serif display + sans body, narrow reading measure",
        "terminal": "Teenage Engineering / TUI monospace UI, sharp 0-2px edges, hairline grids",
        "fluid": "Scrollytelling / creative motion via 67+ BM25 styles (ui-fluid-novel-system)",
    },
    "ui_tone": {
        "dark": "Retriever deep charcoal (#141517) + elevated surface (#1C1E21)",
        "light": "Warm bone (#F7F6F2) + elevated white surface (#FFFFFF)",
    },
    "ui_addons": {
        "dataviz": "Include frontend-dataviz-and-charts (21 chart families + SVG/G6 v5 audit)",
        "brand-logo": "Include brand-logo-and-svg-forge (SVG logo forge, README banners, PWA icons)",
    },
    "dim": {
        "2d": "2D fast path: pixel art, SVG bone rigs, Wang-16 autotiles, parallax & WAV SFX (no 3D)",
        "3d": "3D path: GLB/glTF mesh & rig QA + WAV SFX (excludes 2D pixel/tile tools)",
    },
    "doc_level": {
        "minimal": "Mandatory core only (README.md + docs/ARCHITECTURE.md + AGENTS.md)",
        "standard": "Core + docs/USER_GUIDE.md + docs/adr/",
        "full": "Core + USER_GUIDE.md + adr/ + BENCHMARKS.md + bilingual docs/README.es.md",
    },
    "doc_items": {
        "user-guide": "docs/USER_GUIDE.md (setup, usage, env vars & troubleshooting)",
        "adr": "docs/adr/ (Architecture Decision Records)",
        "agent-guide": "docs/AGENT_GUIDE.md (active skills inventory & agent playbook)",
        "benchmarks": "docs/BENCHMARKS.md (latency, memory & GPU evaluation baselines)",
        "es": "docs/README.es.md (bilingual Spanish README)",
    },
}


def prompt_choice(
    label: str,
    options: list[str],
    default: str,
    descriptions: dict[str, str] | None = None,
) -> str:
    print(f"\n{label}:")
    for idx, opt in enumerate(options, start=1):
        mark = " (default)" if opt == default else ""
        desc = f" — {descriptions[opt]}" if descriptions and opt in descriptions else ""
        print(f"  {idx}. {opt}{mark}{desc}")
    raw = input(f"Select [1-{len(options)}] or name [{default}]: ").strip()
    if not raw:
        return default
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    if raw in options:
        return raw
    raise SystemExit(f"Invalid selection: {raw}")


def prompt_multi_choice(
    label: str,
    options: list[str],
    defaults: list[str],
    descriptions: dict[str, str] | None = None,
) -> list[str]:
    default_str = ",".join(defaults)
    print(f"\n{label} (comma-separated numbers or names; 'none' for empty):")
    for idx, opt in enumerate(options, start=1):
        mark = " *" if opt in defaults else ""
        desc = f" — {descriptions[opt]}" if descriptions and opt in descriptions else ""
        print(f"  {idx}. {opt}{mark}{desc}")
    raw = input(f"Select [{default_str or 'none'}]: ").strip()
    if not raw:
        return list(defaults)
    if raw.lower() in {"none", "0"}:
        return []
    picked: list[str] = []
    for tok in [x.strip() for x in raw.split(",") if x.strip()]:
        if tok.isdigit() and 1 <= int(tok) <= len(options):
            val = options[int(tok) - 1]
        elif tok in options:
            val = tok
        else:
            raise SystemExit(f"Invalid selection token: {tok}")
        if val not in picked:
            picked.append(val)
    return picked


def prompt_yes_no(label: str, default: bool) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = input(f"{label} [{hint}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "s", "si"}


UI_STYLES = (
    "minimalist",
    "neobrutalist",
    "bento",
    "glassmorphic",
    "enterprise",
    "editorial",
    "terminal",
    "fluid",
)

CODE_PHILOSOPHY_RULES: dict[str, tuple[str, list[str]]] = {
    "minimal-yagni": (
        "Minimalist / YAGNI (Ponytail 7-Rung Ladder)",
        [
            "Stop at the earliest rung that solves the problem: (1) unnecessary -> skip; (2) reuse existing repo code; (3) stdlib; (4) native platform API; (5) installed dependency; (6) one clear line; (7) minimum working diff.",
            "Before fixing a bug, grep every caller of the touched symbol and fix the root cause once; never duplicate wrappers or `_v2` siblings.",
            "New non-trivial logic (branches, loops, parsers, money, security) leaves a focused test or assert self-check; annotate deliberate trade-offs with `shortcut: <limit>, <when to revisit>`.",
            "Never cut trust-boundary validation, data-loss error handling, security, or accessibility; audit structural bloat via `clean-code-and-architecture-gate` (`scan_repo.py`).",
        ],
    ),
    "clean-ddd": (
        "Clean Architecture, DDD & Deep Modules",
        [
            "Keep domain entities, value objects, and business invariants pure with zero framework or DB imports (prefer deep modules over shallow pass-through wrappers).",
            "Enforce inward dependency flow: interfaces/adapters -> application use cases -> domain core (`check_boundaries.py --json`).",
            "Place files strictly by role (no `utils/`/`helpers/` junk drawers) and run `map_structure.py` to block circular imports and misplaced code.",
        ],
    ),
    "functional-dod": (
        "Functional, Data-Oriented Design & Explicit Contracts",
        [
            "Prefer pure stateless functions, explicit data pipelines, and immutable structures (or flat DOD/ECS tables) over mutable shared state.",
            "Treat schemas, events, APIs, and retries as explicit versioned contracts: make async consumers/jobs idempotent or transactional and distinguish derived caches from source-of-truth state.",
            "Push side effects strictly to thin I/O boundaries.",
        ],
    ),
}

UI_STYLE_RULES: dict[str, str] = {
    "minimalist": "Minimalist (Linear / Apple / Retriever 4-Phase Workflow): Phase 1 concrete 4-6 word copy (zero empty hype adjectives) -> Phase 2 charcoal (#141517) or warm bone (#F7F6F2) palette + 2-3% dot texture + Neo-Grotesque (-0.03em) & uppercase Monospace (+0.08em) via `preset_tokens.py --style minimalist --tone dark|light` -> Phase 3 40/60 interactive product showcase + hairline pillars -> Phase 4 single primary vs subtle secondary CTA & 150-220ms ease-out motion.",
    "neobrutalist": "Neobrutalist (Gumroad / Figma): crisp heavy dark borders, hard 0px-blur offset shadows, high-contrast surfaces, zero blurred glass panels.",
    "bento": "Bento Grid (Apple WWDC / Framer): modular rectangular card tiles of balanced proportions, soft rounded corners, subtle surface hierarchy.",
    "glassmorphic": "Glassmorphic / Spatial (visionOS / Raycast): translucent layered panels with controlled backdrop-blur, 1px light hairline borders, and strict >=4.5:1 text contrast.",
    "enterprise": "Enterprise (Stripe / Atlassian): compact data-dense layout, crisp accessible tables, strict button/status hierarchy, calm slate/navy tones.",
    "editorial": "Editorial / Typographic (Medium / Substack): reading-first rhythm, serif display + sans body pairing, narrow prose measure (~65ch), subtle transitions.",
    "terminal": "Retro / Terminal / Hacker (Teenage Engineering / TUI): monospace UI typography everywhere, sharp 0-2px edges, 1px hairline borders, high-contrast phosphor/amber accents on obsidian.",
    "fluid": "Fluid Creative (BM25 / Scrollytelling): atmospheric motion choreography driven by `ui-fluid-novel-system`, always honoring `prefers-reduced-motion`.",
}

DOC_DISCIPLINE_RULES: dict[str, tuple[str, list[str]]] = {
    "minimal": (
        "Docs Basic (`minimal`)",
        [
            "Update `README.md` only when installation, startup commands, CLI flags, or environment variables change.",
            "Keep `docs/ARCHITECTURE.md` concise; skip ADRs and extended guides unless requested.",
        ],
    ),
    "standard": (
        "Docs Standard (`standard`)",
        [
            "Run `sync_arch_graph.py --write` on `docs/ARCHITECTURE.md` whenever modules or package boundaries change.",
            "Include clear behavioral summaries and verification evidence in every PR (`git-commit-and-pr-gate`).",
        ],
    ),
    "full": (
        "Docs Exhaustive (`full`)",
        [
            "Author an ADR in `docs/adr/` BEFORE introducing structural or architectural changes.",
            "Keep `docs/ARCHITECTURE.md` Mermaid graphs, `docs/USER_GUIDE.md`, `docs/BENCHMARKS.md`, and bilingual docs synchronized.",
        ],
    ),
}


def parse_spec_defaults(spec_path: Path) -> dict[str, object]:
    """Extract checked options across all 5 modular setup steps from `_reference/SPEC.md`."""
    if not spec_path.is_file():
        raise SystemExit(f"SPEC file not found: {spec_path}")
    text = spec_path.read_text(encoding="utf-8", errors="replace")
    low = text.lower()
    out: dict[str, object] = {}

    for code_style in CODE_PHILOSOPHY_RULES:
        if re.search(rf"-\s*\[x\]\s*`?{re.escape(code_style)}`?", low):
            out["code_style"] = code_style
            break

    for kind in ("app-system", "library-cli", "game"):
        if re.search(rf"-\s*\[x\]\s*`?{re.escape(kind)}`?", low):
            out["kind"] = kind
            break

    for stack in ("web-frontend", "python-cli", "python-backend", "multi-module", "ml-gpu", "gamedev-godot"):
        if re.search(rf"\[x\]\s*`?{re.escape(stack)}`?", low):
            out["stack"] = stack
            break

    checked_scopes: list[str] = []
    for sc in VALID_SCOPES:
        if re.search(rf"-\s*\[x\]\s*`?{re.escape(sc)}`?\s*(?:\(|$)", low, re.MULTILINE):
            checked_scopes.append(sc)
    if checked_scopes:
        out["scope"] = ",".join(checked_scopes)

    for infra in INFRA_MODES:
        if re.search(rf"-\s*\[x\]\s*`?{re.escape(infra)}`?", low):
            out["infra"] = infra
            break

    if re.search(r"-\s*\[x\]\s*`?ui-minimalist-system`?", low):
        out["ui_profile"] = "minimalist"
    elif re.search(r"-\s*\[x\]\s*`?ui-fluid-novel-system`?", low):
        out["ui_profile"] = "fluid"
    else:
        for style in UI_STYLES:
            if re.search(rf"-\s*\[x\]\s*`?{re.escape(style)}`?", low):
                out["ui_profile"] = style
                break

    for tone in ("dark", "light"):
        if re.search(rf"-\s*\[x\]\s*`?{tone}`?\s*\(", low):
            out["ui_tone"] = tone
            break

    if re.search(r"-\s*\[x\]\s*`?dataviz`?", low):
        out["with_dataviz"] = True
    if re.search(r"-\s*\[x\]\s*`?brand-logo`?", low):
        out["with_brand_logo"] = True

    for lvl in ("minimal", "standard", "full"):
        if re.search(rf"-\s*\[x\]\s*`?(?:doc-level\s*:?\s*|docs-)?{lvl}`?", low):
            out["doc_level"] = lvl
            break

    doc_items: list[str] = []
    for dk in DOC_OPTION_KEYS:
        if re.search(rf"-\s*\[x\]\s*`?{re.escape(dk)}`?\s*\(", low):
            doc_items.append(dk)
    if re.search(r"-\s*\[x\]\s*`?(?:bilingual\s+readme|bilingual\b)", low) and "es" not in doc_items:
        doc_items.append("es")
    if re.search(r"-\s*\[x\]\s*`?(?:evaluation\s*/\s*benchmarks|benchmarks\b)", low) and "benchmarks" not in doc_items:
        doc_items.append("benchmarks")
    if doc_items:
        out["docs_items"] = doc_items

    if re.search(r"-\s*\[x\]\s*`?3d\b", low):
        out["dim"] = "3d"
    elif re.search(r"-\s*\[x\]\s*`?2d\b", low):
        out["dim"] = "2d"

    if re.search(r"-\s*\[x\]\s*`?docker\b", low):
        out["docker"] = True
    return out


def replace_tokens(text: str, mapping: dict[str, str]) -> str:
    result = text
    for k, v in mapping.items():
        result = result.replace(f"{{{{{k}}}}}", v)

    def _fallback(match: re.Match[str]) -> str:
        return mapping.get(match.group(1), match.group(0))

    return PLACEHOLDER_LINE_RE.sub(_fallback, result)


def copy_stack_template(template_dir: Path, root: Path, tokens: dict[str, str]) -> None:
    if not template_dir.is_dir():
        return
    for src in sorted(template_dir.rglob("*")):
        rel_str = src.relative_to(template_dir).as_posix()
        dest = root / replace_tokens(rel_str, tokens)
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = src.read_bytes()
        try:
            dest.write_text(replace_tokens(raw.decode("utf-8"), tokens), encoding="utf-8")
        except UnicodeDecodeError:
            dest.write_bytes(raw)


def update_gitignore(root: Path, stack_dir: Path) -> None:
    gi_path = root / ".gitignore"
    text = gi_path.read_text(encoding="utf-8")
    stage_a_pattern = re.compile(r"# Two-stage Git lifecycle:.*?!_reference/assets/\.gitkeep\n", re.DOTALL)
    text = stage_a_pattern.sub(
        "# Reference sandbox (_reference/) is strictly local/private in initialized projects.\n_reference/\n",
        text,
    )
    frag_path = stack_dir / "gitignore.fragment"
    if frag_path.is_file():
        frag = frag_path.read_text(encoding="utf-8").strip()
        marker = "# 4. Stack-Specific Ignores (Populated from _catalog/stacks/*/gitignore.fragment)\n# =============================================================================="
        if marker in text:
            text = text.replace(marker, f"{marker}\n{frag}", 1)
        else:
            text = text.rstrip() + "\n\n" + frag + "\n"
    gi_path.write_text(text, encoding="utf-8")

    if (root / ".git").exists():
        subprocess.run(["git", "rm", "--cached", "-r", "--ignore-unmatch", "--quiet", "_reference"], cwd=root, check=False)


def resolve_doc_selection(
    doc_level: str,
    raw_docs: str | None,
    spec_doc_items: list[str],
    with_benchmarks_flag: bool,
    stack_name: str,
) -> tuple[set[str], str]:
    """Return (active_optional_doc_keys,effective_doc_level)."""
    items: set[str] = set()
    if doc_level == "standard":
        items.update({"user-guide", "adr"})
    elif doc_level == "full":
        items.update({"user-guide", "adr", "benchmarks", "es"})

    if stack_name == "ml-gpu" or with_benchmarks_flag:
        items.add("benchmarks")

    for it in spec_doc_items:
        if it in DOC_OPTION_KEYS:
            items.add(it)

    if raw_docs:
        tokens = [x.strip().lower() for x in raw_docs.split(",") if x.strip()]
        if tokens == ["en"]:
            items.discard("es")
        elif tokens == ["bilingual"]:
            items.add("es")
        elif tokens == ["minimal"] or tokens == ["none"]:
            items.clear()
        else:
            # Explicit modular `--docs user-guide,adr,...`: start from explicit selection unless + prefix or combined with doc_level
            if not any(t in {"en", "bilingual"} for t in tokens):
                items = set()
            for t in tokens:
                if t in {"bilingual", "es"}:
                    items.add("es")
                elif t == "en":
                    items.discard("es")
                elif t in DOC_OPTION_KEYS:
                    items.add(t)
                else:
                    raise SystemExit(
                        f"Unknown `--docs` option `{t}`. Valid: {', '.join(DOC_OPTION_KEYS)} (or legacy `en`, `bilingual`)."
                    )
            if with_benchmarks_flag:
                items.add("benchmarks")

    return items, doc_level


def update_docs(
    root: Path,
    catalog_dir: Path,
    tokens: dict[str, str],
    use_docker: bool,
    dotenv_profiles: list[str],
    doc_level: str,
    doc_items: set[str],
    *,
    code_style: str,
    infra_mode: str,
    scope_list: list[str],
    installed_skills: list[str],
) -> None:
    include_user_guide = "user-guide" in doc_items
    include_adr = "adr" in doc_items
    include_agent_guide = "agent-guide" in doc_items
    with_benchmarks = "benchmarks" in doc_items
    include_es = "es" in doc_items

    # Strip Bot-Mode bootstrap section from root AGENTS.md
    agents_md_path = root / "AGENTS.md"
    if agents_md_path.is_file():
        cleaned_agents = BOOTSTRAP_BLOCK_RE.sub("\n\n", agents_md_path.read_text(encoding="utf-8")).strip() + "\n"
        agents_md_path.write_text(cleaned_agents, encoding="utf-8")

    docker_badge = (
        "\n[![Docker](https://img.shields.io/badge/Docker-Reproducible-2496ED.svg)](compose.yaml)"
        if use_docker
        else ""
    )
    stack_badges = STACK_BADGES.get(tokens["STACK_NAME"], "") + docker_badge
    visual_comment = (
        "<!-- Add project screenshot or preview banner here (assets/preview.png) -->\n"
        if ("frontend" in scope_list or tokens["STACK_NAME"] in {"web-frontend", "multi-module", "gamedev-godot"})
        else ""
    )

    user_guide_row = (
        "| **User Guide** | [User Guide](docs/USER_GUIDE.md) | Environment setup, CLI flags, container profiles, and troubleshooting |\n"
        if include_user_guide
        else ""
    )
    if include_agent_guide:
        user_guide_row += (
            "| **Agent Guide** | [Agent Guide](docs/AGENT_GUIDE.md) | Active coding philosophy, topology, installed skills & verification gates |\n"
        )

    doc_tokens = {
        **tokens,
        "STACK_BADGES": stack_badges.strip(),
        "VISUAL_PREVIEW_COMMENT": visual_comment.rstrip(),
        "LANG_SWITCHER": "[English](README.md) | [Español](docs/README.es.md)" if include_es else "",
        "BENCHMARK_DOC_NOTE": ", and Benchmarks" if with_benchmarks else "",
        "USER_GUIDE_DOC_ROW": user_guide_row,
        "USER_GUIDE_EXTENDED_NOTE": (
            "2. See [User Guide](docs/USER_GUIDE.md) for environment variables, container profiles, and operational commands."
            if include_user_guide
            else "2. See [Architecture](docs/ARCHITECTURE.md) for module responsibilities and the live knowledge graph."
        ),
        "BENCHMARKS_DOC_ROW_ROOT": (
            "| **Evaluation & Benchmarks** | [Benchmarks](docs/BENCHMARKS.md) | Metrics methodology, hardware profiling, and baselines |\n"
            if with_benchmarks
            else ""
        ),
        "BENCHMARKS_DOC_ROW_DOCS": (
            "| **Evaluación y Benchmarks** | [Benchmarks](BENCHMARKS.md) | Metodología de métricas, perfiles de hardware y baselines |\n"
            if with_benchmarks
            else ""
        ),
        "ADR_DOC_ROW": (
            "| **Architecture Decisions** | [ADRs](docs/adr/README.md) | Historical records of key technical choices |\n"
            if include_adr
            else ""
        ),
        "DOCKER_README_BLOCK": (
            (catalog_dir / "addons" / "docker" / "README.docker.md").read_text(encoding="utf-8").strip()
            if use_docker
            else ""
        ),
    }

    proj_readme_tpl = catalog_dir / "docs" / "PROJECT_README.md"
    if proj_readme_tpl.is_file():
        rendered = replace_tokens(proj_readme_tpl.read_text(encoding="utf-8"), doc_tokens).lstrip()
        rendered = re.sub(r"\n{3,}", "\n\n", rendered)
        (root / "README.md").write_text(rendered, encoding="utf-8")

    es_dest = root / "docs" / "README.es.md"
    if include_es:
        es_tpl = catalog_dir / "docs" / "PROJECT_README.es.md"
        if es_tpl.is_file():
            es_txt = replace_tokens(es_tpl.read_text(encoding="utf-8"), doc_tokens)
            if not include_user_guide:
                es_txt = es_txt.replace(
                    "| **Manual de Usuario** | [User Guide (EN)](USER_GUIDE.md) | Instalación, variables de entorno, perfiles y resolución de problemas |\n",
                    "",
                )
            if not include_adr:
                es_txt = es_txt.replace(
                    "| **Decisiones de Arquitectura** | [ADRs](adr/README.md) | Registro histórico de decisiones técnicas clave |\n",
                    "",
                )
            es_dest.write_text(es_txt, encoding="utf-8")
    elif es_dest.is_file():
        es_dest.unlink()

    if with_benchmarks:
        bench_tpl = catalog_dir / "docs" / "BENCHMARKS.md"
        if bench_tpl.is_file():
            shutil.copy2(bench_tpl, root / "docs" / "BENCHMARKS.md")
    elif (root / "docs" / "BENCHMARKS.md").is_file():
        (root / "docs" / "BENCHMARKS.md").unlink()

    ug_path = root / "docs" / "USER_GUIDE.md"
    if include_user_guide and ug_path.is_file():
        ug = replace_tokens(ug_path.read_text(encoding="utf-8"), doc_tokens)
        env_marker = "<!-- Optional addon configuration sections (e.g., Environment Variables table from _catalog/addons/dotenv/) are injected here when enabled -->"
        doc_marker = "<!-- Optional addon execution sections (e.g., Docker Compose profiles from _catalog/addons/docker/) are injected here when enabled -->"
        if dotenv_profiles:
            env_snip = replace_tokens(
                (catalog_dir / "addons" / "dotenv" / "USER_GUIDE.env.md").read_text(encoding="utf-8").strip(),
                doc_tokens,
            )
            ug = ug.replace(env_marker, env_snip)
        else:
            ug = ug.replace(f"\n{env_marker}\n", "\n")
        if use_docker:
            doc_snip = replace_tokens(
                (catalog_dir / "addons" / "docker" / "USER_GUIDE.docker.md").read_text(encoding="utf-8").strip(),
                doc_tokens,
            )
            ug = ug.replace(doc_marker, doc_snip)
        else:
            ug = ug.replace(f"\n{doc_marker}\n", "\n")
        ug_path.write_text(ug, encoding="utf-8")
    elif not include_user_guide and ug_path.is_file():
        ug_path.unlink()

    if not include_adr and (root / "docs" / "adr").is_dir():
        shutil.rmtree(root / "docs" / "adr")

    agent_guide_path = root / "docs" / "AGENT_GUIDE.md"
    if include_agent_guide:
        skills_bullets = "\n".join(f"- `{s}` (`.agents/skills/{s}/SKILL.md`)" for s in installed_skills)
        agent_guide_path.write_text(
            f"# Agent Engineering Guide — {tokens['PROJECT_NAME']}\n\n"
            "## 1. Active Project Profile\n\n"
            f"- **Coding Philosophy**: `{code_style}` (`.agents/rules/code-philosophy.md`)\n"
            f"- **Base Stack**: `{tokens['STACK_NAME']}`\n"
            f"- **Modular Scope**: `{', '.join(scope_list) if scope_list else 'core'}`\n"
            f"- **Infrastructure Topology**: `{infra_mode}`\n\n"
            "## 2. Installed Executable Skills (`.agents/skills/`)\n\n"
            f"{skills_bullets}\n\n"
            "## 3. Standard Verification Loop\n\n"
            "1. Read [Architecture](ARCHITECTURE.md) (`ARCH_GRAPH`) before structural edits.\n"
            "2. Run `--help` on any skill script under `.agents/skills/<skill>/scripts/` before invoking.\n"
            "3. Verify changes with `make verify` and `.agents/skills/anti-laziness-and-evidence-verifier/scripts/verify_completion.py`.\n",
            encoding="utf-8",
        )
    elif agent_guide_path.is_file():
        agent_guide_path.unlink()

    arch_path = root / "docs" / "ARCHITECTURE.md"
    if arch_path.is_file():
        arch_txt = arch_path.read_text(encoding="utf-8")
        if not include_user_guide:
            arch_txt = arch_txt.replace(
                "Do not duplicate installation or usage instructions here (see [User Guide](USER_GUIDE.md)).",
                "Minimal doc profile: keep this file focused on module boundaries and the live knowledge graph.",
            )
        if not include_adr:
            arch_txt = arch_txt.replace("See [ADR-0001](adr/README.md)", "Documented inline")
        arch_path.write_text(arch_txt, encoding="utf-8")


def resolve_stack_and_scope(
    raw_kind: str | None,
    raw_stack: str | None,
    raw_scope: str | None,
    features: list[str],
) -> tuple[str, str | None, list[str], bool]:
    """Return (kind, stack_name, normalized_scope_list, scope_was_explicit)."""
    scope_explicit = bool(raw_scope)
    scope_list: list[str] = []
    if raw_scope:
        for tok in [x.strip().lower() for x in raw_scope.split(",") if x.strip()]:
            if tok not in VALID_SCOPES:
                raise SystemExit(f"Unknown `--scope` component `{tok}`. Valid: {', '.join(VALID_SCOPES)}")
            if tok not in scope_list:
                scope_list.append(tok)

    for f in features:
        if f in {"db", "api", "frontend", "ml-gpu", "profiling"} and f not in scope_list:
            scope_list.append(f)

    stack_name = raw_stack
    kind = raw_kind

    if not stack_name:
        if kind == "library-cli":
            stack_name = "python-cli"
        elif kind == "game":
            stack_name = "gamedev-godot"
        elif scope_list:
            has_fe = "frontend" in scope_list
            has_be = any(k in scope_list for k in ("api", "db"))
            has_ml = "ml-gpu" in scope_list
            if has_fe and (has_be or has_ml):
                stack_name = "multi-module"
            elif has_fe:
                stack_name = "web-frontend"
            elif has_ml and not has_be:
                stack_name = "ml-gpu"
            else:
                stack_name = "python-backend"
        elif kind == "app-system":
            stack_name = "python-backend"
            scope_list = ["api"]

    if stack_name and not scope_list and not scope_explicit:
        default_scopes_by_stack = {
            "web-frontend": ["frontend"],
            "python-cli": [],
            "python-backend": ["api"],
            "multi-module": ["frontend", "api"],
            "ml-gpu": ["ml-gpu", "profiling"],
            "gamedev-godot": [],
        }
        scope_list = list(default_scopes_by_stack.get(stack_name, []))
        for f in features:
            if f in VALID_SCOPES and f not in scope_list:
                scope_list.append(f)

    if not kind and stack_name:
        if stack_name == "python-cli":
            kind = "library-cli"
        elif stack_name == "gamedev-godot":
            kind = "game"
        else:
            kind = "app-system"

    return kind or "app-system", stack_name, scope_list, scope_explicit


def resolve_skills_list(
    catalog_dir: Path,
    manifest: dict[str, object],
    stack_name: str,
    scope_list: list[str],
    scope_explicit: bool,
    infra_mode: str,
    use_docker: bool,
    ui_profile: str | None,
    dim: str | None,
    features: list[str],
    explicit_skills: str | None,
    with_meta: bool,
    with_profiling: bool,
) -> list[str]:
    if explicit_skills:
        catalog_idx = load_catalog_index(catalog_dir)
        resolved: list[str] = []
        for tok in [x.strip() for x in explicit_skills.split(",") if x.strip()]:
            ent = catalog_idx.get(tok)
            resolved.append(str(ent["id"]) if ent else tok)
    elif scope_explicit and stack_name != "gamedev-godot":
        resolved = list(CORE_ALWAYS_SKILLS)
        if "frontend" in scope_list:
            resolved.extend(
                [
                    "frontend/frontend-quality-and-design-gate",
                    "frontend/frontend-lighthouse-and-design-audit",
                ]
            )
            if ui_profile == "fluid":
                resolved.append("frontend/ui-fluid-novel-system")
            else:
                resolved.append("frontend/ui-design-tokens-and-presets")
        if "api" in scope_list or "db" in scope_list or "ml-gpu" in scope_list:
            resolved.extend(
                [
                    "backend/backend-quality-and-contracts",
                    "backend/backend-security-and-owasp-gate",
                ]
            )
        if "api" in scope_list:
            resolved.append("backend/api-openapi-contract-gate")
        if "db" in scope_list:
            resolved.append("backend/db-migration-and-schema-gate")
        if "ml-gpu" in scope_list:
            resolved.append("infra/ml-gpu-workload-harness")
        if "profiling" in scope_list or "ml-gpu" in scope_list or with_profiling:
            resolved.append("testing/runtime-profiling-and-observability")
        resolved.append("testing/test-and-mutation-gate")
        if use_docker or infra_mode == "split-cpu-gpu":
            resolved.append("infra/docker-and-env-auditor")
    else:
        resolved = list(manifest.get("skills", []))  # type: ignore[arg-type]
        if manifest.get("supports_dimension") and dim:
            if features:
                fmap: dict[str, str] = dict(manifest.get("feature_skill_map", {}))  # type: ignore[arg-type]
                for feat in features:
                    if feat in fmap and fmap[feat] not in resolved:
                        if dim == "2d" and feat == "3d-assets":
                            continue
                        resolved.append(fmap[feat])
            else:
                dim_skills = manifest.get("dimension_skills", {}).get(dim, [])  # type: ignore[union-attr]
                for s in dim_skills:
                    if s not in resolved:
                        resolved.append(str(s))

        if (manifest.get("supports_ui_profile") or "frontend" in scope_list) and ui_profile:
            if ui_profile == "fluid":
                if "frontend/ui-fluid-novel-system" not in resolved:
                    resolved.append("frontend/ui-fluid-novel-system")
            elif ui_profile in UI_STYLES:
                if "frontend/ui-design-tokens-and-presets" not in resolved:
                    resolved.append("frontend/ui-design-tokens-and-presets")

        if "api" in scope_list and "backend/api-openapi-contract-gate" not in resolved:
            resolved.append("backend/api-openapi-contract-gate")
        if "db" in scope_list and "backend/db-migration-and-schema-gate" not in resolved:
            resolved.append("backend/db-migration-and-schema-gate")
        if "ml-gpu" in scope_list and "infra/ml-gpu-workload-harness" not in resolved:
            resolved.append("infra/ml-gpu-workload-harness")
        if ("profiling" in scope_list or "ml-gpu" in scope_list or with_profiling) and (
            "testing/runtime-profiling-and-observability" not in resolved
        ):
            resolved.append("testing/runtime-profiling-and-observability")
        if (use_docker or infra_mode == "split-cpu-gpu") and stack_name != "gamedev-godot":
            if "infra/docker-and-env-auditor" not in resolved:
                resolved.append("infra/docker-and-env-auditor")

    opt_map: dict[str, str] = {
        **dict(manifest.get("optional_features", {})),  # type: ignore[arg-type]
        "dataviz": "frontend/frontend-dataviz-and-charts",
        "brand-logo": "frontend/brand-logo-and-svg-forge",
        "logo": "frontend/brand-logo-and-svg-forge",
        "db": "backend/db-migration-and-schema-gate",
        "api": "backend/api-openapi-contract-gate",
        "profiling": "testing/runtime-profiling-and-observability",
    }
    for feat in features:
        if feat in opt_map and opt_map[feat] not in resolved:
            resolved.append(opt_map[feat])

    if with_meta:
        for meta_s in (
            "00-core/skill-authoring-and-updater",
            "00-core/skill-radar-and-proposals",
            "00-core/reference-harvest-and-prune",
        ):
            if meta_s not in resolved:
                resolved.append(meta_s)
    return resolved


def inject_skills(root: Path, catalog_dir: Path, skills_rel: list[str]) -> list[str]:
    skills_dest = root / ".agents" / "skills"
    skills_dest.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    for rel in skills_rel:
        src_dir = catalog_dir / "skills" / rel
        if not src_dir.is_dir():
            raise SystemExit(f"Missing catalog skill directory: {src_dir}")
        skill_name = src_dir.name
        dest_dir = skills_dest / skill_name
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(src_dir, dest_dir)
        installed.append(skill_name)
    return installed


def _link_or_copy_skills(src_skills: Path, link_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink() or link_path.is_file():
        link_path.unlink()
    elif link_path.is_dir():
        shutil.rmtree(link_path)
    try:
        rel_target = Path("..") / ".agents" / "skills"
        link_path.symlink_to(rel_target, target_is_directory=True)
    except OSError:
        shutil.copytree(src_skills, link_path)


def inject_rules_and_hooks(
    root: Path,
    catalog_dir: Path,
    manifest: dict[str, object],
    use_docker: bool,
    *,
    code_style: str,
    ui_style: str | None,
    ui_tone: str | None,
    infra_mode: str,
    doc_level: str,
    agents_mode: str,
    project_name: str,
) -> None:
    rules_dest = root / ".agents" / "rules"
    rules_dest.mkdir(parents=True, exist_ok=True)
    rules = list(manifest.get("rules", []))  # type: ignore[arg-type]
    if use_docker and "docker-and-env.md" not in rules:
        rules.append("docker-and-env.md")

    for rule_file in rules:
        src = catalog_dir / "rules" / str(rule_file)
        if src.is_file():
            shutil.copy2(src, rules_dest / str(rule_file))

    for mapping in manifest.get("src_agents_rules", []):  # type: ignore[attr-defined]
        src = catalog_dir / "rules" / str(mapping["source"])
        dest = root / str(mapping["dest"])
        if src.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    phil_title, phil_bullets = CODE_PHILOSOPHY_RULES[code_style]
    (rules_dest / "code-philosophy.md").write_text(
        "---\ntrigger: always_on\n---\n\n"
        f"# Code Philosophy: {phil_title}\n\n"
        + "\n".join(f"- {b}" for b in phil_bullets)
        + "\n",
        encoding="utf-8",
    )

    doc_title, doc_bullets = DOC_DISCIPLINE_RULES[doc_level]
    (rules_dest / "docs-discipline.md").write_text(
        "---\ntrigger: always_on\n---\n\n"
        f"# Documentation Discipline: {doc_title}\n\n"
        + "\n".join(f"- {b}" for b in doc_bullets)
        + "\n",
        encoding="utf-8",
    )

    if infra_mode == "split-cpu-gpu":
        (rules_dest / "infra-topology.md").write_text(
            "---\ntrigger: always_on\n---\n\n"
            "# Infrastructure Topology: `split-cpu-gpu` (Multi-Node)\n\n"
            "- Execution is split across nodes (`app-cpu`, `db`, `gpu-worker`).\n"
            "- Never hardcode `localhost` or `127.0.0.1` for cross-node services; always read `REMOTE_WORKER_URL`, `GPU_NODE_HOST`, `DATABASE_URL`, and `REDIS_URL` from environment variables.\n"
            "- Use `docker compose --profile app-cpu|db|gpu-worker up -d` (`make up-cpu`, `make up-db`, `make up-gpu-worker`).\n"
            "- On the remote `gpu-worker` node, run pre-flight `bash .agents/skills/ml-gpu-workload-harness/scripts/gpu_health.sh --require-gpu` before starting heavy inference/training and capture worker RSS/VRAM via `mem_monitor.sh`.\n",
            encoding="utf-8",
        )

    if ui_style and ui_style in UI_STYLE_RULES:
        tone_note = f" (active polarity: `--tone {ui_tone}`)" if ui_tone else ""
        (rules_dest / "ui-aesthetic.md").write_text(
            "---\ntrigger: glob\nglobs: \"**/*.tsx, **/*.jsx, **/*.svelte, **/*.astro, **/*.html, **/*.css\"\n---\n\n"
            f"# Active Frontend Aesthetic: `{ui_style}`{tone_note}\n\n"
            f"- {UI_STYLE_RULES[ui_style]}\n"
            "- Enforce rules via `python3 .agents/skills/frontend-quality-and-design-gate/scripts/run_frontend_pipeline.py run`.\n",
            encoding="utf-8",
        )
        pipeline_py = root / ".agents" / "skills" / "frontend-quality-and-design-gate" / "scripts" / "run_frontend_pipeline.py"
        if pipeline_py.is_file():
            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(pipeline_py),
                    "init",
                    "--style",
                    ui_style,
                    "--project",
                    project_name,
                    "--contract",
                    str(root / ".agents" / "ui-contract.json"),
                ],
                check=False,
                capture_output=True,
            )
        preset_py = root / ".agents" / "skills" / "ui-design-tokens-and-presets" / "scripts" / "preset_tokens.py"
        if preset_py.is_file() and ui_style != "fluid" and ui_tone:
            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(preset_py),
                    "--style",
                    ui_style,
                    "--tone",
                    ui_tone,
                    "--out-dir",
                    str(root / "assets" / "tokens"),
                ],
                check=False,
                capture_output=True,
            )

    hooks_json = catalog_dir / "hooks" / "hooks.json"
    guard_py = catalog_dir / "hooks" / "hooks" / "pre_tool_guard.py"
    if hooks_json.is_file():
        shutil.copy2(hooks_json, root / ".agents" / "hooks.json")
    if guard_py.is_file():
        dest_hook = root / ".agents" / "hooks" / "pre_tool_guard.py"
        dest_hook.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(guard_py, dest_hook)

    skills_src = root / ".agents" / "skills"
    if agents_mode in {"all", "gemini"}:
        gem_cfg = catalog_dir / "hooks" / "gemini.settings.json"
        if gem_cfg.is_file():
            (root / ".gemini").mkdir(parents=True, exist_ok=True)
            shutil.copy2(gem_cfg, root / ".gemini" / "settings.json")
        if skills_src.is_dir():
            _link_or_copy_skills(skills_src, root / ".gemini" / "skills")
        (root / "GEMINI.md").write_text(
            "@AGENTS.md\n\n"
            "## Active Rules & Skills (Gemini CLI)\n"
            "- Skills directory: `.agents/skills/` (linked at `.gemini/skills/`)\n"
            "- Project rules: `.agents/rules/code-philosophy.md`, `.agents/rules/docs-discipline.md`\n",
            encoding="utf-8",
        )

    if agents_mode in {"all", "claude"}:
        claude_cfg = catalog_dir / "hooks" / "claude.settings.json"
        if claude_cfg.is_file():
            (root / ".claude").mkdir(parents=True, exist_ok=True)
            shutil.copy2(claude_cfg, root / ".claude" / "settings.json")
        if skills_src.is_dir():
            _link_or_copy_skills(skills_src, root / ".claude" / "skills")
        (root / "CLAUDE.md").write_text(
            "@AGENTS.md\n\n"
            "## Active Rules & Skills (Claude Code)\n"
            "- Skills directory: `.agents/skills/` (linked at `.claude/skills/`)\n"
            "- Project rules: `.agents/rules/code-philosophy.md`, `.agents/rules/docs-discipline.md`\n",
            encoding="utf-8",
        )


def configure_addons(
    root: Path,
    catalog_dir: Path,
    stack_dir: Path,
    tokens: dict[str, str],
    use_docker: bool,
    dotenv_profiles: list[str],
    *,
    infra_mode: str,
    scope_list: list[str],
) -> None:
    make_dir = root / ".make"
    make_dir.mkdir(parents=True, exist_ok=True)
    stack_mk = stack_dir / "stack.mk"
    if stack_mk.is_file():
        (make_dir / "stack.mk").write_text(replace_tokens(stack_mk.read_text(encoding="utf-8"), tokens), encoding="utf-8")

    if "ml-gpu" in scope_list and tokens["STACK_NAME"] != "ml-gpu":
        # Inject portable device.py resolver when ml-gpu is composed into another stack
        pkg_dir = (
            root / "backend" / "src"
            if (root / "backend").is_dir()
            else root / "src" / tokens["PACKAGE_NAME"]
        )
        pkg_dir.mkdir(parents=True, exist_ok=True)
        dev_src = catalog_dir / "stacks" / "ml-gpu" / "template" / "src" / "{{PACKAGE_NAME}}" / "device.py"
        if dev_src.is_file() and not (pkg_dir / "device.py").exists():
            (pkg_dir / "device.py").write_text(
                replace_tokens(dev_src.read_text(encoding="utf-8"), tokens),
                encoding="utf-8",
            )

    if use_docker:
        docker_mk = catalog_dir / "addons" / "docker" / "Makefile.docker.mk"
        dockerignore = catalog_dir / "addons" / "docker" / ".dockerignore"
        if docker_mk.is_file():
            mk_txt = docker_mk.read_text(encoding="utf-8")
            if infra_mode == "split-cpu-gpu":
                mk_txt = (
                    mk_txt.replace(".PHONY: up up-deps up-prod down logs", ".PHONY: up up-deps up-prod up-cpu up-db up-gpu-worker down logs")
                    .rstrip()
                    + "\n\nup-cpu: ## Start CPU application node only (profile: app-cpu)\n"
                    "\tdocker compose --profile app-cpu up -d --build\n\n"
                    "up-db: ## Start database/cache node only (profile: db)\n"
                    "\tdocker compose --profile db up -d\n\n"
                    "up-gpu-worker: ## Start remote GPU inference/training worker node (profile: gpu-worker)\n"
                    "\tdocker compose --profile gpu-worker up -d --build\n"
                )
            (make_dir / "docker.mk").write_text(mk_txt, encoding="utf-8")
        if dockerignore.is_file():
            shutil.copy2(dockerignore, root / ".dockerignore")

        if infra_mode == "split-cpu-gpu":
            (root / "compose.yaml").write_text(
                "services:\n"
                "  app-cpu:\n"
                "    build: .\n"
                "    profiles: [\"app-cpu\", \"dev\", \"prod\"]\n"
                "    env_file:\n"
                "      - .env\n"
                "    ports:\n"
                "      - \"${PORT:-8000}:8000\"\n"
                "    restart: unless-stopped\n\n"
                "  db:\n"
                "    image: postgres:16-alpine\n"
                "    profiles: [\"db\", \"deps\", \"dev\"]\n"
                "    environment:\n"
                "      POSTGRES_USER: ${POSTGRES_USER:-app}\n"
                "      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}\n"
                f"      POSTGRES_DB: ${{POSTGRES_DB:-{tokens['PACKAGE_NAME']}}}\n"
                "    ports:\n"
                "      - \"${POSTGRES_PORT:-5432}:5432\"\n\n"
                "  gpu-worker:\n"
                "    build: .\n"
                "    profiles: [\"gpu-worker\", \"gpu\"]\n"
                "    env_file:\n"
                "      - .env\n"
                "    ports:\n"
                "      - \"${GPU_WORKER_PORT:-8081}:8081\"\n",
                encoding="utf-8",
            )

    if dotenv_profiles or infra_mode == "split-cpu-gpu":
        parts: list[str] = []
        if infra_mode == "split-cpu-gpu":
            parts.append(
                "# === Split CPU / GPU Multi-Node Topology ===\n"
                "# Never hardcode localhost across distributed nodes; point to the remote host/IP.\n"
                "NODE_ROLE=app-cpu\n"
                "GPU_NODE_HOST=10.0.0.50\n"
                "GPU_WORKER_PORT=8081\n"
                "REMOTE_WORKER_URL=http://10.0.0.50:8081\n"
                "DB_NODE_HOST=10.0.0.40"
            )
        for prof in dotenv_profiles:
            frag = catalog_dir / "addons" / "dotenv" / f"{prof}.env.example"
            if frag.is_file():
                rendered = replace_tokens(frag.read_text(encoding="utf-8").strip(), tokens)
                if infra_mode == "split-cpu-gpu" and prof == "database-redis":
                    rendered += "\n# Point DATABASE_URL to ${DB_NODE_HOST} in your local .env (never localhost)."
                parts.append(rendered)
        if parts:
            (root / ".env.example").write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def configure_workflows(root: Path, stack_dir: Path) -> None:
    wf_dir = root / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    tpl_ci = wf_dir / "template-ci.yml"
    if tpl_ci.is_file():
        tpl_ci.unlink()
    stack_ci = stack_dir / "workflows" / "ci.yml"
    if stack_ci.is_file():
        shutil.copy2(stack_ci, wf_dir / "ci.yml")


def resolve_addons_flags(
    manifest: dict[str, object],
    args: argparse.Namespace,
    scope_list: list[str],
    infra_mode: str,
) -> tuple[bool, list[str], bool]:
    default_docker = bool(manifest.get("addons", {}).get("docker", False))  # type: ignore[union-attr]
    default_dotenv = list(manifest.get("addons", {}).get("dotenv_profiles", []))  # type: ignore[union-attr]
    use_docker = default_docker or infra_mode == "split-cpu-gpu"
    dotenv_profiles = list(default_dotenv)

    if scope_list:
        if any(s in scope_list for s in ("api", "db", "ml-gpu")) and "core" not in dotenv_profiles:
            dotenv_profiles.insert(0, "core")
        if "api" in scope_list and "web-api" not in dotenv_profiles:
            dotenv_profiles.append("web-api")
        if "db" in scope_list and "database-redis" not in dotenv_profiles:
            dotenv_profiles.append("database-redis")
        if "ml-gpu" in scope_list and "gpu-ml" not in dotenv_profiles:
            dotenv_profiles.append("gpu-ml")

    with_benchmarks = bool(args.with_benchmarks or args.stack == "ml-gpu" or "ml-gpu" in scope_list)

    if args.addons:
        for raw_item in [x.strip() for x in args.addons.split(",") if x.strip()]:
            if raw_item == "docker":
                use_docker = True
            elif raw_item in {"no-docker", "none"}:
                use_docker = False
            elif raw_item in {"benchmarks", "benchmarks-doc"}:
                with_benchmarks = True
            elif raw_item.startswith("dotenv:"):
                val = raw_item.split(":", 1)[1].strip()
                dotenv_profiles = [] if val == "none" else [p for p in val.split("+") if p]
            elif raw_item in {"core", "web-api", "database-redis", "gpu-ml"} and raw_item not in dotenv_profiles:
                dotenv_profiles.append(raw_item)

    if args.docker is not None:
        use_docker = args.docker
    if args.dotenv is not None:
        dotenv_profiles = (
            []
            if args.dotenv.strip().lower() in {"", "none"}
            else [p.strip() for p in args.dotenv.split(",") if p.strip()]
        )
    return use_docker, dotenv_profiles, with_benchmarks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize a Zero-Noise Gemini/Antigravity project from template.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 init_project.py\n"
            "  python3 init_project.py --kind game --dim 2d --name arcade-quest --yes\n"
            "  python3 init_project.py --kind app-system --scope frontend --ui-style minimalist --ui-tone dark --name studio-ui --yes\n"
            "  python3 init_project.py --kind app-system --scope frontend,api,db,ml-gpu --infra split-cpu-gpu --ui-style fluid --name dist-app --yes"
        ),
    )
    parser.add_argument("--root", default=".", help="Workspace root to initialize (default: .)")
    parser.add_argument("--kind", "--nature", dest="kind", choices=["app-system", "library-cli", "game"], help="High-level project nature (alias: --nature)")
    parser.add_argument("--scope", help="Comma-separated modular scope (frontend,api,db,ml-gpu,profiling)")
    parser.add_argument("--infra", choices=list(INFRA_MODES), help="Infrastructure topology: single-node | split-cpu-gpu (default: single-node)")
    parser.add_argument("--stack", help="Stack name under _catalog/stacks/")
    parser.add_argument("--from-spec", help="Read checked options from SPEC.md (e.g. _reference/SPEC.md)")
    parser.add_argument("--name", help="Project name (default: root directory name)")
    parser.add_argument("--description", default="Modular software project built on the Antigravity Zero-Noise core.")
    parser.add_argument("--dim", choices=["2d", "3d"], help="Game dimension for gamedev-godot (default: 2d)")
    parser.add_argument("--code-style", choices=list(CODE_PHILOSOPHY_RULES), help="Coding philosophy: minimal-yagni | clean-ddd | functional-dod (default: minimal-yagni)")
    parser.add_argument("--ui-style", "--ui-profile", dest="ui_profile", choices=list(UI_STYLES), help="Frontend aesthetic preset (default: minimalist)")
    parser.add_argument("--ui-tone", choices=["dark", "light"], help="Minimalist palette polarity: dark | light (default: dark)")
    parser.add_argument("--with-dataviz", action="store_true", help="Include frontend-dataviz-and-charts skill")
    parser.add_argument("--with-brand-logo", action="store_true", help="Include brand-logo-and-svg-forge skill")
    parser.add_argument("--with-profiling", action="store_true", help="Include runtime-profiling-and-observability skill")
    parser.add_argument("--agents", choices=["all", "antigravity", "gemini", "claude"], default="all", help="Agent hosts to wire (default: all)")
    parser.add_argument("--features", help="Comma-separated optional features (e.g. pixel-art,rig-fx,autotile,sfx,dataviz,brand-logo,db,api,profiling)")
    parser.add_argument("--skills", help="Explicit comma-separated skill names/ids overriding manifest defaults")
    parser.add_argument("--addons", help="Comma-separated addons (docker, no-docker, dotenv:core+web-api, benchmarks)")
    parser.add_argument("--docker", dest="docker", action="store_true", default=None, help="Enable Docker addon")
    parser.add_argument("--no-docker", dest="docker", action="store_false", help="Disable Docker addon")
    parser.add_argument("--dotenv", help="Comma-separated dotenv profiles or 'none'")
    parser.add_argument("--doc-level", choices=["minimal", "standard", "full"], help="Adaptive documentation preset shortcut (default: standard; minimal for CLI, full for ml-gpu)")
    parser.add_argument("--docs", help="Comma-separated optional docs (user-guide,adr,agent-guide,benchmarks,es or legacy en|bilingual)")
    parser.add_argument("--with-benchmarks", action="store_true", help="Include docs/BENCHMARKS.md")
    parser.add_argument("--with-meta-skills", action="store_true", help="Retain skill-authoring, skill-radar & reference-harvest meta-skills")
    parser.add_argument("--list-catalog", action="store_true", help="Print _catalog/catalog.json skill index and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without modifying files")
    parser.add_argument("--keep-catalog", action="store_true", help="Keep _catalog/, TEMPLATE_GUIDE.md, and init_project.py")
    parser.add_argument("--yes", "-y", action="store_true", help="Non-interactive mode using manifest defaults")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    catalog_dir = root / "_catalog"
    if not catalog_dir.is_dir():
        print(f"Error: `_catalog/` directory not found under {root}", file=sys.stderr)
        return 1

    if args.list_catalog:
        cat_file = catalog_dir / "catalog.json"
        print(cat_file.read_text(encoding="utf-8") if cat_file.is_file() else "{}")
        return 0

    spec_defaults = parse_spec_defaults(root / args.from_spec) if args.from_spec else {}
    if not args.code_style and "code_style" in spec_defaults:
        args.code_style = str(spec_defaults["code_style"])
    if not args.kind and "kind" in spec_defaults:
        args.kind = str(spec_defaults["kind"])
    if not args.scope and "scope" in spec_defaults:
        args.scope = str(spec_defaults["scope"])
    if not args.infra and "infra" in spec_defaults:
        args.infra = str(spec_defaults["infra"])
    if not args.stack and "stack" in spec_defaults:
        args.stack = str(spec_defaults["stack"])
    if not args.ui_profile and "ui_profile" in spec_defaults:
        args.ui_profile = str(spec_defaults["ui_profile"])
    if not args.ui_tone and "ui_tone" in spec_defaults:
        args.ui_tone = str(spec_defaults["ui_tone"])
    if not args.with_dataviz and spec_defaults.get("with_dataviz"):
        args.with_dataviz = True
    if not args.with_brand_logo and spec_defaults.get("with_brand_logo"):
        args.with_brand_logo = True
    if not args.dim and "dim" in spec_defaults:
        args.dim = str(spec_defaults["dim"])
    if not args.doc_level and "doc_level" in spec_defaults:
        args.doc_level = str(spec_defaults["doc_level"])
    if not args.with_benchmarks and spec_defaults.get("with_benchmarks"):
        args.with_benchmarks = True
    if args.docker is None and spec_defaults.get("docker"):
        args.docker = True

    spec_doc_items: list[str] = list(spec_defaults.get("docs_items", []))  # type: ignore[arg-type]

    features = [x.strip() for x in args.features.split(",") if x.strip()] if args.features else []
    if args.with_dataviz and "dataviz" not in features:
        features.append("dataviz")
    if args.with_brand_logo and "brand-logo" not in features:
        features.append("brand-logo")
    if args.with_profiling and "profiling" not in features:
        features.append("profiling")

    # Step 1: Coding Philosophy
    code_style = args.code_style or (
        "minimal-yagni"
        if (args.yes or args.dry_run)
        else prompt_choice(
            "Step 1. Coding philosophy",
            list(CODE_PHILOSOPHY_RULES),
            "minimal-yagni",
            INTERACTIVE_HINTS["code_style"],
        )
    )

    # Step 2: Project Nature, Modular Scope & Infrastructure Topology
    stacks = available_stacks(catalog_dir)
    if not args.stack and not args.scope and not args.kind:
        if args.yes or args.dry_run:
            print("Error: `--stack`, `--scope`, `--kind`, or `--from-spec` is required in `--yes` / `--dry-run` mode.", file=sys.stderr)
            return 1
        args.kind = prompt_choice(
            "Step 2a. Project nature",
            ["app-system", "library-cli", "game"],
            "app-system",
            INTERACTIVE_HINTS["kind"],
        )
        if args.kind == "app-system":
            picked_scopes = prompt_multi_choice(
                "Step 2b. Modular scope components",
                list(VALID_SCOPES),
                ["api", "db"],
                INTERACTIVE_HINTS["scope"],
            )
            args.scope = ",".join(picked_scopes)

    kind, stack_name, scope_list, scope_explicit = resolve_stack_and_scope(args.kind, args.stack, args.scope, features)
    if not stack_name or stack_name not in stacks:
        print(f"Error: Unknown or unresolved stack `{stack_name}`. Available: {stacks}", file=sys.stderr)
        return 1

    infra_mode = args.infra or (
        "single-node"
        if (args.yes or args.dry_run or stack_name == "gamedev-godot")
        else prompt_choice(
            "Step 2c. Infrastructure topology",
            list(INFRA_MODES),
            "single-node",
            INTERACTIVE_HINTS["infra"],
        )
    )

    stack_dir = catalog_dir / "stacks" / stack_name
    manifest = json.loads((stack_dir / "stack.json").read_text(encoding="utf-8"))

    default_name = root.name
    project_name = args.name or (
        default_name if (args.yes or args.dry_run) else (input(f"Project name [{default_name}]: ").strip() or default_name)
    )
    package_name = slugify_package(project_name)

    # Step 3: Frontend Design Options (Only when frontend is in scope or stack supports it)
    has_frontend = ("frontend" in scope_list) or (not scope_explicit and bool(manifest.get("supports_ui_profile")))
    ui_profile: str | None = None
    ui_tone: str | None = args.ui_tone
    if has_frontend:
        ui_profile = args.ui_profile or (
            "minimalist"
            if (args.yes or args.dry_run)
            else prompt_choice(
                "Step 3a. Frontend design style",
                list(UI_STYLES),
                "minimalist",
                INTERACTIVE_HINTS["ui_style"],
            )
        )
        if ui_profile == "minimalist" and not ui_tone and not (args.yes or args.dry_run):
            ui_tone = prompt_choice(
                "Step 3b. Minimalist palette tone",
                ["dark", "light"],
                "dark",
                INTERACTIVE_HINTS["ui_tone"],
            )
        if not (args.yes or args.dry_run) and not args.with_dataviz and not args.with_brand_logo:
            default_ui_addons = [a for a in ("dataviz", "brand-logo") if a in features]
            picked_ui_addons = prompt_multi_choice(
                "Step 3c. Optional frontend addons",
                ["dataviz", "brand-logo"],
                default_ui_addons,
                INTERACTIVE_HINTS["ui_addons"],
            )
            for addon in picked_ui_addons:
                if addon not in features:
                    features.append(addon)

    # Step 4: Game Dimension (Only when game / gamedev-godot, 2D default fast path)
    dim: str | None = None
    if manifest.get("supports_dimension"):
        dim = args.dim or (
            str(manifest.get("default_dimension", "2d"))
            if (args.yes or args.dry_run)
            else prompt_choice(
                "Step 4. Game dimension (2D default fast path; strictly excludes 3D skills)",
                ["2d", "3d"],
                "2d",
                INTERACTIVE_HINTS["dim"],
            )
        )

    use_docker, dotenv_profiles, with_benchmarks = resolve_addons_flags(manifest, args, scope_list, infra_mode)
    if args.docker is None and not args.addons and not (args.yes or args.dry_run) and stack_name != "gamedev-godot" and infra_mode == "single-node":
        use_docker = prompt_yes_no("Enable Docker & Compose addon?", use_docker)

    # Step 5: Documentation Footprint (README + ARCHITECTURE always mandatory)
    default_doc_lvl = str(manifest.get("default_doc_level", "standard"))
    if args.docs and not args.doc_level and not any(x in args.docs for x in ("en", "bilingual")):
        doc_level = "minimal"
    else:
        doc_level = args.doc_level or (
            default_doc_lvl
            if (args.yes or args.dry_run)
            else prompt_choice(
                "Step 5a. Base documentation tier (README + ARCHITECTURE always included)",
                ["minimal", "standard", "full"],
                default_doc_lvl,
                INTERACTIVE_HINTS["doc_level"],
            )
        )

    if not args.docs and not spec_doc_items and not (args.yes or args.dry_run) and not args.doc_level:
        tier_defaults = {
            "minimal": [],
            "standard": ["user-guide", "adr"],
            "full": ["user-guide", "adr", "benchmarks", "es"],
        }
        picked_docs = prompt_multi_choice(
            "Step 5b. Optional documentation files",
            list(DOC_OPTION_KEYS),
            tier_defaults.get(doc_level, ["user-guide", "adr"]),
            INTERACTIVE_HINTS["doc_items"],
        )
        args.docs = ",".join(picked_docs) if picked_docs else "minimal"

    doc_items, doc_level = resolve_doc_selection(doc_level, args.docs, spec_doc_items, with_benchmarks, stack_name)
    docs_mode = "bilingual" if "es" in doc_items else "en"
    with_benchmarks = "benchmarks" in doc_items

    skills_rel = resolve_skills_list(
        catalog_dir,
        manifest,
        stack_name,
        scope_list,
        scope_explicit,
        infra_mode,
        use_docker,
        ui_profile,
        dim,
        features,
        args.skills,
        args.with_meta_skills,
        args.with_profiling,
    )

    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "project": project_name,
                    "package": package_name,
                    "code_style": code_style,
                    "kind": kind,
                    "stack": stack_name,
                    "scope": scope_list,
                    "infra": infra_mode,
                    "dimension": dim,
                    "ui_style": ui_profile,
                    "ui_profile": ui_profile,
                    "ui_tone": ui_tone,
                    "agents": args.agents,
                    "features": features,
                    "docker": use_docker,
                    "dotenv_profiles": dotenv_profiles,
                    "doc_level": doc_level,
                    "docs": docs_mode,
                    "doc_items": sorted(doc_items),
                    "with_benchmarks": with_benchmarks,
                    "skills": [Path(s).name for s in skills_rel],
                },
                indent=2,
            )
        )
        return 0

    project_slug = re.sub(r"[^a-z0-9]+", "-", project_name.lower()).strip("-") or package_name.replace("_", "-")
    tokens = {
        "STACK_NAME": stack_name,
        "PROJECT_NAME": project_name,
        "PROJECT_SLUG": project_slug,
        "PACKAGE_NAME": package_name,
        "PROJECT_DESCRIPTION": args.description,
        "ONE_SENTENCE_PROJECT_PITCH": args.description,
        "PRIMARY_CODE_DIR": str(manifest.get("primary_code_dir", "src/")),
        "PREREQUISITE_1": str(manifest.get("prerequisite", "Python 3.12+ or Node.js 22+")),
    }

    copy_stack_template(stack_dir / "template", root, tokens)
    configure_addons(
        root,
        catalog_dir,
        stack_dir,
        tokens,
        use_docker,
        dotenv_profiles,
        infra_mode=infra_mode,
        scope_list=scope_list,
    )
    installed_skills = inject_skills(root, catalog_dir, skills_rel)
    inject_rules_and_hooks(
        root,
        catalog_dir,
        manifest,
        use_docker,
        code_style=code_style,
        ui_style=ui_profile,
        ui_tone=ui_tone,
        infra_mode=infra_mode,
        doc_level=doc_level,
        agents_mode=args.agents,
        project_name=project_name,
    )
    configure_workflows(root, stack_dir)
    update_gitignore(root, stack_dir)
    update_docs(
        root,
        catalog_dir,
        tokens,
        use_docker,
        dotenv_profiles,
        doc_level,
        doc_items,
        code_style=code_style,
        infra_mode=infra_mode,
        scope_list=scope_list,
        installed_skills=installed_skills,
    )

    if not args.keep_catalog:
        shutil.rmtree(catalog_dir)
        evals_dir = root / "evals"
        if evals_dir.is_dir():
            shutil.rmtree(evals_dir)
        brand_assets_dir = root / "docs" / "assets" / "brand"
        if brand_assets_dir.is_dir():
            shutil.rmtree(brand_assets_dir)
        assets_dir = root / "docs" / "assets"
        if assets_dir.is_dir() and not any(assets_dir.iterdir()):
            assets_dir.rmdir()
        for cleanup_rel in ("TEMPLATE_GUIDE.md", "init_project.py", "tests/test_init_project.py"):
            p = root / cleanup_rel
            if p.is_file():
                p.unlink()
        tests_dir = root / "tests"
        if tests_dir.is_dir() and not any(tests_dir.iterdir()):
            tests_dir.rmdir()

    print(
        f"\nInitialized `{project_name}` (code_style={code_style}, stack={stack_name}, scope={','.join(scope_list) or 'core'}, "
        f"infra={infra_mode}, dim={dim or 'n/a'}, ui_style={ui_profile or 'n/a'}, docs={sorted(doc_items)}, agents={args.agents})"
    )
    print(f"Skills injected (1-level under .agents/skills/): {len(installed_skills)} -> {', '.join(installed_skills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
