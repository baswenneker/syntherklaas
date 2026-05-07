# syntherklaas

Synthetic data pipeline for Excel / CSV → SQLite, with consistent PII anonymization and intact foreign keys.

A Claude Code skill (and standalone Python CLI) that takes business-shaped input — an Excel file with multiple tabs, or a directory of CSV files — detects personally identifiable information per column, replaces every PII value with a coherent fake (the same input always maps to the same fake within a run, across rows and across tables), and writes the result to a SQLite database while preserving foreign-key relationships via per-table ID-offset rewriting.

Built on [Microsoft Presidio](https://github.com/microsoft/presidio) for column-level PII detection, [Faker](https://github.com/joke2k/faker) (`nl_NL` locale) for fake values, and custom NL recognizers for BSN (with 11-proof checksum), Dutch IBAN, postcode, and phone formats.

## Skills

| Category | Skill | Description |
| --- | --- | --- |
| engineering | [syntherklaas](skills/engineering/syntherklaas/SKILL.md) | Generate synthetic data from Excel (multi-tab) or a directory of CSVs into a SQLite database with consistent PII anonymization and intact foreign-key relationships. |

## Quick start

```bash
cd skills/engineering/syntherklaas/scripts

# First run only: install deps + Spacy NL model
uv sync
uv run python -m spacy download nl_core_news_md

# Anonymize an Excel file into a new SQLite DB
uv run python syntherklaas.py \
  --input ./mydata.xlsx \
  --db ./mydata.sqlite

# CSV directory + cap to 100 root rows
uv run python syntherklaas.py \
  --input ./mydata/ \
  --db ./mydata.sqlite \
  --max-rows 100

# Append to existing DB
uv run python syntherklaas.py \
  --input ./more.xlsx \
  --db ./existing.sqlite \
  --mode append
```

The bundled `scripts/run.sh` does the install on first invocation and then forwards to the CLI. Use it from Claude Code via `${CLAUDE_SKILL_DIR}/scripts/run.sh ...`.

## Try it on the demo

```bash
bash skills/engineering/syntherklaas/examples/run-example.sh
```

Generates a 3-table demo (50 klanten / 201 orders / 583 orderlines) with PII columns, runs both Excel and CSV variants of the input through the pipeline, and prints a JOIN sanity check showing fake Dutch names with their order counts.

## Pipeline

```
Input (xlsx tabs / csv dir + optional _relations / _pii_config)
   │
   ▼
1. Detect PII columns         (Presidio + custom NL recognizers + override)
2. Resolve FKs (topo-sort)    (DB-schema > _relations > auto-infer)
3. Sample (cap-only first-N)  (children follow via FK-filter)
4. Anonymize PII              (FakerAnonymizer with shared entity_mapping)
5. Write to SQLite            (ID-offset + FK rewrite, schema-mismatch fail-fast)
   │
   ▼
SQLite + human-readable report
```

## Input format

- **Excel**: one tab per table. Optional meta-tabs `_relations` (FK overrides) and `_pii_config` (PII overrides).
- **CSV directory**: one file per table. Optional `_relations.csv` and `_pii_config.csv` in the same directory.

Override schemas:

```
_relations:    table | column | references_table | references_column
_pii_config:   table | column | pii_type         | strategy   (force | skip)
```

Resolution priority for FKs: existing DB schema (append-mode) > `_relations` > auto-infer.
Resolution priority for PII: `_pii_config` (force/skip) > Presidio auto-detection.

## PII coverage (v1)

| Type | Detection | Generation |
|------|-----------|------------|
| `PERSON` | Presidio NER (Spacy `nl_core_news_md`) | `Faker.name()` (nl_NL) |
| `EMAIL_ADDRESS` | Presidio regex | `Faker.email()` |
| `NL_PHONE` / `PHONE_NUMBER` | Custom recognizer (06-/+31/0X0 formats) | Custom Faker provider (06-XXXXXXXX) |
| `BSN` | Custom recognizer (regex + 11-proof) | Custom Faker provider (passes 11-proof) |
| `NL_IBAN` / `IBAN_CODE` | Custom recognizer (mod-97) | `Faker.iban()` |
| `NL_POSTCODE` | Custom recognizer (`1234 AB`) | Custom Faker provider |

Out of scope for v1: addresses (street/huisnr), dates of birth, credit cards, passport numbers.

## Tests

```bash
cd skills/engineering/syntherklaas/scripts
uv run pytest -v
```

21 unit tests covering BSN 11-proof, anonymizer mapping consistency cross-row + cross-table, FK auto-inference + cyclic + composite detection, and SQLite ID-offset + FK rewrite + schema-mismatch.

## Adding more skills

1. Create a new folder under `skills/<category>/<skill-name>/` with a `SKILL.md` (YAML frontmatter `name`, `description`, plus a markdown body).
2. Bash helpers go in a sibling `scripts/` subfolder.
3. Register the skill folder in `.claude-plugin/plugin.json` under `skills`.
4. Add a row to the table above.

## Exit codes

- `0` — success
- `2` — schema mismatch or invalid `--mode` against existing DB
- `3` — cyclic or composite FK detected
- `4` — missing dependencies (uv / spacy model)

## Related

- [microsoft/presidio](https://github.com/microsoft/presidio) — PII detection and de-identification SDK.
- [joke2k/faker](https://github.com/joke2k/faker) — fake data generation, used here with `nl_NL` locale.
- [HeadingFWD/fwd-skills](https://github.com/baswenneker/fwd-skills) — sibling skills plugin from which this repo borrows layout conventions.
