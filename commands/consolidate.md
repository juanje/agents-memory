# /consolidate — Memory maintenance cycle

Run maintenance on ~/agents-memory/. Auto-detects which cycle is due
(daily, weekly, monthly) or accepts an explicit argument to force one.

Usage:
- `/consolidate` — auto-detect and run what's due
- `/consolidate daily` — force daily cycle
- `/consolidate weekly` — force weekly cycle (includes daily)
- `/consolidate monthly` — force monthly cycle (includes weekly + daily)

Can be run multiple times in a day — only acts on what needs attention.
Follow the formats in ~/agents-memory/formats.md for any files modified.

**Idempotency rule:** Do not rewrite existing content that already follows
the formats. Only add, remove, or fix content that is structurally wrong
(missing fields, wrong format, stale data). Rephrasing correct content is
not a valid change. If a file is already correct, leave it untouched.

## What to read per cycle

| Cycle | Read | Don't read |
|-------|------|-----------|
| Daily | Project info files (index.md, last-session.md, open-threads.md), logs from today/yesterday, formats.md | Archived logs, full stack/team files (unless promoting) |
| Weekly | Same as daily + all logs from the current week, stack index files | Monthly archives, logs older than 7 days |
| Monthly | Same as weekly + all logs from the month, full stack and team files | Logs older than current month (already archived) |

Start with the lightest reads (indexes, info files). Only open full logs
when the index shows relevant activity. Don't read archived content.

## Parallelization with subagents

- **Daily (5+ projects):** Launch one background subagent per project for
  normalization and trimming. Main agent handles cross-references after.
- **Weekly (5+ projects):** Same — subagent per project for log review.
  Main agent handles cross-project pattern detection.
- **Monthly (3+ projects):** Launch one subagent per project for
  archive/compact. Main agent handles deep cross-scope generalization
  with the results.

Each subagent receives: the project path, formats.md, and specific
instructions for its cycle. It returns a brief summary of what it did.
The main agent synthesizes.

## Cycle detection

Read `~/agents-memory/hooks/.state/consolidate.json`. If it doesn't exist,
run daily. Otherwise check `last_run`:
- Same day → only re-normalize if needed (safe to re-run)
- New day → daily
- >7 days → weekly (includes daily)
- >28 days → monthly (includes weekly + daily)

## Daily cycle

1. **Normalize formats:** Read all projects' files (last-session.md,
   open-threads.md, logs/, index.md). Compare against
   ~/agents-memory/formats.md. Fix any deviations (headers, structure,
   empty states).

2. **Trim oversized indexes:** Check each project's index.md. If >80
   lines, extract the heaviest section into a separate file (context.md,
   decisions.md) and replace with a pointer. Keep index.md as a lean hub.

3. **Update projects/index.md:** Ensure every project has a current
   one-line description (not "(new project)"). Derive from the project's
   index.md content.

4. **Cross-reference:** If yesterday's sessions mentioned other projects
   in memory, ensure "## Related projects" sections exist with pointers.

5. **Validate open-threads:** Read each project's open-threads.md. If a
   session log resolved a thread (explicitly or implicitly), remove it.

6. **Git commit:** `cd ~/agents-memory && git add -A && git commit -m "daily: YYYY-MM-DD"`

## Weekly cycle (includes daily first)

7. **Cross-project patterns:** Read all session logs from the week across
   projects. If the same decision or pattern appears in 2+ projects of the
   same stack → promote to stacks/<stack>/index.md (or standards.md/
   patterns.md if the index is getting long).

8. **Stack enrichment:** Add learnings that generalize (not
   project-specific) to the relevant stack file.

9. **Team updates:** If new conventions were established this week across
   projects of the same team, update teams/<team>/index.md.

10. **Flag stale projects:** Projects with no sessions in >30 days →
    note in the weekly commit message (don't auto-archive yet).

11. **Git commit:** `cd ~/agents-memory && git add -A && git commit -m "weekly: YYYY-WNN"`

## Monthly cycle (includes weekly first)

12. **Archive old logs:** For each project, move logs >30 days old to
    `projects/<name>/logs/archive/YYYY-MM/`. Create a monthly summary
    file in the archive directory.

13. **Deep generalization:** Read all stacks — any patterns that should
    be global? Read all projects — any that should share a convention
    not yet captured?

14. **Compact inactive projects:** Projects with no sessions in >60 days
    → trim their context to essentials (keep index.md, clear last-session
    and open-threads to empty state).

15. **Prune stale promotions:** If a pattern was promoted to stack/global
    but hasn't been confirmed by continued use (no references in logs for
    30+ days), flag it for review.

16. **Git commit:** `cd ~/agents-memory && git add -A && git commit -m "monthly: YYYY-MM"`

## After running

Update the state file:
```
~/agents-memory/hooks/.state/consolidate.json
{"last_run": "YYYY-MM-DD", "last_cycle": "daily|weekly|monthly"}
```

Report what was done: "Consolidation (daily): normalized 3 files, trimmed
pac-jobs index, added 1 cross-reference. Committed."
