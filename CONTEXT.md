# CONTEXT.md

Shared vocabulary for the `syntherklaas` repo. Keeps terminology consistent across the skill, README, and future ADRs.

## Vocabulary

### Schema-YAML
The single source of truth for one `syntherklaas` run: tables + columns + providers + volume + locale + seed + optional `output` block. Built interactively (via dialog) or hand-written. Determinism is anchored to it: same YAML + same code = bit-identical output. Lives ephemerally in `/tmp/syntherklaas-<sessid>/` during a session; user may copy it elsewhere via the save-step at the end of the dialog.

### Provider
The generator strategy for one column. Three families:

- **Native**: `sequential` (auto-increment PK), `fk` (random pick from a parent table's IDs), `categorical` (choice list with optional weights), `numeric_range` (int/float with `uniform | normal | lognormal | exponential`), `datetime_range` (timestamp in a window with `uniform | normal`).
- **`faker.<method>`**: locale-aware Faker call (`faker.name`, `faker.email`, `faker.phone_number`, `faker.address`, `faker.company`, `faker.text`, ...). Follows the session `locale`.
- **`nl.<name>`**: NL-locked extras — `nl.bsn` (11-proof), `nl.iban` (mod-97 NL), `nl.postcode` (`1234 AB`), `nl.phone` (06-XXXXXXXX), `nl.tussenvoegsel`. **Unaffected by session locale** — BSN/IBAN/postcode are NL concepts; they always emit NL-format values even when `locale: en_US`.

### Volume-spec
How many rows a table produces. Two shapes:

- `count: { distribution, ... }` — total row count for the table (typical for root tables).
- `per_parent: { parent, distribution, ... }` — for each parent row, draw a child-count from the distribution. Total = sum of draws.

Allowed count distributions: `fixed`, `uniform`, `normal`, `poisson`. Distribution-specific params (`value`, `min/max`, `mean/stddev`, `lambda`) are required per type.

### Distributie-spec
Per-column draws for stochastic providers:

- `numeric_range`: `uniform` (min/max), `normal` (mean/stddev, clipped to min/max), `lognormal` (mean/sigma), `exponential` (scale).
- `datetime_range`: `uniform` over the window, or `normal` centered in the window (stddev = window/6 so ~±3σ covers it).
- `categorical`: `weights` (same length as `choices`, normalized internally).

### Session-locale
Top-level `locale: <Faker-locale>` (default `nl_NL`). Drives `faker.*` providers; ignored by `nl.*` providers and native providers. Changing locale produces different name/email/address outputs from the same seed.

### Deterministic seed
`seed: <int>` in YAML, or derived from `SHA256(schema-bytes)[:8]` when absent. Drives both numpy (`Generator`) and Faker (`seed_instance`). Identical schema → identical output, every time.

### Re-invoke path
`/syntherklaas <path-to-schema.yaml>` — the skill detects the YAML argument, skips the dialog, shows a confirmation summary + 10-row preview, then runs generation. Output format/path come from the YAML's `output` block (if present) or are asked at confirmation time.

### FK overdracht
For child tables: the generator iterates parent rows and emits FK values pointing at the correct parent IDs. With `per_parent`, the child rows are grouped by parent (parent_1, parent_1, ..., parent_2, parent_2, ...). With `count`, FK values are uniform-random picks across all parent IDs. No post-hoc remapping — IDs are correct by construction.
