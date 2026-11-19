# Project Specification Contract (SPEC)

> Describe your intent in plain language (English or Spanish) and check (`[x]`) the 5 modular setup steps below. Once ready, run `python3 init_project.py --from-spec _reference/SPEC.md` or tell the agent:
> **"Interview me or read `_reference/SPEC.md` and bootstrap the project architecture, rules, skills, and starter modules."**

## 1. Intent & Problem Statement (Plain Language)

- **What I want to build**: {{Describe in 2-5 lines what this project does, who uses it, and the core problem it solves.}}
- **Success Criteria (What "Done" Looks Like)**:
  - {{Concrete outcome or metric 1}}
  - {{Concrete outcome or metric 2}}

## 2. Modular 5-Step Project Setup (`init_project.py --from-spec`)

### Step 1: Coding Philosophy (`--code-style`)
- [ ] `minimal-yagni` (Default — Ponytail 7-rung ladder: simplest working solution, stdlib first, minimal dependencies & LOC)
- [ ] `clean-ddd` (Clean Architecture, DDD & Deep Modules: pure domain core, inward dependency flow, explicit ports/DTOs)
- [ ] `functional-dod` (Functional & Data-Oriented Design: stateless pipelines, immutable data, explicit idempotent contracts)

### Step 2: Project Nature (`--kind`), Modular Scope (`--scope`) & Infrastructure Topology (`--infra`)
- **Base Nature (`--kind` / `--stack`):**
  - [ ] `app-system` (Application / Service — compose modular scope checkboxes below)
  - [ ] `library-cli` (`python-cli` — installable CLI tool or library, zero web/DB/game bloat)
  - [ ] `gamedev-godot` (`--kind game` — Godot 4.x + C# .NET 8+ game project)
- **Modular Scope (`--scope`, check all that apply for `app-system`):**
  - [ ] `frontend` (Web UI / SaaS / Landing — injects UI skeleton + frontend quality/lighthouse/style skills)
  - [ ] `api` (Backend REST/API layer — injects API skeleton + `.env` web-api + `api-openapi-contract-gate` & backend gates)
  - [ ] `db` (Database & Cache — injects `.env` database-redis + `db-migration-and-schema-gate` for SQL/Alembic/Drizzle)
  - [ ] `ml-gpu` (ML / GPU Workload — injects portable `device.py` + `.env` gpu-ml + `ml-gpu-workload-harness` & `runtime-profiling-and-observability`)
  - [ ] `profiling` (Opt-in runtime p50/p95 latency, `cProfile`/`tracemalloc` & structured log gate via `runtime-profiling-and-observability`)
- **Legacy Stack Presets (optional shortcut if not using `--scope` above):**
  - [ ] `web-frontend` | [ ] `python-backend` | [ ] `multi-module` | [ ] `ml-gpu`
- **Infrastructure Topology (`--infra`):**
  - [ ] `single-node` (Default — everything runs on one development/host machine)
  - [ ] `split-cpu-gpu` (Distributed across machines: CPU laptop/API node + remote GPU worker / DB node; emits multi-profile `compose.yaml`, `REMOTE_WORKER_URL`/`GPU_NODE_HOST` in `.env.example`, and forbids hardcoded cross-node `localhost`)

### Step 3: Frontend Design Options (Only if `frontend` is in scope)
- **Aesthetic Preset (`--ui-style`):**
  - [ ] `minimalist` (Linear / Apple / Retriever 4-Phase Workflow: 4-6 word copy filter, Neo-Grotesque `-0.03em` + uppercase Mono `+0.08em`, 2-3% dot texture, 40/60 showcase, 150-220ms ease-out)
  - [ ] `neobrutalist` (Gumroad / Figma: bold dark borders, 0px hard offset shadows, high-contrast surfaces)
  - [ ] `bento` (Apple WWDC / Framer: modular grid cards, smooth radii, layered subtle surfaces)
  - [ ] `glassmorphic` (visionOS / Raycast: translucent panels, controlled `backdrop-blur`, 1px light borders)
  - [ ] `enterprise` (Stripe / Atlassian: dense data hierarchy, accessible tables, calm slate/navy palette)
  - [ ] `editorial` (Medium / Substack: serif display + sans body, narrow prose measure, reading rhythm)
  - [ ] `terminal` (Teenage Engineering / TUI: monospace UI, sharp 0-2px edges, 1px hairline grids)
  - [ ] `fluid` (Scrollytelling / Motion: creative BM25 design taxonomy via `ui-fluid-novel-system`)
- **Minimalist Polarity (`--ui-tone`, when `minimalist` is selected):**
  - [ ] `dark` (Retriever deep charcoal `#141517` + `#1C1E21` elevated surface)
  - [ ] `light` (Warm bone `#F7F6F2` + `#FFFFFF` elevated surface)
- **Optional Frontend Addons:**
  - [ ] `dataviz` (`--with-dataviz` -> `frontend-dataviz-and-charts`)
  - [ ] `brand-logo` (`--with-brand-logo` -> `brand-logo-and-svg-forge`)

### Step 4: Game Dimension (Only if `game` / `gamedev-godot` is selected)
- [ ] `2d` (Default fast path — pixel art, SVG bone rigs, Wang-16 autotiles, parallax & WAV SFX; strictly excludes 3D skills)
- [ ] `3d` (GLB/glTF 3D mesh/rig QA & WAV SFX; excludes 2D pixel/tile generators)

### Step 5: Documentation Footprint (`--docs` / `--doc-level`)
- **Always Included (Mandatory Core):** `README.md`, `docs/ARCHITECTURE.md` (live `ARCH_GRAPH`), and root `AGENTS.md`.
- **Selectable Optional Documents (`--docs user-guide,adr,agent-guide,benchmarks,es`):**
  - [ ] `user-guide` (`docs/USER_GUIDE.md` — setup, CLI/API/container usage & troubleshooting)
  - [ ] `adr` (`docs/adr/` — Architecture Decision Records)
  - [ ] `agent-guide` (`docs/AGENT_GUIDE.md` — extended agent workflow, active skill inventory & verification playbook)
  - [ ] `benchmarks` (`docs/BENCHMARKS.md` — latency/memory/GPU evaluation baselines)
  - [ ] `es` (`docs/README.es.md` — bilingual Spanish README)
- **Preset Shortcuts (`--doc-level`):**
  - [ ] `minimal` (Mandatory core only)
  - [ ] `standard` (Core + `user-guide` + `adr`)
  - [ ] `full` (Core + `user-guide` + `adr` + `benchmarks` + `es`)
- **Container Addon Override:**
  - [ ] `docker` (Force Docker & Compose even on single-node CLI/web projects)

## 3. Scope & Non-Goals

### In Scope (MVP)
- {{Core capability 1}}
- {{Core capability 2}}

### Out of Scope (Strict Non-Goals)
- {{Feature or over-engineering the agent MUST NOT add}}

## 4. Tech Stack, Contracts & Constraints

- **Languages & Libraries**: `{{e.g., Python 3.12 + FastAPI / TypeScript + Astro / Godot 4 C#}}`
- **Forbidden Patterns**: `{{e.g., no ORM, no GDScript, no third-party telemetry}}`

## 5. Reference Material Inventory (`_reference/`)

| Path in `_reference/` | Purpose / What to Extract | What to Ignore |
| :--- | :--- | :--- |
| `_reference/repos/{{repo}}` | {{Run `repo_map.py --digest-reference` to extract only engines/contracts}} | {{Demo bloat / unrelated tests}} |
| `_reference/assets/{{file}}` | {{Wireframes, papers, PDF specs, spritesheets}} | {{Draft scratch notes}} |
