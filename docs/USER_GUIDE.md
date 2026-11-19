# User & Operations Guide

> Canonical owner of configuration, execution workflows, verification commands, and troubleshooting. For internal design and module boundaries, see [Architecture](ARCHITECTURE.md).

## 1. Environment Setup

Run the universal setup target to initialize local dependencies and Git hooks:

```bash
make setup
```

<!-- Optional addon configuration sections (e.g., Environment Variables table from _catalog/addons/dotenv/) are injected here when enabled -->

---

## 2. Running the Project

Use the standard `Makefile` interface to run and interact with the project:

| Command | Description |
| :--- | :--- |
| `make help` | List all available commands in this repository |
| `make setup` | Install dependencies and configure Git pre-commit hooks |
| `make dev` | Launch local development mode |
| `make lint` | Run static code analysis and formatting checks |
| `make format` | Auto-format source files and apply safe lint fixes |
| `make test` | Execute the automated test suite |
| `make verify` | Run the full quality gate (`lint` + `test`) |
| `make clean` | Remove temporary build, cache, and coverage artifacts |

<!-- Optional addon execution sections (e.g., Docker Compose profiles from _catalog/addons/docker/) are injected here when enabled -->

---

## 3. Usage Examples

```bash
# {{Replace with primary CLI command, local URL, or engine launch instruction}}
```

---

## 4. Troubleshooting

| Symptom / Error | Likely Cause | Resolution |
| :--- | :--- | :--- |
| `make setup` fails on hook installation | `pre-commit` binary not installed on host | Install `pre-commit` (`pipx install pre-commit` or package manager) and re-run `make setup` |
| `make verify` fails before commit | Linter or test regression introduced | Run `make format` and `make test` locally to inspect and fix failures |
