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

**Index integrity rule:** NEVER remove entries from `projects/index.md`.
You may update descriptions but the set of project entries must remain
unchanged. If a project directory exists, its entry must stay in the index.
Removing an entry is data loss — the project becomes invisible to all agents.

## Architecture: staging-based pipeline

All consolidation follows this pipeline. Parallelism is only in reading
and analysis — never in writing or committing.

```
ASSESS → ANALYZE (per project) → PLAN → EXECUTE → COMMIT → CLEAN UP
```

- **Analyze** phase produces manifests in `~/agents-memory/.staging/`.
- **Execute** phase is the only step that modifies project memory files.
- **Commit** is always a single `git add -A && git commit` at the end.
- `.staging/` is cleaned after commit.

**Subagent rules (when used):**
- Subagents may ONLY write to `.staging/`. Never to project files.
- Subagents have NO git permissions.
- Subagents read: the project's files + `formats.md`. Nothing else.

## What to read per cycle

| Cycle | Read | Don't read |
|-------|------|-----------|
| Daily | Project info files (index.md, latest-sessions.md, open-threads.md, context.md), logs from today/yesterday, formats.md | Archived logs, full stack/team files (unless promoting) |
| Weekly | Same as daily + all logs from the current week, stack index files | Monthly archives, logs older than 7 days |
| Monthly | Same as weekly + all logs from the month, full stack and team files | Logs older than current month (already archived) |

Start with the lightest reads (indexes, info files). Only open full logs
when the index shows relevant activity. Don't read archived content.

## Subagent strategy

| Cycle | Projects | Strategy |
|-------|----------|----------|
| Daily | ≤5 | Single agent — sequential Analyze+Plan+Execute |
| Daily | 6+ | Subagents for Analyze, main agent for Plan+Execute |
| Weekly | any | Subagents for Analyze |
| Monthly | any | Subagents for Analyze + archive assessment |

When running as a single agent (daily ≤5), skip manifest files — analyze
in memory and proceed directly to Plan+Execute. The staging pipeline is
for coordination when subagents are involved.

## Cycle detection

Read `~/agents-memory/hooks/.state/consolidate.json`. If it doesn't exist,
run daily. Otherwise check `last_run`:
- Same day → only re-normalize if needed (safe to re-run)
- New day → daily
- >7 days → weekly (includes daily)
- >28 days → monthly (includes weekly + daily)

---

## Phase 1: ASSESS

1. Read `hooks/.state/consolidate.json` → determine cycle.
2. List `projects/` → identify active projects (have logs from this cycle's
   window).
3. Decide strategy (single agent vs subagents) per table above.

## Phase 2: ANALYZE (per project)

For each active project, produce an analysis. When using subagents, each
writes to `.staging/<project>-analysis.md`. When single-agent, hold the
analysis in working memory.

**What to analyze:**

- Read the project's `index.md`, `latest-sessions.md`, `open-threads.md`, `context.md`.
- Read `logs/index.md` to identify recent sessions.
- Read relevant session logs (per cycle scope).
- Compare all files against `formats.md`.

**Analysis manifest format** (`.staging/<project>-analysis.md`):

```markdown
# Analysis: <project-name>

## Format issues
- <file>: <what's wrong per formats.md>

## Stale threads
- <thread summary> — resolved in <log date> (evidence: <brief quote>)

## Cross-references detected
- References <other-project> (<reason>)

## Index update
- Current description: "<current>"
- Suggested: "<better one-line description>" (or "OK" if current is fine)

## Hub trimming
- index.md is <N> lines (threshold: 80). Action: <none | extract to context.md>

## Patterns (weekly+)
- "<pattern>" appears N times → candidate for <scope>

## Archive candidates (monthly)
- logs/<date>.md — older than 30 days, candidate for archive
```

Omit empty sections. Only include sections with actionable findings.

**Subagent prompt template:**

> Read the project memory at ~/agents-memory/projects/<name>/ and
> ~/agents-memory/formats.md. Analyze the project's files for: format
> deviations, stale open threads (check against recent logs), cross-project
> references, index description accuracy, and hub size. Write your findings
> to ~/agents-memory/.staging/<name>-analysis.md following the analysis
> manifest format. Omit sections with no findings. Return a one-line
> summary.

## Phase 3: PLAN

Read all analysis results (from `.staging/` or working memory). Produce a
consolidated plan. When using subagents, write to `.staging/_plan.md`. When
single-agent, hold in working memory.

**Plan format** (`.staging/_plan.md`):

```markdown
# Consolidation plan (<cycle> — YYYY-MM-DD)

## Normalize
1. <project>/<file> — <what to fix>

## Remove stale threads
1. <project>/open-threads.md — remove "<thread>" (resolved <date>)

## Cross-references
1. <project>/index.md — add <other-project> to Related projects

## Update descriptions
1. projects/index.md — <project>: "<new description>"

## Hub trimming
1. <project>/index.md — extract <section> to <project>/context.md

## Promotions (weekly+)
1. "<pattern>" → stacks/<stack>/<file>.md

## Archive (monthly)
1. <project>/logs/<date>.md → <project>/logs/archive/YYYY-MM/

## No action needed
- <project>: all files correct
```

**Decision rules:**
- Only include actions where something is actually wrong or missing.
- "No action needed" confirms you checked — not that you skipped.
- Cross-references: only add genuinely related projects (shared data,
  dependency, migration context). Not every project mentioned in passing.
- Promotions require the pattern to appear in 2+ projects of the same
  stack. A single occurrence is project-level, not stack-level.

## Phase 4: EXECUTE

Apply the plan. This is the only phase that modifies project memory files.

**Rules:**
- Follow the plan literally. Don't add changes not in the plan.
- If a file is already correct (plan says normalize but the file matches
  formats.md), skip it — don't touch.
- When modifying files, preserve existing content that isn't flagged in
  the plan. Don't rewrite surrounding prose.
- Do NOT run git commands during this phase.

**Execution order:**
1. Normalize (format fixes)
2. Remove stale threads
3. Cross-references
4. Update descriptions (projects/index.md) — update wording only, NEVER remove entries
5. Hub trimming (extract to separate file + pointer)
6. Promotions (weekly+)
7. Archive (monthly)

## Phase 5: COMMIT + CLEAN UP

After all changes are applied:

1. Update state:
   ```
   ~/agents-memory/hooks/.state/consolidate.json
   {"last_run": "YYYY-MM-DD", "last_cycle": "daily|weekly|monthly"}
   ```

2. Single commit:
   ```bash
   cd ~/agents-memory && git add -A && git commit -m "consolidate(<cycle>): YYYY-MM-DD"
   ```
   This is the ONLY git command in the entire run. No intermediate commits.
   No per-project commits. One commit.

3. Clean up staging:
   ```bash
   rm -rf ~/agents-memory/.staging/
   ```

4. Report:
   ```
   Consolidation (<cycle>): <brief summary of what changed>. Committed.
   ```

---

## Daily cycle — what to check

1. **Normalize formats:** Compare project files against formats.md.
2. **Trim oversized indexes:** index.md >80 lines → extract to context.md.
3. **Update projects/index.md:** Ensure current one-line descriptions.
4. **Cross-reference:** Sessions mentioning other projects → Related sections.
5. **Validate open-threads:** Remove threads resolved in recent logs.
6. **Validate latest-sessions.md:** Check that the file follows the format
   in formats.md (max 3 sections, each with summary + blockquote log
   reference). Fix format issues only — do not rewrite content or merge
   sections. This file is self-managed by /save, not by consolidation.
   **Migration:** If `last-session.md` exists but `latest-sessions.md`
   doesn't, rename the file and reformat to match the new format.
7. **Enrich context.md (append-only):** Read recent logs and compare
   against `context.md`. Apply the three rules from formats.md:
   - **Add** new information with `(learned YYYY-MM-DD)` marker.
   - **Do not change or remove** existing valid content.
   - **Update only with explicit log evidence** of a change (migration,
     removal, replacement). Keep the previous state inline:
     `<new state> (changed YYYY-MM-DD — was <old state>, <reason>)`.
   If `context.md` doesn't exist yet, create it from recent logs following
   the format in formats.md.

## Weekly cycle (includes daily)

6. **Cross-project patterns:** Same decision in 2+ projects of same stack
   → promote to stacks/<stack>/index.md.
7. **Stack enrichment:** Generalizable learnings → stack files.
8. **Team updates:** New conventions across a team → teams/<team>/index.md.
9. **Flag stale projects:** No sessions in >30 days → note in commit message.

## Monthly cycle (includes weekly)

10. **Archive old logs:** logs >30 days → `logs/archive/YYYY-MM/` with summary.
11. **Deep generalization:** Stack patterns that should be global?
12. **Compact inactive projects:** No sessions in >60 days → trim to essentials.
13. **Prune stale promotions:** Promoted patterns with no recent references → flag.
14. **Compact context.md:** If the file has grown large, compress old entries:
    remove inline change history older than 3 months (keep only the current
    state), consolidate related entries. The original logs exist as backup
    for anything removed.
