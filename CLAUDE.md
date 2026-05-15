Generate coherent fake datasets with this AI skill, and export it to xlsx, csv, sqlite or sql.

Skill: [`syntherklaas`](skills/syntherklaas/SKILL.md). Vocab: [CONTEXT.md](CONTEXT.md).

## Conventions

- Folder name = `name` frontmatter -> `/syntherklaas`.
- Python via `uv`. Deps: `skills/syntherklaas/scripts/pyproject.toml`. First run: `scripts/run.sh` -> `uv sync`.
- Bash helpers in `scripts/`. Ref via `${CLAUDE_SKILL_DIR}/scripts/<name>.sh`.
- Git via `rtk git`. No plain `git`.

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
