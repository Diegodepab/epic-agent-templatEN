"""Security & scoping helpers for polish_audit (extracted from launch_check v1.0).

Provides same-origin Playwright routing guards, credential redaction (`sanitize_report`),
and bounded same-site HTTP `Fetcher` without external dependencies.
"""

from __future__ import annotations

import re
import time
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

USER_AGENT = "polish-audit/1.0 (+epic-agent-templatEN; passive check)"
MAX_HTML = 3_000_000
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")

COMPILED = {
    "stripe-secret": re.compile(r"\b[sr]k_live_[0-9A-Za-z]{20,}"),
    "stripe-webhook": re.compile(r"\bwhsec_[0-9A-Za-z]{24,}"),
    "anthropic": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{32,}"),
    "openai": re.compile(r"\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{30,}|\bsk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}|\bsk-[A-Za-z0-9]{48}\b"),
    "aws": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}"),
    "slack": re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{20,}"),
    "sendgrid": re.compile(r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b"),
    "supabase-secret": re.compile(r"\bsb_secret_[A-Za-z0-9_-]{20,}"),
}
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")


def clean(text: object, limit: int = 160) -> str:
    s = CTRL.sub("", str(text if text is not None else ""))
    return s if len(s) <= limit else s[: limit - 1] + "…"


def sanitize_report(value: object) -> object:
    """Remove known credential shapes and URL query/user credentials from report data."""
    if isinstance(value, dict):
        return {clean(k, 200): sanitize_report(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_report(v) for v in value]
    if not isinstance(value, str):
        return value
    text = CTRL.sub("", value)
    text = re.sub(
        r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----|\Z)",
        "[REDACTED PRIVATE KEY]",
        text,
    )
    for rx in COMPILED.values():
        text = rx.sub("[REDACTED]", text)
    text = JWT.sub("[REDACTED JWT]", text)

    def _url_without_secrets(match: re.Match[str]) -> str:
        try:
            parts = urlparse.urlsplit(match.group())
            host = parts.hostname or ""
            if ":" in host:
                host = "[" + host + "]"
            if parts.port is not None:
                host += ":" + str(parts.port)
            q = urlparse.urlencode([(k, "[REDACTED]") for k, _ in urlparse.parse_qsl(parts.query, keep_blank_values=True)])
            return urlparse.urlunsplit((parts.scheme, host, parts.path, q, ""))
        except ValueError:
            return "[OMITTED URL]"

    return re.sub(r"https?://[^\s<>\"'`]+", _url_without_secrets, text)


def origin(url: str) -> tuple[str, str, int]:
    parts = urlparse.urlsplit(url)
    if parts.username or parts.password or "\\" in url:
        raise ValueError("URL credentials/backslashes are not allowed")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return parts.scheme.lower(), (parts.hostname or "").lower(), port


def same_site(a: str, b: str) -> bool:
    oa, ob = origin(a), origin(b)
    return oa == ob or (oa[0] == "https" and ob[0] == "http" and oa[1] == ob[1] and oa[2] == 443 and ob[2] == 80)


def guard_browser_context(context: object, target: str) -> None:
    """Restrict active rendering to same-origin GET/HEAD and block outbound sockets."""
    if not hasattr(context, "route_web_socket"):
        raise RuntimeError("Browser audit requires Playwright with WebSocket routing support")
    context.route_web_socket("**/*", lambda socket: socket.close())  # type: ignore[attr-defined]

    def _route_request(route: object) -> None:
        req = route.request  # type: ignore[attr-defined]
        try:
            allowed = (
                req.method in ("GET", "HEAD")
                and origin(req.url) == origin(target)
                and urlparse.urlsplit(req.url).scheme in ("http", "https")
            )
        except ValueError:
            allowed = False
        route.continue_() if allowed else route.abort()  # type: ignore[attr-defined]

    context.route("**/*", _route_request)  # type: ignore[attr-defined]


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Resp:
    def __init__(self, url: str, status: int, headers: dict[str, str], body: bytes, elapsed: float, error: str = ""):
        self.url, self.status, self.headers, self.body, self.elapsed, self.error = url, status, headers, body, elapsed, error

    def header(self, name: str) -> str:
        return self.headers.get(name.lower(), "")


class Fetcher:
    """GET with manual same-site redirect checks and bounded body reads."""

    def __init__(self, timeout: int, user_agent: str = USER_AGENT):
        self.timeout = timeout
        self.user_agent = user_agent
        self.opener = urlrequest.build_opener(_NoRedirect)
        self.requests = 0
        self.refused: list[str] = []

    def raw(self, url: str, cap: int, method: str = "GET") -> Resp:
        self.requests += 1
        req = urlrequest.Request(
            url,
            method=method,
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity", "Accept": "*/*"},
        )
        t0 = time.time()
        try:
            resp = self.opener.open(req, timeout=self.timeout)  # nosec B310 - scheme guarded by caller
        except urlerror.HTTPError as exc:
            resp = exc
        except (urlerror.URLError, OSError, ValueError) as exc:
            return Resp(url, 0, {}, b"", time.time() - t0, str(getattr(exc, "reason", exc)))
        headers: dict[str, str] = {}
        for key, value in resp.headers.items():
            kl = key.lower()
            headers[kl] = headers[kl] + "\n" + value if kl == "set-cookie" and kl in headers else value
        try:
            body = resp.read(cap + 1) if method == "GET" else b""
        except OSError:
            body = b""
        status = getattr(resp, "status", None) or getattr(resp, "code", 0)
        resp.close()
        return Resp(url, int(status), headers, body[:cap], time.time() - t0)

    def get(self, url: str, cap: int = MAX_HTML, start: str | None = None, max_redirects: int = 5):
        start = start or url
        chain = []
        for _ in range(max_redirects + 1):
            if not re.match(r"^https?://", url, re.I):
                self.refused.append(clean(url))
                return Resp(url, 0, {}, b"", 0.0, "refused: not http(s)"), chain
            resp = self.raw(url, cap)
            if resp.status in (301, 302, 303, 307, 308) and resp.header("location"):
                nxt = urlparse.urljoin(url, resp.header("location").strip())
                chain.append((url, resp.status, nxt))
                if not re.match(r"^https?://", nxt, re.I) or not same_site(nxt, start):
                    self.refused.append(clean(nxt))
                    resp.error = "redirect to another site not followed"
                    return resp, chain
                url = nxt
                continue
            return resp, chain
        return Resp(url, 0, {}, b"", 0.0, "too many redirects"), chain
