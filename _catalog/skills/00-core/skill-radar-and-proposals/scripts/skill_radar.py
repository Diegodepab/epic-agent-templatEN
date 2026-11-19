#!/usr/bin/env python3
"""Skill Radar & Proposal Generator (inspired by last30days-skill velocity scoring).

1. Online mode (`discover`): Queries GitHub Search/Releases & Hacker News Algolia
   for the last N days, ranks candidates by recency-weighted engagement velocity
   (`engagement / sqrt(age_days + 1)` with first-week boost), filters already-seen
   repos, and checks whether candidates bundle real executable engines (`scripts/`).
2. Offline/Local mode (`propose`): Compares digested reference repos against the
   local skill catalog to emit concrete skill enhancement proposals.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_WATCHLIST = Path(__file__).parent.parent / "data" / "watchlist.json"
DEFAULT_SEEN_PATH = Path(".agents/radar_seen.json")

ENGINE_EXTRACTION_MAP = (
    ("recon.py", "backend/backend-security-and-owasp-gate", "Regex/entropy secret scanner for JS bundles & source files"),
    ("scope.py", "00-core / backend", "Deterministic allowlist/denylist target scope guard"),
    ("verify-action-pins.sh", "github/git-commit-and-pr-gate", "Verify GitHub Actions workflows pin third-party actions by commit SHA"),
    ("open-code-review-delegate", "github/git-commit-and-pr-gate", "Structured diff preview, file grouping, and severity/category review schema"),
    ("rerank.py", "00-core/skill-radar-and-proposals", "Recency-weighted engagement velocity scoring algorithm"),
    ("extract-static-html", "frontend/frontend-quality-and-design-gate", "Clean static HTML/CSS extraction & post-processing scripts"),
    ("validate.js", "frontend/frontend-quality-and-design-gate", "Component structure & asset validation checks"),
    ("svg_audit.py", "frontend/brand-logo-and-svg-forge", "Geometric vector SVG auditor and PNG variant exporter"),
    ("map_structure.py", "00-core/clean-code-and-architecture-gate", "Multi-language symbol/role mapper and Clean Architecture boundary checker"),
    ("fingerprint.py", "00-core/systematic-debugging-and-rca", "Deterministic SHA-256 failure fingerprinting to break AI fix loops"),
    ("dependency_scanner.py", "backend/backend-security-and-owasp-gate", "Read-only supply-chain and Dockerfile security scanner"),
    ("check_drizzle_migrations.py", "backend/db-migration-and-schema-gate", "Drizzle ORM migration journal and snapshot conflict verifier"),
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def velocity_score(engagement: float, iso_date: str | None, now: datetime) -> float:
    """Apply recency decay (`1 / sqrt(age_days + 1)`) + 1.5x first-week boost."""
    if engagement <= 0:
        return 0.0
    age_days = 30
    if iso_date:
        try:
            dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
            age_days = max(0, (now - dt).days)
        except ValueError:
            pass
    weight = 1.0 / math.sqrt(age_days + 1)
    if age_days < 7:
        weight *= 1.5
    return round(engagement * weight, 2)


def resolve_github_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    try:
        proc = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False, timeout=4)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except OSError:
        pass
    return None


def http_get_json(url: str, token: str | None = None, timeout: int = 12) -> dict[str, object]:
    headers = {"User-Agent": "antigravity-skill-radar/1.0", "Accept": "application/vnd.github+json"}
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_github_candidates(queries: list[str], days: int, token: str | None) -> list[dict[str, object]]:
    since = (utc_now() - timedelta(days=days)).strftime("%Y-%m-%d")
    now = utc_now()
    seen_slugs: set[str] = set()
    candidates: list[dict[str, object]] = []

    for q in queries:
        full_q = f"{q} pushed:>={since}"
        url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(full_q)}&sort=updated&per_page=8"
        data = http_get_json(url, token=token)
        for item in data.get("items", []):  # type: ignore[union-attr]
            slug = str(item.get("full_name", ""))
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            stars = float(item.get("stargazers_count", 0))
            pushed_at = str(item.get("pushed_at", ""))
            candidates.append(
                {
                    "source": "github",
                    "slug": slug,
                    "url": item.get("html_url", ""),
                    "description": (item.get("description") or "")[:140],
                    "stars": int(stars),
                    "pushed_at": pushed_at[:10],
                    "language": item.get("language") or "mixed",
                    "velocity": velocity_score(stars, pushed_at, now),
                }
            )
    return candidates


def fetch_watched_releases(repos: list[str], days: int, token: str | None) -> list[dict[str, object]]:
    cutoff = utc_now() - timedelta(days=days)
    releases: list[dict[str, object]] = []
    for slug in repos:
        url = f"https://api.github.com/repos/{slug}/releases/latest"
        try:
            rel = http_get_json(url, token=token)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        pub = str(rel.get("published_at") or "")
        if not pub:
            continue
        dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        if dt >= cutoff:
            releases.append(
                {
                    "repo": slug,
                    "tag": rel.get("tag_name", ""),
                    "published_at": pub[:10],
                    "url": rel.get("html_url", ""),
                }
            )
    return releases


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("seen", []))
    except (OSError, json.JSONDecodeError):
        return set()


def save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"seen": sorted(seen)}, indent=2) + "\n", encoding="utf-8")


def cmd_discover(args: argparse.Namespace) -> int:
    watchlist = json.loads(Path(args.watchlist).read_text(encoding="utf-8"))
    days = int(args.days or watchlist.get("window_days", 30))
    token = resolve_github_token()
    seen_path = Path(args.seen_file)
    already_seen = load_seen(seen_path)

    try:
        candidates = fetch_github_candidates(watchlist.get("github_queries", []), days, token)
        releases = fetch_watched_releases(watchlist.get("watched_repos", []), days, token)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(
            f"NETWORK_UNAVAILABLE: Could not reach GitHub API ({exc}). "
            "Run outside sandbox or use `propose` against local reference repos.",
            file=sys.stderr,
        )
        return 1

    fresh = [c for c in candidates if str(c["slug"]) not in already_seen]
    fresh.sort(key=lambda c: -float(c["velocity"]))

    lines = [
        f"# Skill Radar Proposals (Last {days} Days)",
        f"> Generated: {utc_now().strftime('%Y-%m-%dT%H:%M:%SZ')} | New candidates: {len(fresh)} | Recent watched releases: {len(releases)}",
        "",
        "## Watched Repository Releases",
    ]
    if releases:
        for r in releases:
            lines.append(f"- **`{r['repo']}` `{r['tag']}`** ({r['published_at']}) — {r['url']}")
    else:
        lines.append("- _No new tagged releases in window._")

    lines.extend(["", "## Ranked Skill & Tool Candidates (By Recency Velocity)"])
    for c in fresh[:15]:
        lines.append(
            f"- **`{c['slug']}`** (score={c['velocity']}, stars={c['stars']}, {c['language']}, pushed {c['pushed_at']}) — {c['description']} | {c['url']}"
        )

    out_text = "\n".join(lines) + "\n"
    if args.out == "-":
        print(out_text)
    else:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"Wrote skill radar proposals to {args.out}")

    if args.mark_seen:
        already_seen.update(str(c["slug"]) for c in fresh)
        save_seen(seen_path, already_seen)
    return 0


def cmd_propose(args: argparse.Namespace) -> int:
    """Match digested/local reference repos against the skill catalog to propose extractions."""
    ref_root = Path(args.reference_dir)
    catalog_root = Path(args.catalog_dir)
    if not ref_root.is_dir():
        print(f"Reference directory not found: {ref_root}", file=sys.stderr)
        return 1

    existing_skills = {p.parent.name for p in catalog_root.rglob("SKILL.md")} if catalog_root.is_dir() else set()
    proposals: list[dict[str, str]] = []
    seen_assets: set[tuple[str, str]] = set()

    for repo_dir in sorted(p for p in ref_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for artifact, target_skill, rationale in ENGINE_EXTRACTION_MAP:
            matches = list(repo_dir.rglob(f"*{artifact}*"))
            real_matches = [m for m in matches if "tests" not in m.parts and not m.name.startswith("test_")]
            if real_matches:
                rel = real_matches[0].relative_to(repo_dir).as_posix()
                seen_assets.add((repo_dir.name, rel))
                target_name = target_skill.split("/")[-1]
                status = "ENHANCE_EXISTING" if target_name in existing_skills else "CREATE_OR_BUILD_PLANNED"
                proposals.append(
                    {
                        "source_repo": repo_dir.name,
                        "matched_path": rel,
                        "target_skill": target_skill,
                        "status": status,
                        "rationale": rationale,
                    }
                )

        # Generic discovery for unseen repos: find script-backed SKILL.md folders not yet in catalog
        for skill_md in sorted(repo_dir.rglob("SKILL.md")):
            skill_dir = skill_md.parent
            scripts_dir = skill_dir / "scripts"
            if not scripts_dir.is_dir():
                continue
            has_exec = any(f.suffix in {".py", ".sh", ".js", ".ts", ".mjs", ".cjs"} for f in scripts_dir.iterdir() if f.is_file())
            if not has_exec:
                continue
            rel = skill_dir.relative_to(repo_dir).as_posix()
            if (repo_dir.name, rel) in seen_assets:
                continue
            status = "ALREADY_IN_CATALOG" if skill_dir.name in existing_skills else "CANDIDATE_PORT"
            proposals.append(
                {
                    "source_repo": repo_dir.name,
                    "matched_path": rel,
                    "target_skill": f"triage/{skill_dir.name}",
                    "status": status,
                    "rationale": "Generic script-backed SKILL.md detected; inspect via `repo_map.py --digest-reference`",
                }
            )

    lines = [
        "# Local Reference -> Skill Extraction Proposals",
        f"> Scanned reference dir: `{ref_root}` | Existing skills detected: {len(existing_skills)}",
        "",
        "| Source Repo | Extractable Asset | Target Skill / Area | Catalog Status | Rationale |",
        "|---|---|---|---|---|",
    ]
    for p in proposals:
        lines.append(
            f"| `{p['source_repo']}` | `{p['matched_path']}` | `{p['target_skill']}` | `{p['status']}` | {p['rationale']} |"
        )
    if not proposals:
        lines.append("| _none_ | — | — | — | No known engine signatures matched; inspect with `repo_map.py --digest-reference` first. |")

    out_text = "\n".join(lines) + "\n"
    if args.out == "-":
        print(out_text)
    else:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"Wrote {len(proposals)} extraction proposal(s) to {args.out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Skill discovery radar and local extraction proposer.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover", help="Query GitHub/releases in last N days (requires network)")
    p_disc.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    p_disc.add_argument("--days", type=int, default=30)
    p_disc.add_argument("--seen-file", default=str(DEFAULT_SEEN_PATH))
    p_disc.add_argument("--mark-seen", action="store_true")
    p_disc.add_argument("--out", default=".agents/SKILL_PROPOSALS.md")
    p_disc.set_defaults(func=cmd_discover)

    p_prop = sub.add_parser("propose", help="Propose extractions from local _reference/repos/ vs catalog")
    p_prop.add_argument("--reference-dir", default="_reference/repos")
    p_prop.add_argument("--catalog-dir", default=".agents/skills")
    p_prop.add_argument("--out", default="-")
    p_prop.set_defaults(func=cmd_propose)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
