---
trigger: glob
globs: "**/*.py, **/pyproject.toml"
---

# Python Engineering & Static Analysis Standards

## 1. Toolchain & Dependency Management (`uv`)

- Use `uv` exclusively (`uv sync`, `uv add`, `uv run`). Never invoke bare `pip`, `pip3`, or unwrapped `python` when executing project scripts, linters, or tests.
- Keep dependencies pinned in `uv.lock` and separate development tools (`ruff`, `mypy`/`pyright`, `pytest`) into `[dependency-groups]` or `[project.optional-dependencies]`.

## 2. Strict Typing & Data Contracts

- Annotate all function parameters, return values, and class attributes.
- **No Unjustified `Any` or Raw Dicts**: Avoid `Any` and untyped `dict` / `Dict[str, Any]` across module boundaries.
- Use **Pydantic v2** (`BaseModel`, `ConfigDict`, `Field`) for external boundaries (API payloads, settings, config files) and `@dataclass(frozen=True, slots=True)` or `TypedDict` for internal domain structures.

## 3. Filesystem, Security & Resource Safety

- **Path Handling**: Always use `pathlib.Path` instead of `os.path`.
- **Path Traversal & Extraction Safety**: When resolving user-supplied filenames or extracting archives, verify containment via `target_path.resolve().relative_to(allowed_root.resolve())`.
- **Context Managers**: Always open files, network clients (`httpx.AsyncClient`), DB sessions, and locks inside `with` or `async with` blocks.

## 4. Error Handling, Logging & Concurrency

- **Specific Exceptions**: Catch concrete exception classes (`ValueError`, `KeyError`, `OSError`). Never use bare `except:` or silent `except Exception: pass`.
- **Structured Logging**: Use the standard `logging` module (`logger = logging.getLogger(__name__)`) with appropriate levels (`debug`, `info`, `warning`, `error`). Never leave `print()` calls in production code.
- **Non-Blocking Async**: Never execute CPU-heavy work (tensor math, large parsing, hashing) or synchronous blocking I/O directly inside `async def` coroutines; offload via `asyncio.to_thread()` or `loop.run_in_executor()`.
