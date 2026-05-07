# syntherklaas

<p align="center">
  <img src="assets/sinterklaas.jpg" alt="De nieuwe Sint Nicolaas-prent — 18th-century print of Sinterklaas on horseback" width="640">
  <br>
  <sub><i>"De nieuwe Sint Nicolaas-prent" — Rijksmuseum, 18th century. Public domain via <a href="https://commons.wikimedia.org/wiki/File:De_nieuwe_Sint_Nicolaas-prent.jpg">Wikimedia Commons</a>.</i></sub>
</p>

Synthetic data pipeline as a [Claude Code](https://claude.ai/code) skill. Excel or CSV input → SQLite output, with consistent PII anonymization and intact foreign-key relationships.

Built on [Microsoft Presidio](https://github.com/microsoft/presidio) for column-level PII detection and [Faker](https://github.com/joke2k/faker) (`nl_NL` locale) for replacement values, with custom NL recognizers for BSN (with 11-proof checksum), Dutch IBAN, postcode, and phone formats.

## Installation

> Only tested with [Claude Code](https://claude.ai/code).

```bash
npx skills@latest add baswenneker/syntherklaas
```

After installation, restart Claude Code (or open a new session). The skill registers itself via `.claude-plugin/plugin.json`.

## Skills

| Category | Skill | Description |
| --- | --- | --- |
| engineering | [syntherklaas](skills/engineering/syntherklaas/SKILL.md) | Generate synthetic data from Excel (multi-tab) or a directory of CSVs into a SQLite database with consistent PII anonymization (names, emails, phone numbers, BSNs, postcodes, IBANs) and intact foreign-key relationships. |

## How to invoke

From Claude Code, either invoke directly:

```
/syntherklaas
```

Or describe the task — Claude triggers the skill via its description (matches phrases like *synthetic data*, *fake data*, *anonymize*, *Excel/CSV to SQLite*, *BSN-safe test data*):

> Anonymize `example_data/xlsx/example_data.xlsx` into `./demo.db`, capped at 50 root rows.

The skill loads its own instructions from `SKILL.md`, runs the pipeline (detect → resolve FKs → sample → anonymize → write), and reports per-column PII detection, FK resolution, row counts, and ID ranges.

## Try it on the bundled demo

A 3-table demo (50 klanten / 201 orders / 583 orderlines, with PII columns and meta-sheets) lives at the project root under `example_data/`:

```
example_data/
├── xlsx/example_data.xlsx       # Excel variant (3 data tabs + 2 meta tabs)
└── csv/                         # CSV-directory variant
    ├── klanten.csv
    ├── orders.csv
    ├── orderlines.csv
    ├── _relations.csv
    └── _pii_config.csv
```

Both are committed; regenerate them with:

```bash
bash skills/engineering/syntherklaas/examples/run-example.sh
```

That script regenerates the demo, runs both variants through the pipeline, and prints a JOIN sanity check showing fake Dutch names with their order counts. You can also point Claude at the demo files directly:

```
/syntherklaas
```
> "Run the pipeline on `example_data/xlsx/example_data.xlsx` into `./demo.db`."

### Example run on `example_data/csv/`

Invocation (no `--max-rows` cap, all input is processed):

```bash
bash skills/engineering/syntherklaas/scripts/run.sh \
  --input ./example_data/csv \
  --db ./tmp/example_data.db
```

Pipeline report:

```
PII detection:
  klanten.bsn: BSN
  klanten.email: EMAIL_ADDRESS
  klanten.naam: PERSON
  klanten.postcode: NL_POSTCODE
  klanten.telefoon: NL_PHONE
  orderlines: (none)
  orders: (none)

FK resolution:
  orderlines.order_id -> orders.id
  orders.klant_id -> klanten.id
Topological order: klanten -> orders -> orderlines

Row counts:
  klanten: 50 -> 50
  orderlines: 583 -> 583
  orders: 201 -> 201

Anonymized 250 unique values across 5 entity types:
  ['BSN', 'EMAIL_ADDRESS', 'NL_PHONE', 'NL_POSTCODE', 'PERSON']

SQLite write:
  klanten: 50 rows inserted (IDs 1..50)
  orderlines: 583 rows inserted (IDs 1..583)
  orders: 201 rows inserted (IDs 1..201)
```

Sample of `klanten` after the run:

```
$ sqlite3 -header -column ./tmp/example_data.db \
    "SELECT id, naam, email, bsn, telefoon, postcode FROM klanten LIMIT 5"

id  naam                     email                           bsn        telefoon     postcode
--  -----------------------  ------------------------------  ---------  -----------  --------
1   Tom Mulder               van-ommerenben@example.org      372941631  06-51510466  2365 HM
2   Liza van de Weterink     kde-bruin@example.org           219225060  06-07771090  0692 MX
3   Lisanne Oosterhek        ejones@example.com              750586461  06-45258652  3923 SU
4   Joy die Bont             ties93@example.org              951873246  06-36401889  5017 SZ
5   Dean Garret-de Strigter  dylanovan-boulogne@example.org  580059145  06-23231473  7801 JI
```

All five PII types are replaced (names → Dutch fakes, emails → `@example.{org,com}` with domain fully replaced, BSNs pass 11-proof checksum, phones in `06-XXXXXXXX` format, postcodes in `1234 XX` format). Foreign keys remain consistent: `orderlines.order_id → orders.id → klanten.id` joins still return the same logical pairs as the input, just with the fake names.

## Input format

- **Excel**: one tab per table. Optional meta-tabs `_relations` (FK overrides) and `_pii_config` (PII overrides).
- **CSV directory**: one file per table. Optional `_relations.csv` and `_pii_config.csv` in the same directory.

Override schemas:

```
_relations:    table | column | references_table | references_column
_pii_config:   table | column | pii_type         | strategy   (force | skip)
```

Resolution priority:

- **FKs**: existing DB schema (append-mode) > `_relations` > auto-infer (column-name `*_id` → match parent table).
- **PII**: `_pii_config` (force/skip) > Presidio auto-detection.

## PII coverage (v1)

| Type | Detection | Generation |
|------|-----------|------------|
| `PERSON` | Presidio NER (Spacy `nl_core_news_md`) | `Faker.name()` (nl_NL) |
| `EMAIL_ADDRESS` | Presidio regex | `Faker.email()` (domain fully replaced) |
| `NL_PHONE` / `PHONE_NUMBER` | Custom recognizer (06-/+31/0X0 formats) | Custom Faker provider (06-XXXXXXXX) |
| `BSN` | Custom recognizer (regex + 11-proof checksum) | Custom Faker provider (passes 11-proof) |
| `NL_IBAN` / `IBAN_CODE` | Custom recognizer (mod-97) | `Faker.iban()` |
| `NL_POSTCODE` | Custom recognizer (`1234 AB`) | Custom Faker provider |

Out of scope for v1: addresses (street/huisnr), dates of birth, credit cards, passport numbers.

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

The shared `entity_mapping` is the key to consistency: same input value always yields the same fake within a run, both across rows of one table and across tables (so a customer's anonymized name in `klanten.naam` matches their name in `orders.klant_naam`). FKs stay intact through per-table ID-offset rewriting; new IDs start at `MAX(id)+1` in append-mode.

## Tests

```bash
cd skills/engineering/syntherklaas/scripts
uv sync
uv run pytest -v
```

21 unit tests cover BSN 11-proof, anonymizer mapping consistency cross-row + cross-table, FK auto-inference + cyclic + composite detection, and SQLite ID-offset + FK rewrite + schema-mismatch.

## Adding more skills to this plugin

1. Create `skills/<category>/<skill-name>/SKILL.md` (YAML frontmatter `name`, `description`, plus a markdown body).
2. Bash helpers go in a sibling `scripts/` subfolder.
3. Register the skill folder in `.claude-plugin/plugin.json` under `skills`.
4. Add a row to the table above.

See [CLAUDE.md](CLAUDE.md) for repo conventions and [CONTEXT.md](CONTEXT.md) for shared vocabulary.

## Standalone CLI (without Claude Code)

If you want to run the pipeline directly without going through the skill:

```bash
cd skills/engineering/syntherklaas/scripts
uv sync
uv run python -m spacy download nl_core_news_md

uv run python syntherklaas.py \
  --input /path/to/data.xlsx \
  --db /path/to/output.sqlite \
  --max-rows 100
```

Exit codes: `0` ok, `2` schema mismatch, `3` cyclic / composite FK, `4` missing dependencies.

## Related

- [microsoft/presidio](https://github.com/microsoft/presidio) — PII detection and de-identification SDK.
- [joke2k/faker](https://github.com/joke2k/faker) — fake data generation, used here with the `nl_NL` locale.
- [baswenneker/fwd-skills](https://github.com/baswenneker/fwd-skills) — sibling skills plugin from which this repo borrows layout conventions.
- [mattpocock/skills](https://github.com/mattpocock/skills/tree/main) — the `skills` CLI used for installation and the layout pattern this repo follows.
