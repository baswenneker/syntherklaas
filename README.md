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
  <iframe src="https://www.veed.io/embed/320d6102-79cd-41a5-bc89-a5df8c4dcd95?watermark=0&color=purple&sharing=0&title=0" width="744" height="504" frameborder="0" title="syntherklaas intro" webkitallowfullscreen mozallowfullscreen allowfullscreen></iframe>
</p>

**[▶ Watch on Veed](https://www.veed.io/view/320d6102-79cd-41a5-bc89-a5df8c4dcd95/089cd154-4be1-4141-8433-f86e369f2c20)** — a quick tour: define two related tables, see the data model, pick volume distributions, and pick an output format.

## Installation

> Only tested with [Claude Code](https://claude.ai/code).

```bash
npx skills@latest add baswenneker/syntherklaas
```

Restart Claude Code (or open a new session). The skill registers via `.claude-plugin/plugin.json`.

## How it feels in a session

1. **Start the skill**

   ```
   /syntherklaas
   ```

2. **Define your first table** — for example `users` with `user_id, first_name, last_name, bsn, email`. Faker handles name + email; `nl.bsn` produces 11-proof BSNs.

3. **Add related tables** — for example `invoices` with `user_id`, description, amount, IBAN. The `user_id` column is auto-detected as an FK to `users.id`; `iban` gets `nl.iban` (mod-97).

4. **Review the data model** — Claude renders an ASCII UML diagram with cardinality. Looks right? Continue. Otherwise: correct a table.

5. **Pick volumes per table** — for each table, choose one of four distributions:
   - **Fixed** (e.g. `1000` users)
   - **Poisson** with λ (e.g. "around 5 invoices per user")
   - **Normal** with μ ± σ
   - **Uniform** in `[min, max]` — or just describe it in your own words and Claude maps it to the right distribution.

6. **Preview** — 10 rows per table, rendered in chat.

7. **Pick an output format** — CSV, XLSX (loose or multi-sheet), SQLite, or a PostgreSQL / MSSQL SQL dump. Or just say what you want; Claude picks the right flag.

8. **Save the schema (optional)** — store the YAML at a path of your choice. Next time, `/syntherklaas <path>` reproduces the exact same dataset (deterministic seed).

```mermaid
flowchart LR
    subgraph dialog["Dialog (Claude in chat)"]
        P0["locale"]
        P1["tables + columns + FKs"]
        P2["ASCII UML"]
        P3["volume + distributions"]
    end
    Y["schema.yaml"]
    G["<b>generate.py</b><br/>Faker + numpy<br/>(seeded)"]

    subgraph out["Output"]
        O1["CSV<br/>(loose files)"]
        O2["XLSX<br/>(loose or multi-sheet)"]
        O3["SQLite<br/>(.db / .sqlite)"]
    end

    dialog --> Y
    Y --> G
    G --> O1
    G --> O2
    G --> O3
```

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

## Schema-YAML format

```yaml
version: 1
locale: nl_NL          # default; any Faker locale (en_US, de_DE, ...)
seed: 42               # optional; otherwise SHA256(schema)[:8] as int

output:                # optional; preset for re-invoke
  format: sqlite       # csv-loose | xlsx-loose | xlsx-multi | sqlite
  path: ./demo.db

tables:
  - name: users
    columns:
      - { name: id,    provider: sequential, primary_key: true }
      - { name: naam,  provider: faker.name }
      - { name: bsn,   provider: nl.bsn,    unique: true }
      - { name: email, provider: faker.email }
      - name: leeftijd
        provider: numeric_range
        type: int
        min: 18
        max: 80
        distribution: normal
        mean: 42
        stddev: 15
      - name: status
        provider: categorical
        choices: [active, inactive, suspended]
        weights: [0.8, 0.15, 0.05]
    volume:
      count: { distribution: fixed, value: 100 }

  - name: events
    columns:
      - { name: id,        provider: sequential, primary_key: true }
      - { name: user_id,   provider: fk, references: users.id }
      - name: occurred_at
        provider: datetime_range
        start: "2024-01-01"
        end:   "2024-12-31"
        distribution: uniform
    volume:
      per_parent:
        parent: users
        distribution: poisson
        lambda: 20
        min: 1
```

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
