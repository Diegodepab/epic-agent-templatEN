# Template Usage Guide (`init_project.py` & 33-Skill Catalog)

> Visible in the public template repository on GitHub and **automatically deleted** by `init_project.py` (alongside `_catalog/`, `evals/`, `docs/assets/brand/`, `tests/test_init_project.py`, and `init_project.py`) once a child project is initialized.

## 1. Initializer CLI Flags (`init_project.py`)

> **Fast Start (<1 min):** Click **Use this template** (or `git clone <repo-url> my-project && cd my-project`). To use **Bot Mode**, open the folder in Antigravity and ask: *"Interview me to bootstrap this project"* (Section 0 of `AGENTS.md` is auto-removed after init). Or initialize directly via CLI below:

```bash
# Interactive 5-step questionnaire
python3 init_project.py

# Initialize from checked boxes in _reference/SPEC.md
python3 init_project.py --from-spec _reference/SPEC.md --name my-app --yes

# Web app with Clean/DDD coding rules + Neobrutalist UI preset
python3 init_project.py --code-style clean-ddd --stack web-frontend --ui-style neobrutalist --name studio-ui --yes

# 2D Godot C# game (strictly excludes 3D skills, web, and Docker)
python3 init_project.py --stack gamedev-godot --dim 2d --name arcade-quest --yes

# Minimal Python CLI (README.md + docs/ARCHITECTURE.md only, zero bloat)
python3 init_project.py --stack python-cli --name fasttool --doc-level minimal --yes

# Inspect machine-readable catalog for agent-guided selection
python3 init_project.py --list-catalog
```

| Flag | Values / Default | Purpose |
| :--- | :--- | :--- |
| `--code-style` | `minimal-yagni` (default) \| `clean-ddd` \| `functional-dod` | Injects `.agents/rules/code-philosophy.md` (Step 1) |
| `--kind` (`--nature`) | `app-system` \| `library-cli` \| `game` | High-level project nature when composing via `--scope` (Step 2a) |
| `--scope` | Comma-separated: `frontend,api,db,ml-gpu,profiling` | Composes exact skills, `.env.example`, and `device.py` per active area (`db` -> `db-migration-and-schema-gate`, `api` -> `api-openapi-contract-gate`) (Step 2b) |
| `--infra` | `single-node` (default) \| `split-cpu-gpu` | Multi-machine topology emitting `app-cpu`/`db`/`gpu-worker` Compose profiles, `REMOTE_WORKER_URL`, and `.agents/rules/infra-topology.md` (Step 2c) |
| `--stack` | `web-frontend`, `python-cli`, `python-backend`, `multi-module`, `ml-gpu`, `gamedev-godot` | Selects stack manifest under `_catalog/stacks/<stack>/stack.json` |
| `--from-spec` | e.g. `_reference/SPEC.md` | Parses `[x]` checkboxes across all 5 setup steps |
| `--name` / `--description` | Default: folder name | Sets `{{PROJECT_NAME}}`, `{{PACKAGE_NAME}}`, and project pitch |
| `--dim` | `2d` (default) \| `3d` | Game dimension for `gamedev-godot` (`2d` strictly blocks 3D skills) (Step 4) |
| `--ui-style` (`--ui-profile`) | `minimalist` (default), `neobrutalist`, `bento`, `glassmorphic`, `enterprise`, `editorial`, `terminal`, `fluid` | Selects aesthetic tokens/lint (`ui-design-tokens-and-presets` or `ui-fluid-novel-system`), writes `.agents/rules/ui-aesthetic.md`, and initializes `.agents/ui-contract.json` (Step 3a) |
| `--ui-tone` | `dark` \| `light` | Polarity for `minimalist` (`dark` Retriever charcoal `#141517` or `light` bone `#F7F6F2`); runs `preset_tokens.py` on init (Step 3b) |
| `--with-dataviz` / `--with-brand-logo` / `--with-profiling` | Flags | Opt-in toggles for `frontend-dataviz-and-charts`, `brand-logo-and-svg-forge`, and `runtime-profiling-and-observability` |
| `--docs` | `user-guide,adr,agent-guide,benchmarks,es` (or `en` \| `bilingual`) | Granular optional documentation selection on top of mandatory `README.md` + `docs/ARCHITECTURE.md` (Step 5) |
| `--doc-level` | `minimal` \| `standard` (default) \| `full` | Preset shortcuts for `--docs` and `.agents/rules/docs-discipline.md` |
| `--agents` | `all` (default) \| `antigravity` \| `gemini` \| `claude` | Emits hooks (`pre_tool_guard.py`), `.gemini/settings.json`, `.claude/settings.json`, symlinks, and `GEMINI.md`/`CLAUDE.md` |
| `--features` | e.g. `pixel-art,rig-fx,autotile,sfx,dataviz,brand-logo` | Cherry-picks optional art/audio/dataviz/logo features within the chosen stack |
| `--skills` | Comma-separated skill names or IDs | Overrides defaults for custom agent-guided selection from `_catalog/catalog.json` |
| `--addons` | `docker`, `no-docker`, `dotenv:core+web-api`, `benchmarks` | Declarative toggles for Docker, `.env.example`, and `docs/BENCHMARKS.md` |
| `--docker` / `--no-docker` | Boolean override | Enables or disables Dockerfile, `.dockerignore`, and `.make/docker.mk` |
| `--dotenv` | `none` or profile list | Overrides `.env.example` fragment assembly directly |
| `--with-benchmarks` | Flag | Adds `docs/BENCHMARKS.md` regardless of doc-level |
| `--with-meta-skills` | Flag | Retains `skill-authoring-and-updater`, `skill-radar-and-proposals`, and `reference-harvest-and-prune` |
| `--list-catalog` | Flag | Prints `_catalog/catalog.json` and exits |
| `--dry-run` | Flag | Prints planned configuration and skills JSON without touching disk |
| `--keep-catalog` | Flag | Preserves template scaffolding (debugging only) |
| `--yes`, `-y` | Flag | Non-interactive mode |

---

## 2. Gemini / Antigravity Skill Standard

Every skill in `_catalog/skills/` complies with `audit_skill.py --strict --verify-help`:
- **Third-person YAML `description`** with explicit `Use when ... Not for ...` boundaries for clean progressive disclosure.
- **`## Decision Tree`** inside `SKILL.md` for unambiguous routing.
- **Black-Box Scripts (`--help` first):** encourages running `--help` instead of wasting tokens reading script internals.
- **1-level workspace placement:** `.agents/skills/<skill-name>/SKILL.md` (mirrored to `.gemini/skills/` and `.claude/skills/` when `--agents all`).

---

## 3. Complete Catalog of the 33 Executable Skills

| # | Category | Skill (`name`) | Scope / Dim | Executable Engine (`scripts/`) | Concrete Output / Gate |
| :-: | :--- | :--- | :--- | :--- | :--- |
| 1 | `00-core` | `long-context-state-manager` | Universal (`any`) | `state_manager.py` | Bounded `.agents/current_state.md` (`<=80L`) + `state_history.jsonl` |
| 2 | `00-core` | `anti-laziness-and-evidence-verifier` | Universal (`any`) | `verify_completion.py` | AST No-Stubbing scanner (Py/TS/C# + `ast-grep`) + `--cmd` runner (`exit=0`) |
| 3 | `00-core` | `repo-map-and-context-pack` | Universal (`any`) | `repo_map.py` | AST/TS/C# symbol map (`.agents/REPO_MAP.md`) + `--digest-reference` |
| 4 | `00-core` | `architecture-knowledge-and-docs-sync` | Universal (`any`) | `sync_arch_graph.py`, `audit_docs_integrity.py` | Live `ARCH_GRAPH` Mermaid/table sync + `--check-drift` + doc integrity |
| 5 | `00-core` | `clean-code-and-architecture-gate` | Universal (`any`) | `detect_stack.py`, `scan_repo.py`, `map_structure.py`, `check_boundaries.py`, `check_compression.py`, `audit_shortcuts_and_lean.py` | Multi-language (21 langs) smells, cycles, dead code, DDD layers, `# shortcut:` ledger/Lean metrics & 14 classic books `.nano.md` |
| 6 | `00-core` | `systematic-debugging-and-rca` | Universal (`any`) | `triage_failure.py`, `fingerprint.py`, `find_polluter.py` | Stacktrace triage, failing-repro gate, fix-loop hashes & test polluter isolation |
| 7 | `00-core` | `skill-authoring-and-updater` | Meta (`opt-in`) | `audit_skill.py`, `scaffold_skill.py` | Enforces Gemini v2 `SKILL.md` + `--verify-help` (`--strict`) |
| 8 | `00-core` | `skill-radar-and-proposals` | Meta (`opt-in`) | `skill_radar.py` | Last-30-days velocity discovery + local reference matcher |
| 9 | `00-core` | `reference-harvest-and-prune` | Meta (`opt-in`) | `audit_reference_harvest.py` | Reconciles cloned reference repos (extracted vs pending vs bloat) + prune list |
| 10 | `github` | `git-commit-and-pr-gate` | Universal (`any`) | `commit_gate.py`, `verify-action-pins.sh` | `<=69`-char title + layered English body + SHA pinning + `prepush` |
| 11 | `frontend` | `frontend-quality-and-design-gate` | Scope `frontend` | `run_frontend_pipeline.py`, `anti_slop_scanner.py`, `icon_search.py`, `ts_diagnostic.py`, `i18n_checker.py`, `extract-colors.cjs`, `validate-tokens.cjs`, `sync-brand-to-tokens.cjs`, `html-token-validator.py` | Locks `.agents/ui-contract.json`, blocks UI emojis/slop & hardcoded colors, TS diagnostics, i18n checks & Phosphor icons |
| 12 | `frontend` | `frontend-lighthouse-and-design-audit` | Scope `frontend` | `design-audit.mjs`, `run_lighthouse_gate.sh`, `agentic-readiness-check.mjs`, `polish_audit.py`, `tastegate_audit.py`, `layout-audit.js`, `verify_agentic_web_readiness.py` | 6-viewport Playwright + Lighthouse `>=90` + LaunchGuard/TasteGate + WebMCP / `/llms.txt` / `ard.json` agentic audit |
| 13 | `frontend` | `ui-design-tokens-and-presets` | Web Presets | `preset_tokens.py`, `aesthetic_lint.py`, `physics_calculator.py`, `generate-tokens.cjs`, `tailwind_config_gen.py` | Aesthetic presets (`minimalist`, `neobrutalist`, `bento`, `glassmorphic`, `enterprise`, `editorial`, `terminal`, `fluid`), spring physics & W3C tokens |
| 14 | `frontend` | `ui-fluid-novel-system` | Web Fluid | `search.py`, `core.py`, `design_system.py` | BM25 taxonomy across 67+ styles & scroll choreography (exclusive with #13) |
| 15 | `frontend` | `frontend-dataviz-and-charts` | Opt-In (`dataviz`) | `chart_advisor.py` | Intent recommender + 21-type synonym search + SVG/G6 v5 audit |
| 16 | `frontend` | `brand-logo-and-svg-forge` | Opt-In (`brand-logo`) | `svg_audit.py`, `render_png.py`, `readme_lockup.py`, `export_variants.py`, `extract_mascot_png.py`, `concept_sheet.py`, `presentation_board.py`, `search_library.py` | Geometric SVG audit, Light/Dark README lockups, mascot PNG/`.ico` cutout, pattern catalog search & PWA pack |
| 17 | `backend` | `backend-quality-and-contracts` | Scope `api`/`db`/CLI | `quality_and_contracts.py` | Wraps `ruff`/`radon` + AST layers, `except: pass`, DTOs, N+1, SQL drops |
| 18 | `backend` | `backend-security-and-owasp-gate` | Scope `api`/`db`/CLI | `security_gate.py`, `dependency_scanner.py`, `injection_scanner.py`, `secrets_scanner.py`, `scope.py` | Redacted secrets, SQLi/XSS/SSRF injection & secret entropy scanners, file scope resolver, OWASP AST, deps/Dockerfiles + `bandit`/`semgrep` |
| 19 | `backend` | `api-openapi-contract-gate` | Scope `api` | `openapi_contract_gate.py` | OpenAPI 3.x/Swagger response schemas, list pagination & FastAPI/Flask/Express route parity |
| 20 | `backend` | `db-migration-and-schema-gate` | Scope `db` ONLY | `audit_sql_and_migrations.py`, `check_drizzle_migrations.py` | Blocks `DROP`/`TRUNCATE`, `NOT NULL` without `DEFAULT`, unindexed FKs, Alembic split heads & Drizzle conflicts |
| 21 | `testing` | `test-and-mutation-gate` | Web / Backend / CLI | `test_audit.py`, `with_server.py` | Ghost-test AST detector + `mutmut`/`stryker` wrapper + E2E server manager |
| 22 | `testing` | `runtime-profiling-and-observability` | Scope `ml-gpu`/`profiling` | `profile_and_observability_gate.py` | p50/p95 latency, `cProfile` hotspots, `tracemalloc` memory budgets & secret-in-log audit |
| 23 | `infra` | `docker-and-env-auditor` | Docker / `split-cpu-gpu` | `docker_env_linter.py` | Code <-> `.env.example` sync + `Dockerfile`/Compose + `hadolint` |
| 24 | `infra` | `ml-gpu-workload-harness` | Scope `ml-gpu` | `gpu_workload_auditor.py`, `gpu_health.sh`, `mem_monitor.sh` | Model weight ignore guard, GPU/VRAM & RSS telemetry scripts + AST-verified `cpu/mps/cuda` + `inference_mode()` |
| 25 | `gamedev` | `godot-architecture-and-static-audit` | Godot (`2d`, `3d`) | `check_godot_project.py`, `check_csharp_godot_architecture.py` | `res://` Linux case & `uid://` audit + C# `partial`, `-=`, pure `Domain/` |
| 26 | `gamedev` | `godot-scene-and-input-audit` | Godot (`2d`, `3d`) | `audit_scene_and_input.py` | Collision matrix, `_Process` physics, per-frame C# GC/LINQ/`GetNode` allocations, UI `focus_mode`, atomic saves |
| 27 | `gamedev` | `godot-headless-testing` | Godot (`2d`, `3d`) | `run_godot_tests.py` + `TestRunnerTemplate.cs` | `dotnet test` + headless `godot` reporting `PASS`/`FAIL`/`SKIP` truthfully |
| 28 | `gamedev` | `godot-2d-sprite-and-art-pipeline` | Godot (`2d`) | `soft_matte_keyer.py`, `audit_spritesheet_metrics.py`, `spritesheet_surgeon.py`, `godot_spriteframes_export.py` | Chroma keyer, sole-Y telemetry, Pillow/NumPy repair & `.tres`/`.tscn`/`.cs` export |
| 29 | `gamedev` | `godot-2d-pixel-art-forge` | Godot (`2d`) | `pixel_downscale_palette.py`, `render_pixelspec.py`, `pixel_qa.py` | CIELAB k-means 1x downscaler, PixelSpec renderer & onion-skin/L-corner QA |
| 30 | `gamedev` | `godot-2d-rig-and-fx-animator` | Godot (`2d`) | `rig_animate.py`, `svg_render.py`, `ambient_bake.py`, `fx_and_shader_kit.py`, `build_animation_clips.py`, `assemble_frames.py`, `forge_matte.py`, `fx_build.py`, `fx_verify.mjs`, `gait_loop.py` | Hierarchical SVG bone-rig IK, gait loops, ambient plate loops, VFX strips & verification, shaders & springs |
| 31 | `gamedev` | `godot-2d-autotile-and-parallax` | Godot (`2d`) | `autotile_seam_builder.py`, `autotile_build.py`, `layout_build.py`, `validate_layout.py`, `forge_nav.py`, `parallax_build.py`, `validate_parallax.py`, `export_godot.py`, `forge_schema.py` | Wang-16 tiles & tilemap builder, periodic parallax & validation, 2D layout validation, BFS nav reachability & Godot export |
| 32 | `gamedev` | `godot-procedural-audio-and-sfx` | Godot (`2d`, `3d`) | `synth_sfx.py` | Pure-NumPy DSP generator for peak-normalized 16-bit WAV SFX |
| 33 | `gamedev-3d` | `godot-3d-asset-and-rig-qa` | Godot (`3d` ONLY) | `audit_glb_assets.py` | GLB/glTF mesh, draw-call budget, texture & animation audit (never in 2D) |
