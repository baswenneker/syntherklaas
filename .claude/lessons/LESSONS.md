# Lessons

Persistent learnings from prior sessions. Append-only, newest at the bottom.

## Format

````
### YYYY-MM-DD | <type> | <scope>
**Context**: ...
**Observation**: ...
**Lesson**: ...
````

- **type**: correction | insight | rule-gap | deviation
- **scope**: free-form — skill (e.g. `fwd:git-commit`), area (`engineering`), or `general`

## Entries

<!-- new entries appended below -->

### 2026-05-14 | correction | syntherklaas
**Context**: In the `syntherklaas` Phase 3 dialog I jumped straight into an `AskUserQuestion` for "Hoeveel `<tabel>`?" with options like `Vast 200`, `Poisson λ=300`, `Normal 500±100`, `Uniform 100-1000`. The user only saw the options and labels — no explanation of what each distribution means or when to pick which.
**Observation**: Even when one of the options is the obvious "Vast N" (concrete number), the user wants a primer first so the alien options (`poisson`, `normal`, `uniform`) are intelligible. Diving straight into `AskUserQuestion` with jargon-laden options feels abrupt.
**Lesson**: For any `AskUserQuestion` whose options use domain jargon or statistical terms the user might not parse at a glance, **first send a short plain-text intro** that names what we're about to decide and explains each option in one line. Then fire the `AskUserQuestion`. Applies inside `syntherklaas` Phase 3 (volume + distributies, datetime/numeric ranges, categorical weights) and to any future skill dialog with similarly non-obvious options.
