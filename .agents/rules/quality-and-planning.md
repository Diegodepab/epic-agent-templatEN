---
trigger: always_on
---

# Universal Code Quality & Phased Planning Rules

## 1. Static-Analyzer Maintainability Standards (SonarQube / CodeClimate Grade A)

- **File Length**: Keep imperative source code files under **350 lines** (excluding declarative configs/schemas, database migrations, `.tscn` scenes, shaders, or static data dictionaries). Split growing imperative modules into cohesive submodules before exceeding this threshold.
- **Function Size & Complexity**: Keep functions/methods under **50 lines**, maximum **3 indentation levels**, and cognitive complexity <= 15. Use early-return guard clauses to flatten nested branches.
- **Single Responsibility & DRY**: Each module and function must have one clear responsibility. Eliminate duplicated logic by extracting pure helpers, without introducing premature abstractions.

## 2. Zero Fake Logic & Zero Silent Failures

- **No Production Placeholders**: Strictly forbidden outside test directories: hardcoded mock return payloads, artificial delays (`sleep` / `setTimeout`), empty stubs (`pass` / `{}`), or unresolved `TODO`, `FIXME`, `HACK`, `PLACEHOLDER`, and `STUB` comments.
- **No Silent Error Swallowing**: Never ignore errors or write empty catch/except blocks (`except: pass`, `except Exception: pass`, `catch (e) {}`). Always catch specific error types, log structured context, and propagate or return explicit typed errors.

## 3. Phased Execution & Safe Refactoring

- **Plan Before Multi-File Edits**: For complex features, new architecture, or cross-module refactors, present a phased implementation plan and wait for user confirmation before editing production code.
- **Preserve Public Contracts**: When refactoring existing modules, preserve public signatures and re-exports until callers and tests are migrated. Run `make verify` after each phase.
