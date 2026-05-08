---
name: syntherklaas
description: Generate synthetic data from Excel (multi-tab) or a directory of CSV files into a SQLite database or Excel (.xlsx) file with consistent PII anonymization (names, emails, phone numbers, BSNs, postcodes, IBANs) and intact foreign-key relationships. Output format is inferred from the extension (.db/.sqlite or .xlsx). Use when the user wants to anonymize business data, create test or demo data from production samples, convert Excel or CSV input into SQLite or XLSX with fake but coherent values, or mentions "synthetic data", "fake data", "anonymize", "BSN-safe test data", or refers to multi-table data with FK relations.
---

# syntherklaas

Pipeline: Excel/CSV → detect PII + FKs → topo-sort → sample → anonymize → SQLite or XLSX.

PII (PERSON / EMAIL / PHONE_NUMBER / BSN / POSTCODE / IBAN) is replaced with consistent fakes within one run — same input value always maps to the same fake, across rows and across tables. Foreign-key relations are preserved via per-table ID-offset and FK-rewriting.

Output format is selected via the `--output` extension: `.db` or `.sqlite` writes a SQLite database (supports `--mode append`); `.xlsx` writes a multi-sheet Excel file (always new — append is not supported for xlsx).

## Quick start

```bash
# First run only: install deps and Spacy NL model
bash "${CLAUDE_SKILL_DIR}/scripts/run.sh" --help

# Anonymize an Excel file into a new SQLite DB
bash "${CLAUDE_SKILL_DIR}/scripts/run.sh" \
  --input ./mydata.xlsx \
  --output ./mydata.sqlite

# Same input, but write to a new Excel file (multi-sheet)
bash "${CLAUDE_SKILL_DIR}/scripts/run.sh" \
  --input ./mydata.xlsx \
  --output ./mydata-anonymized.xlsx

# CSV directory + cap to 100 root rows
bash "${CLAUDE_SKILL_DIR}/scripts/run.sh" \
  --input ./mydata/ \
  --output ./mydata.sqlite \
  --max-rows 100

# Append to existing SQLite DB (default = auto: append if file exists, else new)
# NOTE: --mode append is SQLite-only; combining it with .xlsx exits with code 2.
bash "${CLAUDE_SKILL_DIR}/scripts/run.sh" \
  --input ./more.xlsx \
  --output ./existing.sqlite \
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

Override priority for FKs: existing DB schema (SQLite append-mode only) > `_relations` > auto-infer.
Override priority for PII: `_pii_config` (force/skip) > Presidio auto-detection.

## Workflows

### Anonymize a single dataset
1. Identify the input (Excel or CSV directory) and target output path. Output format is inferred from the extension: `.db` / `.sqlite` for SQLite, `.xlsx` for Excel.
2. Decide whether to add `_relations` / `_pii_config` overrides.
3. Run `scripts/run.sh --input <path> --output <path>`.
4. Inspect the report (PII detection per column, FK resolution per relation, row counts).

### Append more rows to an existing DB (SQLite only)
1. Confirm input columns match the existing tables (skill fails fast on mismatch).
2. Run with `--output existing.sqlite --mode append` (or default `auto` when DB exists).
3. New rows get IDs starting from `MAX(id)+1`; FK columns are rewritten so children point at the new parent IDs.

XLSX output does not support append — `--mode append` combined with `.xlsx` exits with code 2. Re-run with a fresh `.xlsx` path instead.

### Write to a multi-sheet Excel file
- Use `--output <path>.xlsx`. Sheet order is topological (parent → child); the header row is frozen for usability. The output path must not already exist.

### Create a smaller subset
- Pass `--max-rows N`. Cap is applied to root tables (no incoming FK); children follow via FK-filter.

## Exit codes

- `0` — success
- `2` — schema mismatch, mode conflict, or invalid output target (e.g. unsupported extension, identical input/output paths, xlsx output already exists, `--mode append` with xlsx, table name exceeds Excel's 31-char sheet-name limit)
- `3` — cyclic or composite FK detected
- `4` — missing dependencies (uv / spacy model)

## Reference

- Pipeline modules in `scripts/`: `detector.py`, `nl_recognizers.py`, `fk_resolver.py`, `sampler.py`, `anonymizer.py`, `sqlite_writer.py`, `xlsx_writer.py`.
- CLI entry: `scripts/syntherklaas.py`.
- Tests: `scripts/tests/` (run via `uv run pytest`).
- Worked example: `examples/run-example.sh`.
