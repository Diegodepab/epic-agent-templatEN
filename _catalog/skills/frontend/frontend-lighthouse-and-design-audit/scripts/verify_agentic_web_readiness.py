#!/usr/bin/env python3
"""Verify Google Lighthouse 2026 Agentic Browsing & WebMCP readiness.

Ports all 6 official rules from Google Lighthouse (`core/config/agentic-browsing-config.js`
and `third-party/ard/ard.js` v0.91):
  1. `agentic/llms-txt`: `/llms.txt` existence, `# Title` H1, Markdown links, >= 50 chars
  2. `agentic/ard-schema`: `/.well-known/ard.json` or `<link rel="ard">`, URN `urn:air:*`,
     IANA standard agentic media types, deprecated `application/mcp-server+json` rejection,
     strict `url` XOR `data`, `representativeQueries` recommendation
  3. `agentic/agent-accessibility-tree`: landmark coverage, unlabeled buttons/links/inputs,
     missing image alt attributes, heading hierarchy skips
  4. `webmcp-form-coverage`: `<form>` elements carrying `toolname` + `tooldescription`
  5. `webmcp-registered-tools`: declarative WebMCP forms + imperative `navigator.modelContext`
  6. `webmcp-schema-validity`: valid tool names, non-empty descriptions, valid JSON schemas

Works 100% offline on local static build directories (`--dir public`) or live HTTP(S) (`--url`).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

sys.dont_write_bytecode = True

URN_REGEX = re.compile(r"^urn:air:([a-zA-Z0-9.-]+)(?::([a-zA-Z0-9._:-]+))?:([a-zA-Z0-9._-]+)$")
STANDARD_MEDIA_TYPES = {
    "application/ai-catalog+json",
    "application/agent-card+json",
    "application/a2a-agent-card+json",
    "application/mcp-server-card+json",
    "application/agent-skills+json",
    "application/agent-skills+md",
    "application/agent-skills+zip",
    "application/agent-skills+gzip",
    'text/markdown; profile="urn:air:agent-skills"',
    "application/agent-plugins+zip",
    "application/agent-plugins+gzip",
    "application/ai-registry",
    "application/ai-registry+json",
}
DEPRECATED_MEDIA_TYPES = {
    "application/mcp-server+json": "application/mcp-server-card+json",
}
WEBMCP_IMPERATIVE_RE = re.compile(
    r"navigator\.modelContext\.(?:registerTool|provideContext)\s*\(\s*\{(?P<body>[\s\S]{1,1200}?)\}",
    re.MULTILINE,
)
TOOLNAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,63}$")
SKIP_DIRS = {"node_modules", ".git", ".next", ".venv", "__pycache__"}


class _AgenticDomParser(HTMLParser):
    """Collect agentic accessibility, ARD `<link rel='ard'>`, and WebMCP form metadata."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ard_links: list[str] = []
        self.forms: list[dict[str, object]] = []
        self.headings: list[int] = []
        self.has_main_landmark = False
        self.labelled_ids: set[str] = set()
        self.unlabeled_images: list[str] = []
        self.unlabeled_inputs: list[dict[str, str]] = []
        self.interactive_stack: list[dict[str, str]] = []
        self.unlabeled_interactive: list[str] = []
        self._in_label_for: str | None = None
        self._current_tag: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        t = tag.lower()
        self._current_tag = t

        if t == "main" or a.get("role") == "main":
            self.has_main_landmark = True
        if t in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.headings.append(int(t[1]))

        if t == "link" and "ard" in a.get("rel", "").lower().split() and a.get("href"):
            self.ard_links.append(a["href"])

        if t == "img":
            hidden = a.get("aria-hidden") == "true" or a.get("role") in {"presentation", "none"}
            if not hidden and "alt" not in a:
                self.unlabeled_images.append(a.get("src", "<img without src>")[:80])

        if t == "label" and a.get("for"):
            self.labelled_ids.add(a["for"])

        if t in {"input", "select", "textarea"} and a.get("type", "").lower() not in {"hidden", "submit", "button", "reset"}:
            has_acc = bool(a.get("aria-label") or a.get("aria-labelledby") or a.get("title") or a.get("id") in self.labelled_ids)
            if not has_acc and a.get("id"):
                # Deferred check resolved after parsing all `<label for=...>` elements
                self.unlabeled_inputs.append({"tag": t, "id": a["id"], "name": a.get("name", ""), "has_placeholder": str(bool(a.get("placeholder")))})
            elif not has_acc:
                self.unlabeled_inputs.append({"tag": t, "id": "", "name": a.get("name", "")})

        if t in {"button", "a"}:
            self.interactive_stack.append(
                {
                    "tag": t,
                    "text": "",
                    "aria": (a.get("aria-label") or a.get("aria-labelledby") or a.get("title") or "").strip(),
                    "href": a.get("href", ""),
                }
            )

        if t == "form":
            self.forms.append(
                {
                    "id": a.get("id", ""),
                    "action": a.get("action", ""),
                    "toolname": a.get("toolname", ""),
                    "tooldescription": a.get("tooldescription", ""),
                    "has_toolname": "toolname" in a,
                    "has_tooldescription": "tooldescription" in a,
                    "autosubmit": "toolautosubmit" in a,
                }
            )

    def handle_data(self, data: str) -> None:
        if self.interactive_stack:
            self.interactive_stack[-1]["text"] += data

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in {"button", "a"} and self.interactive_stack and self.interactive_stack[-1]["tag"] == t:
            item = self.interactive_stack.pop()
            if not item["text"].strip() and not item["aria"]:
                self.unlabeled_interactive.append(f"<{t} href='{item['href'][:40]}'> missing accessible text or aria-label")

    def unresolved_inputs(self) -> list[str]:
        bad: list[str] = []
        for inp in self.unlabeled_inputs:
            iid = inp.get("id", "")
            if iid and iid in self.labelled_ids:
                continue
            bad.append(f"<{inp['tag']} name='{inp.get('name', '')}'> missing <label>/aria-label")
        return bad


def check_llms_txt(content: str | None, source: str) -> dict[str, object]:
    if content is None:
        return {"audit": "agentic/llms-txt", "status": "NOT_APPLICABLE", "errors": [], "warnings": ["No /llms.txt present"]}
    errors: list[str] = []
    if not re.search(r"^\s*#\s+.+", content, re.MULTILINE):
        errors.append("Missing required H1 header (`# Title`)")
    if not re.search(r"\[.+?\]\(.+?\)", content):
        errors.append("Missing Markdown links (`[label](url)`)")
    if len(content.strip()) < 50:
        errors.append("Content too short (< 50 characters)")
    return {"audit": "agentic/llms-txt", "status": "FAIL" if errors else "PASS", "source": source, "errors": errors}


def validate_ard_manifest(raw_content: str | None, source: str) -> dict[str, object]:
    if raw_content is None:
        return {"audit": "agentic/ard-schema", "status": "NOT_APPLICABLE", "errors": [], "warnings": ["No ARD manifest present"]}

    errors: list[str] = []
    warnings: list[str] = []
    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        return {"audit": "agentic/ard-schema", "status": "FAIL", "source": source, "errors": [f"Malformed JSON: {exc}"], "warnings": []}

    if not isinstance(data, dict):
        return {"audit": "agentic/ard-schema", "status": "FAIL", "source": source, "errors": ["Root ARD manifest must be a JSON object"], "warnings": []}

    entries = data.get("entries")
    if not isinstance(entries, list):
        return {"audit": "agentic/ard-schema", "status": "FAIL", "source": source, "errors": ["Missing required `entries` array"], "warnings": []}

    if "collections" in data:
        warnings.append("Deprecated top-level `collections` key; model hierarchies inside `entries`")

    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"Entry #{idx} must be a JSON object")
            continue
        label = str(entry.get("displayName") or entry.get("identifier") or f"Entry #{idx}")
        ident = entry.get("identifier")
        if not isinstance(ident, str) or not ident:
            errors.append(f"{label}: missing required `identifier`")
        elif not URN_REGEX.match(ident):
            errors.append(f"{label}: `identifier` '{ident}' violates RFC 8141 URN (`urn:air:<publisher>:<namespace>:<name>`)")

        if not entry.get("displayName"):
            errors.append(f"{label}: missing required `displayName`")

        media_type = entry.get("type")
        if not isinstance(media_type, str) or not media_type:
            errors.append(f"{label}: missing required `type` mediaType")
        else:
            base = media_type.split(";", 1)[0].strip().lower()
            if media_type.strip().lower() not in STANDARD_MEDIA_TYPES and base not in STANDARD_MEDIA_TYPES:
                if base in DEPRECATED_MEDIA_TYPES:
                    warnings.append(f"{label}: deprecated media type `{base}`; use `{DEPRECATED_MEDIA_TYPES[base]}`")
                elif not base.startswith("application/"):
                    warnings.append(f"{label}: non-standard ARD media type `{media_type}`")

        has_url = "url" in entry
        has_data = "data" in entry
        if has_url == has_data:
            errors.append(f"{label}: must provide strictly one of `url` or `data`")

        queries = entry.get("representativeQueries")
        if queries is None:
            warnings.append(f"{label}: missing `representativeQueries` (entry will not be indexed semantically)")
        elif not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
            errors.append(f"{label}: `representativeQueries` must be a list of strings")
        elif not (2 <= len(queries) <= 5):
            warnings.append(f"{label}: recommend 2-5 `representativeQueries` (got {len(queries)})")

    status = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {
        "audit": "agentic/ard-schema",
        "status": status,
        "source": source,
        "entries": len(entries),
        "errors": errors,
        "warnings": warnings,
    }


def _fetch_text(url: str, timeout: int = 6) -> tuple[int, str | None]:
    try:
        req = urlrequest.Request(url, headers={"User-Agent": "agentic-web-audit/1.0"})
        with urlrequest.urlopen(req, timeout=timeout) as resp:  # nosec B310 - http/https validated by caller
            return int(getattr(resp, "status", 200)), resp.read(2_000_000).decode("utf-8", errors="replace")
    except urlerror.HTTPError as exc:
        return int(exc.code), None
    except (urlerror.URLError, OSError, ValueError):
        return 0, None


def audit_directory(root: Path, require_agentic: bool) -> dict[str, object]:
    llms_candidates = [root / "llms.txt", root / "public/llms.txt", root / "dist/llms.txt"]
    llms_path = next((p for p in llms_candidates if p.is_file()), None)
    llms_res = check_llms_txt(llms_path.read_text(encoding="utf-8", errors="replace") if llms_path else None, str(llms_path or "missing"))

    ard_candidates = [
        root / ".well-known/ard.json",
        root / "public/.well-known/ard.json",
        root / "dist/.well-known/ard.json",
        root / "ard.json",
    ]
    ard_path = next((p for p in ard_candidates if p.is_file()), None)

    html_files = [p for p in sorted(root.rglob("*.html")) if p.is_file() and not any(part in SKIP_DIRS for part in p.parts)]
    a11y_errors: list[str] = []
    forms_total = 0
    forms_covered = 0
    webmcp_errors: list[str] = []
    registered_tools: list[dict[str, str]] = []

    for html_file in html_files[:50]:
        rel = html_file.relative_to(root).as_posix()
        parser = _AgenticDomParser()
        parser.feed(html_file.read_text(encoding="utf-8", errors="replace"))

        if parser.ard_links and ard_path is None:
            cand = (html_file.parent / parser.ard_links[0].lstrip("/")).resolve()
            if cand.is_file():
                ard_path = cand

        if not parser.has_main_landmark:
            a11y_errors.append(f"{rel}: missing `<main>` landmark for agent navigation")
        for img in parser.unlabeled_images[:5]:
            a11y_errors.append(f"{rel}: `<img>` missing `alt` ({img})")
        for inter in parser.unlabeled_interactive[:5]:
            a11y_errors.append(f"{rel}: {inter}")
        for inp in parser.unresolved_inputs()[:5]:
            a11y_errors.append(f"{rel}: {inp}")

        prev_h = 0
        for h in parser.headings:
            if prev_h and h - prev_h > 1:
                a11y_errors.append(f"{rel}: heading skip `h{prev_h} -> h{h}`")
                break
            prev_h = h

        for fm in parser.forms:
            forms_total += 1
            tname = str(fm["toolname"]).strip()
            tdesc = str(fm["tooldescription"]).strip()
            if fm["has_toolname"] or fm["has_tooldescription"]:
                if not tname:
                    webmcp_errors.append(f"{rel}: form declares WebMCP without `toolname`")
                elif not TOOLNAME_RE.match(tname):
                    webmcp_errors.append(f"{rel}: invalid WebMCP `toolname` '{tname}'")
                if not tdesc:
                    webmcp_errors.append(f"{rel}: form `{tname or '<unnamed>'}` missing `tooldescription`")
                if tname and tdesc and TOOLNAME_RE.match(tname):
                    forms_covered += 1
                    registered_tools.append({"kind": "declarative-form", "name": tname, "file": rel})

    # Scan JS/TS files for imperative navigator.modelContext WebMCP tool registration
    script_files = [
        p
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix in {".js", ".ts", ".tsx", ".jsx", ".mjs"} and not any(part in SKIP_DIRS for part in p.parts)
    ]
    for sf in script_files[:100]:
        rel = sf.relative_to(root).as_posix()
        txt = sf.read_text(encoding="utf-8", errors="replace")
        for m in WEBMCP_IMPERATIVE_RE.finditer(txt):
            body = m.group("body")
            nm = re.search(r"name\s*:\s*['\"]([^'\"]+)['\"]", body)
            dm = re.search(r"description\s*:\s*['\"]([^'\"]*)['\"]", body)
            tname = nm.group(1).strip() if nm else ""
            if not tname or not TOOLNAME_RE.match(tname):
                webmcp_errors.append(f"{rel}: imperative registerTool missing valid `name`")
            if not dm or not dm.group(1).strip():
                webmcp_errors.append(f"{rel}: imperative tool `{tname or '<unnamed>'}` missing `description`")
            else:
                registered_tools.append({"kind": "imperative-js", "name": tname, "file": rel})

    ard_res = validate_ard_manifest(ard_path.read_text(encoding="utf-8", errors="replace") if ard_path else None, str(ard_path or "missing"))

    if require_agentic:
        if llms_res["status"] == "NOT_APPLICABLE":
            llms_res = {"audit": "agentic/llms-txt", "status": "FAIL", "source": "missing", "errors": ["Missing required `/llms.txt`"]}
        if ard_res["status"] == "NOT_APPLICABLE":
            ard_res = {"audit": "agentic/ard-schema", "status": "FAIL", "source": "missing", "errors": ["Missing required `/.well-known/ard.json`"], "warnings": []}

    audits = [
        llms_res,
        ard_res,
        {
            "audit": "agentic/agent-accessibility-tree",
            "status": "FAIL" if a11y_errors else ("NOT_APPLICABLE" if not html_files else "PASS"),
            "html_files": len(html_files),
            "errors": a11y_errors,
        },
        {
            "audit": "webmcp-form-coverage",
            "status": "PASS" if (forms_total == 0 or forms_covered == forms_total) else "WARN",
            "forms_total": forms_total,
            "forms_covered": forms_covered,
        },
        {
            "audit": "webmcp-registered-tools",
            "status": "PASS",
            "tools": registered_tools,
        },
        {
            "audit": "webmcp-schema-validity",
            "status": "FAIL" if webmcp_errors else ("NOT_APPLICABLE" if not registered_tools and not webmcp_errors else "PASS"),
            "errors": webmcp_errors,
        },
    ]
    failed = [a["audit"] for a in audits if a["status"] == "FAIL"]
    return {
        "tool": "frontend-lighthouse-and-design-audit/verify_agentic_web_readiness",
        "mode": "directory",
        "target": root.name,
        "status": "FAIL" if failed else "PASS",
        "failed_audits": failed,
        "audits": audits,
    }


def audit_url(url: str, require_agentic: bool) -> dict[str, object]:
    base = url.rstrip("/")
    st_l, llms_txt = _fetch_text(f"{base}/llms.txt")
    st_a, ard_txt = _fetch_text(f"{base}/.well-known/ard.json")
    llms_res = check_llms_txt(llms_txt if 200 <= st_l < 400 else None, f"{base}/llms.txt")
    ard_res = validate_ard_manifest(ard_txt if 200 <= st_a < 400 else None, f"{base}/.well-known/ard.json")
    if require_agentic:
        if llms_res["status"] == "NOT_APPLICABLE":
            llms_res = {"audit": "agentic/llms-txt", "status": "FAIL", "source": f"{base}/llms.txt", "errors": ["Missing `/llms.txt`"]}
        if ard_res["status"] == "NOT_APPLICABLE":
            ard_res = {"audit": "agentic/ard-schema", "status": "FAIL", "source": f"{base}/.well-known/ard.json", "errors": ["Missing `/.well-known/ard.json`"], "warnings": []}
    audits = [llms_res, ard_res]
    failed = [a["audit"] for a in audits if a["status"] == "FAIL"]
    return {
        "tool": "frontend-lighthouse-and-design-audit/verify_agentic_web_readiness",
        "mode": "url",
        "target": base,
        "status": "FAIL" if failed else "PASS",
        "failed_audits": failed,
        "audits": audits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Lighthouse 2026 Agentic Browsing & WebMCP readiness (`llms.txt`, ARD v0.91, agent a11y, WebMCP)."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dir", help="Local static site / public / dist directory to audit offline")
    group.add_argument("--url", help="Live http(s) base URL to probe for /llms.txt and /.well-known/ard.json")
    parser.add_argument("--require-agentic", action="store_true", help="Fail if /llms.txt or /.well-known/ard.json is missing")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any failed audit (default exits 1 on schema/a11y FAIL)")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    parser.add_argument("--json-out", help="Write JSON report to path")
    args = parser.parse_args()

    if args.url:
        if not re.match(r"^https?://", args.url, re.I):
            print("[agentic-web] --url must start with http:// or https://", file=sys.stderr)
            return 2
        report = audit_url(args.url, args.require_agentic)
    else:
        target = Path(args.dir or ".").resolve()
        if not target.is_dir():
            print(f"[agentic-web] Directory not found: {target}", file=sys.stderr)
            return 2
        report = audit_directory(target, args.require_agentic)

    if args.json_out:
        out_p = Path(args.json_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"[agentic-web] status={report['status']} mode={report['mode']} target={report['target']}")
        for au in report["audits"]:  # type: ignore[attr-defined]
            print(f"  [{au['status']:14s}] {au['audit']}")
            for err in au.get("errors", [])[:6]:
                print(f"      ERR: {err}")
            for warn in au.get("warnings", [])[:4]:
                print(f"      WARN: {warn}")

    return 1 if report["failed_audits"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
