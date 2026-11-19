---
trigger: glob
globs: "**/Dockerfile*, **/dockerfile*, **/compose*.yaml, **/compose*.yml, **/.dockerignore, **/.env*"
---

# Containerization & Environment Configuration Rules

## 1. Multi-Stage Dockerfile Standards

- **Deterministic Layer Caching**: Copy dependency manifests and lockfiles (`pyproject.toml` + `uv.lock`, `package.json` + lockfile) and install dependencies in a dedicated layer *before* copying application source code.
- **Target Separation**: Provide distinct stages (`base`, `deps`, `dev`, `prod`) so local development supports hot-reload while production images stay minimal.
- **Hardened Production Stage**: In `prod` targets, copy only runtime artifacts, drop build toolchains, run as an unprivileged non-root user (`USER appuser`), and declare a lightweight `HEALTHCHECK`.

## 2. Modular Docker Compose (`compose.yaml`)

- **Profile-Driven Services**: Assign services to explicit `profiles`:
  - `deps`: auxiliary infrastructure only (databases, Redis, queues) for fast host-local code execution.
  - `dev`: containerized application with source bind-mounts and live reload.
  - `prod`: production-parity container stack.
  - `gpu`: hardware-accelerated workloads with explicit device reservations.
- **Zero Hardcoded Host Paths**: Use relative workspace paths or named volumes; never hardcode developer machine paths (`/home/...`, `/Users/...`).

## 3. Environment Variable Hygiene (`.env`)

- **Strict YAGNI (Zero Speculative Variables)**: Add a variable to `.env.example` **only** when application code actively reads it (`os.getenv`, `process.env`). Never pre-populate speculative services (Postgres, Redis, S3, message queues) or unused keys before the project actually adopts them.
- **Empty Secrets Only**: Never write default passwords, fake credentials (`postgres:postgres`, sample tokens), or real secrets in `.env.example` or source code. Leave secret values blank (`DATABASE_URL=`, `API_KEY=`) and provide real values only in local gitignored `.env`.
- **Code <-> `.env.example` Sync**: Whenever a variable is added or removed in code or `compose.yaml`, update `.env.example` immediately, validate required variables at startup, and run `docker-and-env-auditor` (`docker_env_linter.py`) to eliminate missing or orphan variables.
