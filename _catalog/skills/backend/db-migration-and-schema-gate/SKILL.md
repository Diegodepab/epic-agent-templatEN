---
name: db-migration-and-schema-gate
description: Audits SQL schemas, Alembic revisions, and Drizzle ORM migration journals for destructive DDL (DROP TABLE/COLUMN), lock-inducing NOT NULL additions without DEFAULT, unindexed foreign keys, and divergent migration heads. Use when creating or reviewing database migrations and schemas. Not for frontend CSS or game shaders.
---

# Database Migration and Schema Gate

Prevent data-loss DDL, zero-downtime table locks, unindexed foreign keys, and divergent migration graphs across raw SQL, Alembic (Python), and Drizzle ORM (TypeScript) before applying migrations. Treat scripts under `scripts/` as black boxes: run `--help` first.

## Decision Tree

- **Auditing raw `.sql` schemas or Alembic `versions/*.py` migrations?** -> Run `python3 scripts/audit_sql_and_migrations.py --target <migrations_dir>`
- **Auditing Drizzle ORM (`_journal.json`, snapshots, and `.sql` tags)?** -> Run `python3 scripts/check_drizzle_migrations.py --root . --json`
- **Performing an intentional expand-contract cleanup where `DROP` is approved?** -> Pass `--allow-destructive` to `audit_sql_and_migrations.py`

## What Lives Where

| Artifact | Purpose | Output / Gate |
|---|---|---|
| `scripts/audit_sql_and_migrations.py` | Detects `DROP`/`TRUNCATE`, `ADD COLUMN NOT NULL` without `DEFAULT`, unindexed FKs, and multiple Alembic heads | Exit `0` (clean) / `1` (blocking hazard) |
| `scripts/check_drizzle_migrations.py` | Read-only Drizzle `_journal.json` / snapshot consistency & branch conflict verifier | Exit `0` (clean) / `1` (conflict) / `2` (none found) |

## Commands

```bash
python3 .agents/skills/db-migration-and-schema-gate/scripts/audit_sql_and_migrations.py --help
python3 .agents/skills/db-migration-and-schema-gate/scripts/audit_sql_and_migrations.py --target migrations --require-concurrent-index
python3 .agents/skills/db-migration-and-schema-gate/scripts/check_drizzle_migrations.py --help
python3 .agents/skills/db-migration-and-schema-gate/scripts/check_drizzle_migrations.py --migrations-dir drizzle
```
