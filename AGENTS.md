# Antigravity Project Constitution (AGENTS.md)

<!-- TEMPLATE_BOOTSTRAP_INTERVIEW:START -->
## 0. Uninitialized Template Bot Mode (Conversational Bootstrap)

If `init_project.py` and `_catalog/` exist at the repository root and the user asks to start, configure, or plan a new project without having run `init_project.py` yet:
1. **Run the 5-Step Conversational Questionnaire** with the user in the chat:
   - **Step 1 (Coding Philosophy):** `minimal-yagni` (Ponytail 7-rung minimal) vs `clean-ddd` (Clean Architecture/DDD) vs `functional-dod` (Functional/DOD).
   - **Step 2 (Nature, Modular Scope & Infrastructure):** `app-system` (pick any of `frontend`, `api`, `db`, `ml-gpu`, `profiling`), `library-cli`, or `game`, plus topology `single-node` vs `split-cpu-gpu` (multi-machine CPU + remote GPU/DB).
   - **Step 3 (Frontend Options, if `frontend` in scope):** `--ui-style` (`minimalist`, `neobrutalist`, `bento`, `glassmorphic`, `enterprise`, `editorial`, `terminal`, `fluid`), `--ui-tone` (`dark` | `light` for `minimalist`), and optional `--with-dataviz` / `--with-brand-logo`.
   - **Step 4 (Game Dimension, if `game`):** `2d` (default fast path, zero 3D bloat) vs `3d`.
   - **Step 5 (Documentation Selection):** Mandatory `README.md` + `docs/ARCHITECTURE.md`, plus optional `user-guide`, `adr`, `agent-guide`, `benchmarks`, `es`.
2. **Persist & Execute:** Record the user's choices into `_reference/SPEC.md` and run `python3 init_project.py` with the corresponding CLI flags (`--code-style`, `--scope`, `--infra`, `--ui-style`, `--ui-tone`, `--dim`, `--docs`, `--yes`). `init_project.py` will automatically prune `_catalog/` and remove this Section 0 block.
<!-- TEMPLATE_BOOTSTRAP_INTERVIEW:END -->

## 1. Language & Communication Protocol (Bilingual Rule)

- **Repository Artifacts (100% Technical English)**: All source code, identifiers, comments, docstrings, Markdown documentation (`README.md`, `docs/**`, `AGENTS.md`, `_reference/SPEC.md`), Git branch names, commit messages, and PR descriptions MUST be written in clear, concise technical English.
- **Interactive Chat (User's Language — Spanish by Default)**: Always respond in the chat using the language the user speaks to you (Spanish by default) so architectural reasoning, trade-offs, and plans can be discussed naturally.

## 2. Zero-Duplication Documentation Contract (Artifact Roles)

Every Markdown file owns a strict, non-overlapping scope. Link to the canonical owner instead of repeating facts across files:

| Document | Canonical Scope (What It Owns) | Forbidden Content (Do Not Duplicate) |
| :--- | :--- | :--- |
| `_reference/SPEC.md` | Local pre-bootstrap contract: problem pitch, topology, non-goals, stack constraints, and `_reference/` inventory (gitignored in target projects). | Live runtime docs or post-bootstrap user guides. |
| `AGENTS.md` | Agent operational rules, language protocol, documentation ownership map, workflow gates, and local directory boundaries. | Human onboarding prose, tutorials, or setup guides. |
| `README.md` | Project pitch (1–3 sentences), prerequisites, universal quickstart (`make setup`, `make dev`, `make verify`), top-level layout, and links to `docs/`. | Detailed internal architecture diagrams (a 3-node high-level overview is allowed), full configuration tables, or agent rules. |
| `docs/ARCHITECTURE.md` | System boundaries, Mermaid diagrams (Context/Component & Sequence), directory topology, and strict module dependency rules. | Step-by-step installation commands, CLI flags, or `.env` reference tables. |
| `docs/USER_GUIDE.md` | Detailed configuration, execution modes, CLI/UI/API usage, verification commands, and troubleshooting (optional per setup). | Internal code structure, design rationale, or ADR history. |
| `docs/AGENT_GUIDE.md` | Extended agent workflow, active installed skill inventory, and verification playbook (optional per setup). | Human user tutorials or duplicate architecture diagrams. |
| `docs/BENCHMARKS.md` | Evaluation methodology, metrics definitions, latency/memory/GPU baselines, and recorded runs (optional per setup). | General installation instructions or routine changelog notes. |
| `docs/adr/NNNN-*.md` | Immutable Architecture Decision Records (Context -> Decision -> Consequences) (optional per setup). | Routine changelog entries or mutable status checklists. |
| `CHANGELOG.md` | Automated release history managed exclusively by `release-please`. | Manual edits or unstructured development notes. |

## 3. Mandatory Engineering Workflow

1. **Context First**: Read `_reference/SPEC.md` and `docs/ARCHITECTURE.md` before proposing structural changes. Treat `_reference/` as strictly read-only inspiration.
2. **Phased Planning for Complex Work**: When a request spans multiple modules, introduces new architecture, or requires a large refactor, produce a **phased implementation plan** first and wait for user approval before writing production code.
3. **Topology & Zero Root Clutter**: Never place loose source files or scripts at the repository root. Respect the active project topology (`src/+tests/`, `backend/+frontend/`, `scenes/+scripts/`, etc.) and any local `AGENTS.md` inside subdirectories.
4. **Branching & Detailed Conventional Commits**:
   - Create dedicated branches (`feat/<slug>`, `fix/<slug>`, `refactor/<slug>`, `docs/<slug>`) for multi-step or extensive features rather than committing directly to `main`.
   - Format commits as `<type>(<scope>): <imperative summary>` (`<= 69` chars target, hard cap 72) followed by a detailed bulleted body explaining *what* changed and *why*.
5. **Verification Gate**: Always run `make verify` (`make lint` + `make test`) and confirm all checks pass before declaring any implementation complete.
