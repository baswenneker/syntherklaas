# CLAUDE.md

Repo-level instructions for agents working in `syntherklaas`.

## Purpose

`syntherklaas` is a single-skill Claude Code plugin: it ships one skill (`syntherklaas`) that builds a data model through an interactive dialog and generates synthetic data from scratch with Faker + numpy (locale-aware, plus NL-locked providers for BSN/IBAN/postcode/phone). Outputs CSV, XLSX (loose or multi-sheet), or SQLite. The supporting Python pipeline lives under the skill's `scripts/` folder; a schema-YAML is the boundary between the dialog (Claude in chat) and the deterministic generator (`generate.py`).

## Repo layout

```
.claude-plugin/plugin.json                          # Plugin manifest (skill paths)
skills/<skill-name>/                                # One folder per skill
  SKILL.md                                          # Required: YAML frontmatter + markdown body
  scripts/                                          # Bash entry + Python pipeline + tests
  examples/                                         # Demo schema-YAML + session transcript
CONTEXT.md                                          # Shared vocabulary
README.md                                           # Public-facing index
```

Skills follow the layout convention from [HeadingFWD/fwd-skills](https://github.com/baswenneker/fwd-skills): one folder per skill under `skills/`, registered in `.claude-plugin/plugin.json`. Unlike `fwd-skills`, this repo does **not** prefix skill names with `fwd:` — the skill is named `syntherklaas` plain (folder name matches frontmatter `name` exactly, so the slash command is `/syntherklaas`).

## Adding a skill

1. Create `skills/<skill-name>/SKILL.md` with frontmatter:

   ```markdown
   ---
   name: <skill-name>
   description: <one paragraph describing what it does and when to invoke>
   ---
   ```

   The `description` is what Claude Code uses to decide when the skill is relevant — be specific about trigger phrases and use cases.

2. Add the skill's folder path to the `skills` array in `.claude-plugin/plugin.json`.
3. Update the skills table in `README.md`.

## Conventions

- **Folder name matches `name` frontmatter exactly.** The slash command is `/<name>`.
- `SKILL.md` is the entry point; supporting code lives in sibling folders (`scripts/`, `examples/`).
- **Python pipelines use `uv`.** Each skill's `scripts/pyproject.toml` declares its own deps; the bash glue (`scripts/run.sh`) handles first-run install via `uv sync`.
- **Bash helpers go in `scripts/`**, referenced from `SKILL.md` via `${CLAUDE_SKILL_DIR}/scripts/<name>.sh`.
- **All git commands route through `rtk git`** (no plain `git` fallback) where the rtk hook is configured.
- See [CONTEXT.md](CONTEXT.md) for project vocabulary.

<!-- fwd:lessons:start -->
## Lessons

Persistent memory across sessions. Location: `.claude/lessons/LESSONS.md`.

**When to consult** (you decide):
- At the start of substantial work
- When uncertain about an approach or convention
- When the user references earlier work or a prior agreement

**When to append** (proactively, without asking):
- After a user correction ("no", "stop", "don't do X")
- When a surprise pattern is valuable across sessions
- When a rule, convention, or vocabulary you should have known is missing

**Format** (strict):

````
### YYYY-MM-DD | <type> | <scope>
**Context**: [what was happening]
**Observation**: [what went wrong / was observed]
**Lesson**: [what to do next time]
````

Types: `correction` | `insight` | `rule-gap` | `deviation`. Scope: skill, area, or `general`.

Use the Write tool to append to the bottom of `.claude/lessons/LESSONS.md`. If the file doesn't exist: create it with a header + format block.
<!-- fwd:lessons:end -->
