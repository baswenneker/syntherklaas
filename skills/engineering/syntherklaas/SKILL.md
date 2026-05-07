---
name: syntherklaas
description: Generate synthetic data from Excel (multi-tab) or a directory of CSV files into a SQLite database with consistent PII anonymization (names, emails, phone numbers, BSNs, postcodes, IBANs) and intact foreign-key relationships. Use when the user wants to anonymize business data, create test or demo data from production samples, convert Excel or CSV input into SQLite with fake but coherent values, or mentions "synthetische data", "fake data", "anonimiseer", "BSN-safe test data", or refers to multi-table data with FK relations.
---

# syntherklaas

Pipeline: Excel/CSV → detect PII + FKs → topo-sort → sample → anonymize → SQLite.

PII (PERSON / EMAIL / PHONE_NUMBER / BSN / POSTCODE / IBAN) is replaced with consistent fakes within one run — same input value always maps to the same fake, across rows and across tables. Foreign-key relations are preserved via per-table ID-offset and FK-rewriting.

## Quick start

```bash
# First run only: install deps and Spacy NL model
bash "${CLAUDE_SKILL_DIR}/scripts/run.sh" --help

# Anonymize an Excel file into a new SQLite DB
bash "${CLAUDE_SKILL_DIR}/scripts/run.sh" \
  --input ./mydata.xlsx \
  --db ./mydata.sqlite

# CSV directory + cap to 100 root rows
bash "${CLAUDE_SKILL_DIR}/scripts/run.sh" \
  --input ./mydata/ \
  --db ./mydata.sqlite \
  --max-rows 100

# Append to existing DB (default = auto: append if file exists, else new)
bash "${CLAUDE_SKILL_DIR}/scripts/run.sh" \
  --input ./more.xlsx \
  --db ./existing.sqlite \
  --mode append
```

See `examples/` for a working 3-table demo (klanten / orders / orderlines) plus optional `_relations` and `_pii_config` meta-sheets.

## Input format

- **Excel**: one tab per table. Optional meta-tabs `_relations` (FK overrides) and `_pii_config` (PII overrides).
- **CSV directory**: one file per table. Optional `_relations.csv` and `_pii_config.csv` in the same directory.

Override schemas:

```
_relations:    table | column | references_table | references_column
_pii_config:   table | column | pii_type         | strategy   (force | skip)
```

Override priority for FKs: existing DB schema (append-mode) > `_relations` > auto-infer.
Override priority for PII: `_pii_config` (force/skip) > Presidio auto-detection.

## Workflows

### Anonymize a single dataset
1. Identify the input (Excel or CSV directory) and target SQLite path.
2. Decide whether to add `_relations` / `_pii_config` overrides.
3. Run `scripts/run.sh --input <path> --db <path>`.
4. Inspect the report (PII detection per column, FK resolution per relation, row counts).

### Append more rows to an existing DB
1. Confirm input columns match the existing tables (skill fails fast on mismatch).
2. Run with `--mode append` (or default `auto` when DB exists).
3. New rows get IDs starting from `MAX(id)+1`; FK columns are rewritten so children point at the new parent IDs.

### Create a smaller subset
- Pass `--max-rows N`. Cap is applied to root tables (no incoming FK); children follow via FK-filter.

## Exit codes

- `0` — success
- `2` — schema mismatch (input columns differ from existing DB table)
- `3` — cyclic or composite FK detected
- `4` — missing dependencies (uv / spacy model)

## Reference

- Pipeline modules in `scripts/`: `detector.py`, `nl_recognizers.py`, `fk_resolver.py`, `sampler.py`, `anonymizer.py`, `sqlite_writer.py`.
- CLI entry: `scripts/syntherklaas.py`.
- Tests: `scripts/tests/` (run via `uv run pytest`).
- Worked example: `examples/run-example.sh`.
