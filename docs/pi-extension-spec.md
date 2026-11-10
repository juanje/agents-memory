# pi-agents-memory — Extension Spec

Pi extension for [agents-memory](https://github.com/juanje/agents-memory).
Provides cross-session persistent memory for Pi agents, equivalent to
the Claude Code / Cursor hooks in the main repo.

## Scope

This extension handles two responsibilities:

1. **Context injection** — load project memory at session start and inject
   it into the conversation so the agent knows what happened last time.
2. **Auto-save** — extract memory from the conversation at session end,
   compaction, and periodically when the agent settles.

It does NOT handle:
- Memory file format or structure (owned by agents-memory)
- `/save` and `/consolidate` commands (prompt templates, copied by install.py)
- Consolidation scheduling (delegated to `pi -p` subprocess)

## Architecture

```
~/.pi/agent/extensions/pi-agents-memory/   (or installed via pi install)
├── package.json
├── extensions/
│   └── agents-memory.ts                   single entry point
├── test/
│   └── agents-memory.test.ts
├── tsconfig.json
├── biome.json
└── vitest.config.ts
```

Runtime dependency: `~/agents-memory/` (or `$AGENT_MEMORY_DIR`) must exist
with the standard agents-memory directory structure. The extension reads
and writes files there — no npm dependencies on the Python code.

## Events

### session_start

- Determine project name from `ctx.cwd` (basename)
- Find or create project directory in `~/agents-memory/projects/{name}/`
- Compose context from project + stack + team + global scopes
- Check if consolidation is due; if so, spawn `pi -p` in background
- Store composed context for `before_agent_start`

### before_agent_start

- If context was composed: inject it as a one-time message
  (`{ message: { customType: "agents-memory", content, display: false } }`)
- Message mode (inject once per session), same pattern as pi-context-loader

### agent_end (periodic save)

- Increment message counter
- If counter reaches threshold (default: 10, from config.json): extract and save
- Read conversation from `ctx.sessionManager.getEntries()`
- Filter to user/assistant text content
- Launch extraction via `pi -p` subprocess with save instructions

Note: `agent_settled` would be more precise (fires only when the agent is
truly idle), but it's not available in the published type definitions yet.
`agent_end` fires at the end of each run, which is close enough for the
periodic counter. Can be upgraded when the types catch up.

### session_shutdown (forced save)

- Only on `reason: "quit"` (skip "reload", "new", "resume", "fork")
- Same extraction as agent_settled but skip threshold check
- Always save if there is meaningful conversation content

### session_before_compact (forced save)

- Same as session_shutdown — always save before compaction discards context
- `session_compact` fires after the compaction is applied (entries already
  trimmed), so saving there would only see the summary — too late

## Conversation filtering

Unlike the Python hooks (which parse JSONL transcript files), the Pi
extension reads structured session entries directly:

```typescript
const entries = ctx.sessionManager.getEntries();
const conversation: string[] = [];

for (const entry of entries) {
  // Pi stores messages as { type: "message", message: { role, content } }
  if (entry.type === "message" &&
      (entry.message?.role === "user" || entry.message?.role === "assistant")) {
    const content = entry.message?.content;
    if (typeof content === "string" && content.trim()) {
      const prefix = entry.message.role === "user" ? "USER" : "AGENT";
      conversation.push(`${prefix}: ${content.trim()}`);
    } else if (Array.isArray(content)) {
      for (const block of content) {
        if (block.type === "text" && block.text?.trim()) {
          const prefix = entry.message.role === "user" ? "USER" : "AGENT";
          conversation.push(`${prefix}: ${block.text.trim()}`);
        }
      }
    }
  }
}

return conversation.join("\n\n");
```

This replaces `filter_claude_transcript()` and `filter_cursor_transcript()`
with a single, cleaner implementation that works with Pi's native data.

## Extraction subprocess

The extension spawns `pi -p` for extraction, similar to how the Python
hooks spawn `claude -p` or `agent -p`:

```typescript
const cmd = ["pi", "-p", extractionPrompt, "--tools", "read,write,edit,bash"];
```

The extraction prompt is built the same way as in auto-save.py:
- Read `~/agents-memory/commands/save.md` for instructions
- Include the filtered conversation
- Instruct to write to the project directory and git commit

## State management

Per-session state (message counter, last save position) uses in-memory
variables scoped to the extension instance. The `session_start` event
resets them. No `.state/*.json` files needed — Pi's extension lifecycle
handles session boundaries cleanly.

Cross-session state (consolidation schedule) still uses
`~/agents-memory/hooks/.state/consolidate.json` — shared with Claude Code
and Cursor instances.

## Context composition

Reuses the same logic as session-start.py, ported to TypeScript:

1. Read `projects/{name}/index.md` — extract stack and team fields
2. Read `projects/{name}/latest-sessions.md`
3. Read `projects/{name}/context.md`
4. Read `projects/{name}/open-threads.md`
5. Read `stacks/{stack}/index.md` (if stack detected)
6. Read `teams/{team}/index.md` (if team declared)
7. Read `global/preferences.md`
8. Compose with rules header and separator

Project auto-creation (detect stack from workspace files, scaffold
index.md + latest-sessions.md + open-threads.md) is also ported.

## Configuration

Reads `~/agents-memory/config.json` (same file as Python hooks):

```json
{
  "auto_save_threshold": 10
}
```

No Pi-specific config file needed. The `.skip` file convention is honored.

## Project structure

Following the pattern of pi-permission-gate and pi-context-loader:

```json
// package.json
{
  "name": "pi-agents-memory",
  "version": "0.1.0",
  "type": "module",
  "pi": { "extensions": ["./extensions"] },
  "peerDependencies": {
    "@earendil-works/pi-agent-core": "*",
    "@earendil-works/pi-coding-agent": "*"
  },
  "devDependencies": {
    "@biomejs/biome": "^2.4.14",
    "@earendil-works/pi-coding-agent": "^0.79.8",
    "typescript": "^5.0.0",
    "vitest": "^3.2.0"
  }
}
```

No runtime dependencies — stdlib only (node:fs, node:path, node:child_process).

## Installation

### As Pi package (preferred)

```bash
pi install npm:pi-agents-memory
```

### Via agents-memory installer

`install.py` detects Pi (`~/.pi/` exists) and runs:

```bash
pi install npm:pi-agents-memory
```

Or, for offline/manual install, copies the extension directory to
`~/.pi/agent/extensions/pi-agents-memory/`.

### Uninstall

```bash
pi remove pi-agents-memory
```

Or via `install.py --uninstall` which calls `pi remove`.

## Test strategy

Unit tests with vitest, following pi-context-loader's patterns:

- **Context composition**: temp dirs with memory structure, verify composed output
- **Conversation filtering**: mock session entries, verify filtered text
- **Event routing**: mock Pi API (createMockPi pattern), verify message
  injection, threshold logic, forced save triggers
- **Project detection/creation**: temp dirs, verify scaffold files created
- **Config loading**: verify threshold, skip file behavior

## What stays in agents-memory repo

- `hooks/auto-save.py` — Claude Code + Cursor auto-save (unchanged)
- `hooks/session-start.py` — Claude Code + Cursor context injection (unchanged)
- `commands/*.md` — prompt templates (copied to instance by install.py,
  also usable as Pi skills)
- `scripts/install.py` — gains Pi platform detection
- `formats.md` — shared memory format spec

## Shared behavior contract

The extension and the Python hooks must produce equivalent results:

1. Same context composition (same files, same order, same rules header)
2. Same extraction prompt structure (save.md instructions + filtered conversation)
3. Same project scaffold (index.md, latest-sessions.md, open-threads.md, logs/)
4. Same config.json keys (auto_save_threshold)
5. Same .skip file convention
6. Same git commit format ("auto-save: {project} {date}")
