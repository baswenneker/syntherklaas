# CONTEXT.md

Shared vocabulary for the `syntherklaas` repo. Keeps terminology consistent across skills, READMEs, and future ADRs.

## Vocabulary

### PII (Personally Identifiable Information)
A column whose values uniquely or strongly identify a person — names, email addresses, phone numbers, BSNs, postcodes, IBANs. The pipeline replaces these consistently within a run.

### Entity mapping
The in-memory dict `Dict[entity_type, Dict[original, fake]]` shared across all tables in a single run. A cache hit returns the existing fake; a miss generates a new one via Faker. Cleared at the end of each run — no cross-run persistence.

### Foreign-key consistency
After anonymization, joins between tables must still return the same logical pairs as in the input. Achieved via per-table `id_map` built during writes: parent rows get new IDs at `MAX(id)+1..n`, and child FK columns are rewritten via `df[fk] = df[fk].map(parent_id_map)`.

### Root table
A table with no outgoing foreign keys (i.e., it doesn't depend on any other table). `--max-rows N` caps root tables to first N rows; child tables follow via FK-filter (rows whose FK is in the sampled-parent set).

### Override sheet
A meta-table delivered alongside the data — `_relations` for FK declarations, `_pii_config` for PII type forcing or skipping. Lives inline in the input package (extra Excel tab, or extra CSV in the same directory). Distinguished by the leading underscore.

### Append mode
**(SQLite output only.)** Writing to an existing SQLite DB without PK collisions. The pipeline reads `MAX(id)` per table, assigns new output IDs starting after that, and rewrites child FK columns to point at the new parent IDs. Schema mismatch fails fast with exit code 2. XLSX output is new-only — `--mode append` combined with `.xlsx` exits with code 2.
