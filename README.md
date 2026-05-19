# Syntherklaas: interactive synthetic data generator

<p align="center">
  <img src="assets/sinterklaas.jpg" alt="Sinterklaas waving to the crowd during an intocht, wearing his red and gold mitre and purple gloves" width="640">
</p>

Real data is the fastest way to prototype.<br>
GDPR is the fastest way to get blocked.

A good synthetic dataset is a gift — and you don't have to wait until December.

## The problem

On most projects the first question is: *what data do you have?* And the answer is usually "none", "not enough", or "we have it but GDPR makes it off-limits".

`syntherklaas` skips the input-data step entirely: you have a short conversation about the shape you need — tables, columns, foreign keys, volumes, distributions — and it generates a coherent synthetic dataset from scratch.

Built on [Faker](https://github.com/joke2k/faker) (locale-aware) plus NL-locked providers for BSN (11-proof), IBAN (mod-97), postcode, and phone formats — fake values that still pass real validators. Packaged as a [Claude Code](https://claude.ai/code) skill: the dialog runs in chat, the schema is captured as a YAML, and a small Python generator turns that YAML into CSV, XLSX, SQLite, or a SQL dump.

## Watch the 2-minute intro

<p align="center">
  <a href="https://www.veed.io/view/f6d1d1f5-75e0-480e-b185-d39974822b73">
    <img src="assets/intro-thumbnail.png" alt="Watch the 2-minute intro: a quick tour through a full syntherklaas session" width="744">
  </a>
</p>

**[▶ Watch on Veed](https://www.veed.io/view/f6d1d1f5-75e0-480e-b185-d39974822b73)** — a quick tour: define two related tables, see the data model, pick volume distributions, and pick an output format.

## Installation

> Only tested with [Claude Code](https://claude.ai/code).

```bash
npx skills@latest add baswenneker/syntherklaas
```

Restart Claude Code (or open a new session). The skill registers via `.claude-plugin/plugin.json`.

## What a conversation looks like

The dialog *is* the product. You name the tables and columns; Claude picks the providers, infers the foreign keys, renders the model, and asks the right follow-ups. Here's a session — slightly compressed, but faithful to the real flow.

> **You:** `/syntherklaas`
>
> **Claude:** Which table do we start with? You can paste sample data, define columns together, or just give me a table name and I'll propose one.
>
> **You:** `users` — `user_id, first_name, last_name, bsn, email`
>
> **Claude:** Inferred for `users`:
>
> | col          | provider           | constraint | example       |
> |--------------|--------------------|------------|---------------|
> | user_id      | `sequential`       | PK         | 1, 2, 3, ...  |
> | first_name   | `faker.first_name` |            | Pieter        |
> | last_name    | `faker.last_name`  |            | Jansen        |
> | bsn          | `nl.bsn`           | UNIQUE     | 391171823     |
> | email        | `faker.email`      |            | x@example.com |
>
> Look right? (`ok` / `change <col>`)
>
> **You:** ok. Next: `invoices` — `invoice_id, user_id, description, amount, iban`
>
> **Claude:** Inferred for `invoices`:
>
> | col          | provider                  | constraint  | example          |
> |--------------|---------------------------|-------------|------------------|
> | invoice_id   | `sequential`              | PK          | 1, 2, 3, ...     |
> | user_id      | `fk` → `users.user_id`    | NOT NULL    | 1..1000          |
> | description  | `faker.text`              |             | "Lorem ipsum..." |
> | amount       | `numeric_range` (uniform) |             | 137.42           |
> | iban         | `nl.iban`                 |             | NL34RABO0382...  |
>
> Model so far:
>
> ```
> ┌─────────────────────────┐         ┌─────────────────────────┐
> │ users                   │ 1     * │ invoices                │
> ├─────────────────────────┤─────────┤─────────────────────────┤
> │ user_id (PK)   INT      │         │ invoice_id (PK)  INT    │
> │ first_name     STR      │         │ user_id (FK)     INT ───┤
> │ last_name      STR      │         │ description      STR    │
> │ bsn (UQ)       STR      │         │ amount           FLOAT  │
> │ email          STR      │         │ iban             STR    │
> └─────────────────────────┘         └─────────────────────────┘
> ```
>
> Another table, or done?
>
> **You:** done.
>
> **Claude:** Volumes per table — pick a distribution:
>
> - **Fixed** — exact row count
> - **Poisson λ** — natural variation around λ (e.g. *"around 5 invoices per user"*)
> - **Normal μ ± σ** — bell-shaped
> - **Uniform [min, max]** — or just describe it in words
>
> How many `users`? And how many `invoices` per user?
>
> **You:** 1000 users; around 5 invoices per user.
>
> **Claude:** Preview (10 rows per table)...
>
> ```
> users (1000 total)
> | user_id | first_name | last_name        | bsn       | email                  |
> | 1       | Ali        | Schellekens      | 391171823 | leonholthuis@example…  |
> | 2       | Finn       | Jansdr-Goyaerts  | 278248962 | molenvigo@example.net  |
> | ...
> ```
>
> Output format? CSV / XLSX / SQLite / PostgreSQL or MSSQL SQL dump.
>
> **You:** sqlite, `./demo.db`
>
> **Claude:** Wrote sqlite → `./demo.db`
>   users: 1000 rows
>   invoices: 4983 rows
>
> Save this schema for re-use? (path, or `no`)
>
> **You:** `./demo-schema.yaml`
>
> **Claude:** Saved. Next time, `/syntherklaas ./demo-schema.yaml` reproduces this exact dataset — same seed, same rows.

You don't need to know the YAML format to use it: the dialog writes it for you. A saved schema is just the receipt — re-runnable, diff-able, version-controllable.

## Skills

| Skill | Description |
| --- | --- |
| [syntherklaas](skills/syntherklaas/SKILL.md) | Interactive synthetic data generator. Builds a data model through dialog, generates with Faker + NL extras, outputs CSV/XLSX/SQLite. Saved schemas re-run with one confirmation. |

## How to invoke

From Claude Code:

```
/syntherklaas
```

…starts the full dialog. Or pass a saved schema YAML to skip the dialog:

```
/syntherklaas ./demo-schema.yaml
```

## Run the bundled example

A 3-tier schema (klanten / orders / orderlines) with FKs, distributions, and categorical weights lives in [`skills/syntherklaas/examples/demo-schema.yaml`](skills/syntherklaas/examples/demo-schema.yaml).

Run it directly:

```bash
bash skills/syntherklaas/scripts/run.sh \
  --schema skills/syntherklaas/examples/demo-schema.yaml \
  --preview
```

Or generate the full SQLite output (the YAML already declares `output.format: sqlite` and `output.path: ./demo.db`):

```bash
bash skills/syntherklaas/scripts/run.sh \
  --schema skills/syntherklaas/examples/demo-schema.yaml
```

A sample of `klanten` after the run:

```
$ sqlite3 -header -column ./demo.db \
    "SELECT id, naam, bsn, postcode, leeftijd FROM klanten LIMIT 5"

id  naam                              bsn        postcode  leeftijd
--  --------------------------------  ---------  --------  --------
1   Ali Schellekens                   391171823  4471 VH         47
2   Finn Jansdr-Goyaerts van Waderle  278248962  4936 DR         26
3   Melle van Brenen                  383465783  3242 CB         53
4   Amin Gellemeyer                   839301030  2499 JO         56
5   Floris van de Elzas-Blonk         105183477  1746 IQ         18
```

BSNs pass the 11-proof checksum, postcodes match `1234 XX`, phone numbers are 06-format, and `orders.klant_id` is guaranteed to reference an existing `klanten.id`.

Walk through a full session transcript at [`skills/syntherklaas/examples/transcript.md`](skills/syntherklaas/examples/transcript.md).

## Schema-YAML (the receipt)

A saved schema looks like this — short enough to grasp at a glance:

```yaml
version: 1
locale: nl_NL          # any Faker locale; default nl_NL
seed: 42               # optional; derived from schema bytes if omitted

output:                # optional; preset for re-invoke
  format: sqlite
  path: ./demo.db

tables:
  - name: users
    columns:
      - { name: id,    provider: sequential, primary_key: true }
      - { name: naam,  provider: faker.name }
      - { name: bsn,   provider: nl.bsn, unique: true }
    volume:
      count: { distribution: fixed, value: 1000 }
```

For the full surface — `numeric_range` with `normal`/`lognormal`/`exponential`, `categorical` with `weights`, `datetime_range`, `per_parent` child volumes, conditional `when` clauses — see the worked example: [`skills/syntherklaas/examples/demo-schema.yaml`](skills/syntherklaas/examples/demo-schema.yaml).

## Providers

| Provider                | Locale-aware? | What it emits                                    |
|-------------------------|:-------------:|---------------------------------------------------|
| `sequential`            | n.v.t.        | Auto-increment int (PK)                           |
| `fk`                    | n.v.t.        | Random pick from a parent table's ID column       |
| `faker.<method>`        | ✅            | Any callable on a `Faker` instance — `name`, `email`, `address`, `phone_number`, `company`, `text`, ... |
| `nl.bsn`                | ❌ NL-locked  | 11-proof BSN                                      |
| `nl.iban`               | ❌ NL-locked  | NL IBAN with mod-97 checksum                      |
| `nl.postcode`           | ❌ NL-locked  | `1234 AB`                                         |
| `nl.phone`              | ❌ NL-locked  | `06-XXXXXXXX`                                     |
| `nl.tussenvoegsel`      | ❌ NL-locked  | Surname-infix (`van der`, `de`, ...)              |
| `numeric_range`         | n.v.t.        | int/float; distributions: `uniform`, `normal`, `lognormal`, `exponential` |
| `categorical`           | n.v.t.        | Choice with optional weights                      |
| `datetime_range`        | n.v.t.        | Datetime in `[start, end]`; `uniform` or `normal` |

## Output formats

| Format       | `--output` is...         | Notes                                                  |
|--------------|--------------------------|--------------------------------------------------------|
| `csv-loose`  | a (new/empty) directory  | One `<table>.csv` per table                            |
| `xlsx-loose` | a (new/empty) directory  | One `<table>.xlsx` per table; per-sheet row limit applies |
| `xlsx-multi` | a (new) `.xlsx` file     | One multi-sheet workbook; topological sheet order; frozen header |
| `sqlite`     | a (new) `.db`/`.sqlite`  | Bulk insert; no FK constraints in DDL (FKs are correct by construction) |
| `postgres`   | a (new) `.sql` file      | PostgreSQL dialect: `CREATE TABLE` (with `PRIMARY KEY` / `UNIQUE` / `REFERENCES`) + batched `INSERT INTO`, wrapped in `BEGIN; ... COMMIT;` |
| `mssql`      | a (new) `.sql` file      | Microsoft SQL Server dialect: identical structure to `postgres` but with `[bracket]` identifiers, `N'...'` string literals, `BIT`/`NVARCHAR(MAX)`/`DATETIME2` types |

No append modes. The output target must be free (file: doesn't exist; directory: empty or doesn't exist).

## Exit codes

- `0` — success
- `2` — schema/output/format problem (malformed YAML, unknown provider, FK to unknown column, output already exists, Excel row/sheet-name limit exceeded, ...)
- `3` — cyclic FK detected
- `4` — missing `uv` on PATH

## Tests

```bash
cd skills/syntherklaas/scripts
uv sync
uv run pytest
```

Unit tests cover providers + validators (BSN 11-proof, NL IBAN mod-97, NL postcode/phone pattern), distributions (statistical mean/range checks on 1k–10k samples), schema validation (happy paths + every error branch), generation (rowcounts, FK integrity, determinism), writers (round-trip per format, output-exists guards, Excel limits).

## Standalone CLI (without Claude Code)

```bash
cd skills/syntherklaas/scripts
uv sync

# Preview-only (JSON to stdout)
uv run python generate.py --schema <yaml-path> --preview

# Write
uv run python generate.py --schema <yaml-path> --output ./out.db --format sqlite
```

The same `bash run.sh` wrapper handles the first-run `uv sync`; pass any of the flags through.

## Adding more skills to this plugin

1. Create `skills/<skill-name>/SKILL.md` (YAML frontmatter `name`, `description`, plus a markdown body).
2. Bash helpers go in a sibling `scripts/` subfolder.
3. Register the skill folder in `.claude-plugin/plugin.json` under `skills`.
4. Add a row to the table above.

See [CLAUDE.md](CLAUDE.md) for repo conventions and [CONTEXT.md](CONTEXT.md) for shared vocabulary.

## Related

- [joke2k/faker](https://github.com/joke2k/faker) — fake data generation; used here locale-aware (`nl_NL` default).
- [baswenneker/fwd-skills](https://github.com/baswenneker/fwd-skills) — sibling skills plugin from which this repo borrows layout conventions.
- [mattpocock/skills](https://github.com/mattpocock/skills/tree/main) — the `skills` CLI used for installation and the layout pattern this repo follows.
