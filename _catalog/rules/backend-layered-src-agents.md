# Source Code Architecture & Quality Rules (Backend Service Layering)

## 1. Modular Layout & Thin Entrypoints
- Keep all production code inside cohesive domain/layer modules (`core/`, `domain/`, `services/`, `api/` or `cli/`, `infra/`).
- Keep entrypoints (`main.py`, `serve.py`, `index.ts`) as thin coordinators (<150 lines) that wire config, logging, and routers/commands without business logic.

## 2. Unidirectional Dependency Rule
- `domain/` (entities, value objects, pure business rules, interfaces): must NEVER import from `api/`, `cli/`, or `infra/`.
- `services/` (use-case orchestration): depends on `domain/` and `core/`; interacts with I/O only through abstractions.
- `infra/` (DB adapters, HTTP clients, filesystem, ML/GPU loaders): implements `domain/` interfaces.
- `api/` / `cli/` (controllers, routers, handlers): thin boundary only. Validate input schemas, call `services/`, return typed DTOs. Never run raw SQL, direct disk I/O, or blocking CPU compute inside route handlers.

## 3. Complexity & Size Thresholds (SonarQube / CodeClimate Grade A)
- **File size**: max **350 lines** per file. Split growing modules into focused submodules.
- **Function size**: max **50 lines** per function/method.
- **Nesting & Cognitive Complexity**: max **3 indentation levels** and cognitive complexity <= 15. Use early-return guard clauses and extract pure helper functions.

## 4. Zero Fake Logic & Zero Silent Failures
- Strictly forbidden outside tests: hardcoded mock payloads, artificial sleeps (`time.sleep`, `setTimeout`), empty stubs (`pass`), or unresolved `TODO`/`FIXME`/`HACK`/`PLACEHOLDER` comments.
- Strictly forbidden: bare `except:` or `except Exception: pass` or empty `catch {}`. Catch specific exceptions, log with structured context, and raise or translate to explicit domain/HTTP errors.

## 5. Strict Data Contracts
- Never use raw untyped dicts (`dict`, `Dict[str, Any]`, `any`) as service or API input/output signatures. Enforce typed schemas (`Pydantic`, `dataclass`, `Zod`, `struct`).
