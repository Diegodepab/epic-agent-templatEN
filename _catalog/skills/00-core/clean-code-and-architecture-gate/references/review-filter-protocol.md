# Code Review Anti-Hallucination & False-Positive Filter Protocol

Adapted from Alibaba `open-code-review` (`review_filter_task_user.md`) and `ponytail` (`ponytail-review` / `ponytail-audit`).
Use when filtering automated review comments or conducting pre-completion adversarial code reviews.

## 1. Two-Ground False-Positive Filter (Default = Approve Comment)

When evaluating a review finding against actual diffs `<review_files>`, keep the finding by default unless the diff itself **proves** the finding false on one of these two strict grounds:

1. **Ground A — Subject-File Mismatch:**
   The symbol, statement, or construct the finding describes does **not** appear anywhere in the `<file>` whose path the finding names. Judge against that subject file alone — a construct in a sibling file does not rescue a misfiled finding.
   - Example: claiming a function body lacks error handling in an interface/header file that only declares it, or discussing host-language logic inside a markup/config file.
2. **Ground B — Literal Diff Contradiction:**
   A concrete diff line in any file in the group **literally contradicts** the finding's central claim without requiring multi-step speculation.
   - Example: claiming an identifier is unused when the diff invokes it; claiming a guard/assertion is missing when the diff shows that exact check; claiming a literal is hardcoded when the diff reads it from configuration.

### Never-Remove Protected Subjects (Hard Vetoes)

Regardless of confidence, **never dismiss** a finding if its subject touches any of these 5 high-cost categories:
1. **Memory safety** — buffer/slice bounds, allocation size, off-by-one, use-after-free, null dereference.
2. **Concurrency** — locks/mutex modes, atomics, check-then-write races, missing synchronization.
3. **Linkage & declaration consistency** — visibility (`static` vs public), declaration vs definition mismatch, missing exports.
4. **Behavioral or compatibility change** — altered status code/default/field/error path, or lifecycle counter/state shift.
5. **Unused accepted parameter** — a public or handler parameter accepted in the signature and silently ignored in the body.

## 2. Six-Axis Audit Rubric (`ponytail-audit` & `ponytail-review`)

Order findings strictly by operational blast radius:
1. **Correctness (Bug):** wrong result, crash, missed edge case (empty, zero, rounding, time zones), or broken caller outside the diff.
2. **Risk:** security flaws (injection, secrets, trust-boundary bypass) or data loss (swallowed errors, missing transactions, out-of-order writes).
3. **Scale:** works for 1 user, breaks under concurrency/load (unbounded growth, per-item N+1 query, O(n^2) hot path, per-process state).
4. **Missing Test:** non-trivial risky branch/parser/money/security/write path with zero failing test guard.
5. **Speed:** repeated expensive work inside hot loops.
6. **Lean (`Lean: -N lines, -M deps possible`):** dead code, speculative config/flags, single-impl interfaces, pass-through wrappers, reinvented stdlib helpers. Every deliberate compromise is allowed only with `shortcut: <ceiling>, <when to revisit>`.
