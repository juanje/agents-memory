# File formats

Reference formats for all memory files. Used by /save and session-start
to generate consistent, predictable content.

---

## projects/index.md (registry)

One line per project. Updated every /save.

```
# Projects

- projects/<name>/index.md — <one-line description> (<stack>, <team>)
```

---

## projects/<name>/index.md (project hub)

Lean summary. ~30-50 lines for simple projects, ~80 max for complex ones.
If CLAUDE.md exists in the project, don't duplicate — complement with
cross-session knowledge (decisions, patterns learned, relationships).

```
# <project-name>

<1-3 line description of what the project is and does.>

- Stack: <language/platform>
- Team: <team name>
- Last session: YYYY-MM-DD

## Related projects

- projects/<other>/index.md — <how it relates to this project>

## Files

- latest-sessions.md — summaries of the most recent sessions
- open-threads.md — unfinished work, pending questions
- logs/index.md — session history
```

The "Related projects" section is added/updated by /save or daily when
cross-project context is discovered. Only include genuinely related
projects — not every project the user has.

---

## projects/<name>/latest-sessions.md

Rolling window of the 3 most recent session summaries. Self-managed by
/save — the daily cycle does NOT rewrite or merge this file, only validates
its format.

Each /save prepends a new section at the top. If > 3 sections, the oldest
(bottom) is removed. Each section answers: what was the session about, what
was done and why, what decisions were made, what's still pending.

```
# Latest sessions

## YYYY-MM-DD ~HH:MM

<4-6 lines of prose. What the session was about, what was done and why,
key decisions with reasoning, what was left pending. Enough context for
an agent to understand where things stand without reading the full log.>

> To continue this work, read projects/<name>/logs/YYYY-MM-DD.md first.

---

## YYYY-MM-DD ~HH:MM

<previous session summary>

> To continue this work, read projects/<name>/logs/YYYY-MM-DD.md first.
```

Empty state (detected by session-start as "nothing to show"):

```
# Latest sessions

(No sessions recorded yet. Use /save when done.)
```

**Migration from last-session.md:** If `last-session.md` exists but
`latest-sessions.md` doesn't, the first /save reads the old file,
converts its content into the oldest entry in the new format, writes
`latest-sessions.md`, and deletes `last-session.md`.

---

## projects/<name>/context.md

Project context: architecture, stack, key components, current state.
Append-only during daily consolidation — the daily cycle only adds new
information, never rewrites or removes existing content. Monthly may
compact old entries.

**Update rules for daily consolidation:**

1. **Add** new information from recent logs with a date marker:
   `(learned YYYY-MM-DD)`. New components, dependencies, integrations,
   architectural details.
2. **Do not change or remove** existing content that is still valid,
   even if the wording could be improved. Stability > prose quality.
3. **Change or remove only with explicit evidence** from a log: "stopped
   using X", "migrated from A to B", "removed module Y". When updating,
   keep the previous state inline with the change date and reason:
   `Migrations: alembic (changed 2026-05-17 — was raw SQL, switched after stabilizing schema)`

**Monthly compaction:** When the file grows too large, the monthly cycle
may compress old entries (remove inline change history older than 3
months, consolidate related entries). The original logs exist as backup.

```
# Context — <project-name>

## Architecture

- <Component or layer> — <what it does> (learned YYYY-MM-DD)
- <Another component> (learned YYYY-MM-DD)

## Stack

- FastAPI + SQLAlchemy + PostgreSQL (learned 2026-04-15)
- Migrations: alembic (changed 2026-05-17 — was raw SQL, switched after stabilizing schema)
- ruff for linting (learned 2026-04-15)

## Current state

- <What's deployed, what's in progress> (learned YYYY-MM-DD)
```

---

## projects/<name>/open-threads.md

Overwritten every /save (merge new, remove resolved).

```
# Open threads

- <Thread description. Specific enough to pick up without extra context.
  Include the WHY if not obvious.>
- <Another thread.>
```

Empty state (detected by session-start as "nothing to show"):

```
# Open threads

(None.)
```

---

## projects/<name>/logs/index.md

Table of sessions. One row per /save invocation.

```
# Session logs — <project-name>

| Date | Summary |
|---|---|
| YYYY-MM-DD | <one-line summary of what happened> |
```

---

## projects/<name>/logs/YYYY-MM-DD.md

Session log. Appended if multiple /save on the same day. Skip empty sections.

```
# YYYY-MM-DD

## Decisions

- <What was decided and why.>

## Corrections

- <What was wrong and what's right.>

## Learnings

- <Patterns discovered, things that work, gotchas.>

## Open threads

- <Unfinished work carried to open-threads.md.>
```

---

## stacks/<stack>/index.md

Standards for this language/platform. Grows over time via /save promotions.

```
# Stack: <name>

<1-2 line description.>

## Key standards

- <Standard and tool> (not <alternative>)
- ...

## Patterns

- <Pattern: library or approach used>
- ...
```

---

## teams/<team>/index.md

Team conventions and processes.

```
# Team: <name>

<1-2 line description of the team.>

## Conventions

- <Convention or process>
- ...

## Services and tools

- <Service name> (<what it's for>)
- ...
```

---

## global/preferences.md

Universal preferences across all projects.

```
# Preferences

## <Category>

- <Preference>
- ...
```
