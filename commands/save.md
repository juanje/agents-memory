# /save — Persist session memory

Read the current conversation and save what matters to the project memory
at ~/agents-memory/. Follow the formats defined in ~/agents-memory/formats.md.

## What to extract

1. **Decisions** — what was decided and why (architecture choices, library
   picks, approach changes). Only decisions with reasoning — not every
   micro-choice.
2. **Corrections** — things that were wrong and what's right. Mistakes
   the agent made that the user corrected. Include both the error and
   the fix.
3. **Learnings** — patterns discovered, things that work well in this
   project, gotchas to remember next time.
4. **Open threads** — unfinished work, pending questions, things to pick
   up next session.
5. **Related projects** — if this session referenced or depended on another
   project in memory, note the relationship.

## Where to write

Derive the project name from the current workspace directory name.

1. **Session log** → `~/agents-memory/projects/<project>/logs/YYYY-MM-DD.md`
   (append if exists). Sections: Decisions, Corrections, Learnings, Open
   threads. Skip empty sections.
2. **Last session** → `~/agents-memory/projects/<project>/last-session.md`
   (overwrite). 3-5 lines of prose summarizing the most recent day's work.
   If today's log already has content from earlier saves, read it first and
   write a combined summary — not just what was processed in this invocation.
3. **Open threads** → `~/agents-memory/projects/<project>/open-threads.md`
   (overwrite with current state — merge new threads, remove resolved ones).
4. **Logs index** → `~/agents-memory/projects/<project>/logs/index.md`
   (add or update today's entry in the table).
5. **Projects index** → `~/agents-memory/projects/index.md` — update the
   one-line description for this project if it says "(new project)" or if
   the description is stale. Format: `- projects/<name>/index.md — <description> (<stack>, <team>)`
6. **Related projects** → if relationships were discovered, add a
   "## Related projects" section to this project's `index.md` with paths
   to related project index files and a brief explanation of the relationship.

If the project directory doesn't exist yet, create it with the structure
from ~/agents-memory/formats.md.

## Size and deduplication

- **Project index.md:** keep it lean — ~30-50 lines for simple projects,
  ~80 max for complex ones. This is what loads at session start.
- **If the project has a CLAUDE.md or AGENTS.md:** don't duplicate what's
  already there. The project's own docs cover architecture, commands, and
  patterns. Memory should complement with cross-session knowledge:
  decisions made over time, patterns learned, relationships with other
  projects, things that aren't in the static docs.

## How to write

- Be specific: "Decided to use tenacity for retries because..." not
  "worked on retries."
- Be concise: future-you needs to understand in 10 seconds, not read
  an essay.
- Include reasoning: the WHY is more valuable than the WHAT.
- Follow the formats in ~/agents-memory/formats.md exactly.
- Don't log: routine operations, tool calls, file reads, things that
  don't inform future sessions.

## After writing

1. Git commit the changes:
   ```
   cd ~/agents-memory && git add -A && git commit -m "save: <project> YYYY-MM-DD"
   ```
2. Report briefly what was saved: "Saved: 2 decisions, 1 learning,
   updated open threads. Committed."
