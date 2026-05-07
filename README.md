# agents-memory

Persistent, cross-session memory for AI coding agents. Works with Cursor and claude-code.

When you open a project, the agent knows what it is, what you did last time, your standards for that stack, and how your team works — without you repeating anything.

## Table of contents

- [How it works](#how-it-works)
- [Setup](#setup)
- [Memory structure](#memory-structure)
- [Requirements](#requirements)
- [Background](#background)

## How it works

```
~/agents-memory/
├── hooks/session-start.py    → Fires at session start, injects context
├── hooks/auto-save.py        → Fires on session end / every N responses
├── commands/save.md          → /save — persist session work
├── commands/consolidate.md   → /consolidate — maintenance cycles
├── config.json               → User configuration (save threshold, etc.)
├── global/preferences.md     → Your universal preferences
├── stacks/<lang>/            → Per-language standards
├── teams/<team>/             → Team conventions
└── projects/<name>/          → Per-project memory (auto-created)
```

**Session start:** A hook fires automatically, finds (or creates) your project's memory, and injects it as context. The agent starts knowing what happened last time.

**During work:** If you correct the agent about your preferences or standards, it updates the memory files immediately.

**End of session:** Run `/save` to persist what matters from the conversation:

| What it extracts | Where it writes |
|-----------------|----------------|
| Decisions (with reasoning) | `projects/<name>/logs/YYYY-MM-DD.md` (append) |
| User corrections | `projects/<name>/logs/YYYY-MM-DD.md` (append) |
| Learnings and patterns | `projects/<name>/logs/YYYY-MM-DD.md` (append) |
| Open threads | `projects/<name>/open-threads.md` (overwrite) |
| Session summary | `projects/<name>/last-session.md` (overwrite) |

It also updates the logs index and commits the changes to git. Only meaningful content gets saved — routine operations, tool calls, and file reads are skipped.

**Auto-save (safety net):** Even if you forget to `/save`, the auto-save hook captures your work automatically:

| Trigger | When | Behavior |
|---------|------|----------|
| Session end | Session closes (`sessionEnd` / `SessionEnd`) | Always saves |
| Pre-compaction | Context window fills up (`preCompact` / `PreCompact`) | Always saves |
| Periodic | After every N agent responses (`afterAgentResponse` / `Stop`) | Only when threshold reached (default: 10) |

The auto-save reads the conversation transcript, filters out noise (tool calls, file reads), and launches a headless agent in the background to extract memory — using the same instructions as `/save`. It's lower fidelity than a manual `/save` (no in-session context), but captures something vs. nothing.

The periodic threshold is configurable in `~/agents-memory/config.json`:
```json
{"auto_save_threshold": 10}
```

Projects with a `.skip` file in their memory directory are excluded from auto-save (useful for projects that have their own memory system).

**Maintenance:** Run `/consolidate` to normalize files, cross-reference projects, and promote recurring patterns. Auto-detects which cycle is due:

| Cycle | When | What it does |
|-------|------|-------------|
| Daily | New day since last run | Normalize formats, trim oversized indexes, validate open threads, cross-reference projects |
| Weekly | >7 days | Cross-project pattern detection, promote learnings to stack/team level, flag stale projects |
| Monthly | >28 days | Archive old logs with summaries, compact inactive projects, deep cross-scope generalization |

Each cycle includes all previous ones. Safe to run multiple times. Use `/consolidate daily` (or `weekly`, `monthly`) to force a specific cycle.

**Auto-consolidation:** You don't need to remember to run `/consolidate` manually. The sessionStart hook checks when consolidation last ran. If a cycle is overdue, it launches `/consolidate` in the background at the start of your next session — while you work, the system normalizes and cross-references behind the scenes. This runs at session *start* (not end), so there's no collision with auto-save which runs at session *end*.

**Over time:** Memory accumulates across sessions. Knowledge that recurs across projects gets promoted to stack or global level.

## Setup

### Quick setup (paste this to your agent)

Copy the section below and paste it into a Cursor or claude-code conversation. The agent will configure everything.

---

**Setup prompt:**

```
Set up agents-memory for me. Follow these steps exactly:

1. Verify python3 is available (version 3.9+).

2. Configure hooks:
   - For Cursor: Add this to ~/.cursor/hooks.json (create if doesn't exist):
     {
       "version": 1,
       "hooks": {
         "sessionStart": [
           {"command": "python3 ~/agents-memory/hooks/session-start.py"}
         ],
         "afterAgentResponse": [
           {"command": "python3 ~/agents-memory/hooks/auto-save.py", "timeout": 30}
         ],
         "preCompact": [
           {"command": "python3 ~/agents-memory/hooks/auto-save.py", "timeout": 30}
         ],
         "sessionEnd": [
           {"command": "python3 ~/agents-memory/hooks/auto-save.py", "timeout": 30}
         ]
       }
     }
   - For claude-code: Add these to ~/.claude/settings.json under "hooks":
     "SessionStart": [{"matcher": "startup|resume", "hooks": [
       {"type": "command", "command": "python3 /FULL/PATH/TO/agents-memory/hooks/session-start.py"}
     ]}],
     "Stop": [{"matcher": "", "hooks": [
       {"type": "command", "command": "python3 /FULL/PATH/TO/agents-memory/hooks/auto-save.py"}
     ]}],
     "PreCompact": [{"matcher": "", "hooks": [
       {"type": "command", "command": "python3 /FULL/PATH/TO/agents-memory/hooks/auto-save.py"}
     ]}],
     "SessionEnd": [{"matcher": "", "hooks": [
       {"type": "command", "command": "python3 /FULL/PATH/TO/agents-memory/hooks/auto-save.py", "timeout": 10}
     ]}]
     IMPORTANT: Use the full absolute path (not ~) for claude-code.

3. Symlink commands globally:
   - Cursor:
     ln -s ~/agents-memory/commands/save.md ~/.cursor/commands/save.md
     ln -s ~/agents-memory/commands/consolidate.md ~/.cursor/commands/consolidate.md
   - claude-code:
     ln -s ~/agents-memory/commands/save.md ~/.claude/commands/save.md
     ln -s ~/agents-memory/commands/consolidate.md ~/.claude/commands/consolidate.md

4. Verify: Start a new conversation in any project. You should see
   project context loaded automatically at the beginning.
```

---

### Manual setup

If you prefer to set it up yourself:

1. Clone this repo:
   ```bash
   git clone https://github.com/juanje/agents-memory ~/agents-memory
   ```

2. Configure hooks — sessionStart for context injection, plus auto-save
   hooks for afterAgentResponse, preCompact, and sessionEnd (see setup
   prompt above for the exact JSON for both Cursor and claude-code).

3. Symlink commands:
   ```bash
   ln -s ~/agents-memory/commands/save.md ~/.cursor/commands/save.md
   ln -s ~/agents-memory/commands/consolidate.md ~/.cursor/commands/consolidate.md
   ln -s ~/agents-memory/commands/save.md ~/.claude/commands/save.md
   ln -s ~/agents-memory/commands/consolidate.md ~/.claude/commands/consolidate.md
   ```

4. Start a new conversation — context should load automatically.

## Memory structure

The system has four scopes that compose:

| Scope | What it provides | Example |
|-------|-----------------|---------|
| **Project** | What this specific project is, last session, open threads | "Refactored auth module, pending migration" |
| **Stack** | Language standards, patterns, library preferences | "Use ruff, pytest, src layout" |
| **Team** | Team conventions, PR process, review norms | "MRs need 1 approval, CI must pass" |
| **Global** | Git workflow, general tool preferences | "Conventional commits, squash merge" |

A project's `index.md` declares its stack and team. The sessionStart hook
composes context from all relevant scopes automatically.

## Requirements

- **python3 ≥ 3.9** (stdlib only, no external dependencies)
- **Cursor** or **claude-code** (for hook support)
- **Platform CLI** (required for auto-save):
  - Cursor: `agent` CLI — `curl https://cursor.com/install -fsS | bash`
  - claude-code: `claude` CLI — installed with `npm install -g @anthropic-ai/claude-code`

The sessionStart hook and `/save` command work without the CLI. The auto-save hook needs it to launch a headless extraction agent in the background.

## Background

This system is based on the principles and experience of [Agentic Buddy](https://github.com/juanje/agentic-buddy) — a file-based memory system for AI agents that uses Hebbian-inspired learning cycles, progressive disclosure, and cross-scope knowledge promotion. agents-memory adapts that architecture for code projects: multiple projects, shared stack standards, team conventions, and portable across editors.

## License

MIT

## Author

Juanje Ojeda — juanje@redhat.com
https://github.com/juanje/
