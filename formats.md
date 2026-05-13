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

- last-session.md — summary of the most recent session
- open-threads.md — unfinished work, pending questions
- logs/index.md — session history
```

The "Related projects" section is added/updated by /save or daily when
cross-project context is discovered. Only include genuinely related
projects — not every project the user has.

---

## projects/<name>/last-session.md

Accumulates session blocks during the day; consolidated overnight.
Each /save appends a block if the date matches, or overwrites if it's a new day.

```
# Last session — YYYY-MM-DD

## Session HH:MM
<3-5 lines of prose. What was done, key decisions, outcome.>

## Session HH:MM
<3-5 lines from a parallel session on the same day.>
```

After daily /consolidate, the file is rewritten as a single coherent
summary (no session headers). This is the version injected at session start.

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
