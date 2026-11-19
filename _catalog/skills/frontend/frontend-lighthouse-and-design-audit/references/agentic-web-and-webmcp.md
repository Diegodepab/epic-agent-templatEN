# Lighthouse 2026 Agentic Browsing & WebMCP Specification

Ported from Google Chrome Lighthouse `agentic-browsing-config.js` and ARD Conformance v0.91 (`third-party/ard/ard.js`).

## The 6 Agentic Readiness Audits

1. **`agentic/llms-txt` (`llmstxt.org`)**
   - Expose `/llms.txt` at site root as concise Markdown.
   - Must start with at least one H1 heading (`# Project Name`), contain Markdown links (`[label](url)`), and exceed 50 characters.
2. **`agentic/ard-schema` (`/.well-known/ard.json`, ARD v0.91)**
   - Serve at `/.well-known/ard.json` or advertise via `<link rel="ard" href="...">`.
   - Root object requires `"entries": [...]`.
   - Each entry requires:
     - `"identifier"`: RFC 8141 URN matching `urn:air:<publisher>:<namespace>:<agent-name>`
     - `"displayName"`: human/agent-readable title
     - `"type"`: standard IANA discovery media type (`application/ai-catalog+json`, `application/agent-card+json`, `application/a2a-agent-card+json`, `application/mcp-server-card+json`, `application/agent-skills+json`, `application/agent-plugins+zip`, etc.; never use deprecated `application/mcp-server+json`)
     - Strictly **one** of `"url"` or `"data"` (never both, never neither)
     - Recommended: `"representativeQueries"` with 2–5 short intent strings for vector registry indexing
3. **`agentic/agent-accessibility-tree`**
   - Require `<main>` landmark, non-empty accessible text/`aria-label` on buttons/links, `<label for>`/`aria-label` on form controls, `alt` text on non-decorative images, and sequential headings (`h1 -> h2 -> h3`).
4. **`webmcp-form-coverage`**
   - Add declarative WebMCP attributes (`toolname`, `tooldescription`) to critical HTML `<form>` workflows so AI browser agents can invoke forms structurally.
5. **`webmcp-registered-tools` & `webmcp-schema-validity`**
   - Validate declarative form attributes and imperative `navigator.modelContext.registerTool({ name, description, inputSchema })` calls: unique valid tool identifiers, non-empty descriptions, and valid JSON schemas.
