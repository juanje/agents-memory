# /import-history — Bootstrap memory from past sessions

Import historical transcripts from Cursor and claude-code into
agents-memory. Gives the system knowledge from day one instead of
starting blank.

## Usage

```bash
# Preview what would be imported (last 30 days by default)
python3 ~/agents-memory/scripts/import-history.py --dry-run

# Import last 30 days (default)
python3 ~/agents-memory/scripts/import-history.py

# Import last 7 days only (quick bootstrap)
python3 ~/agents-memory/scripts/import-history.py --since 7

# Import all history (takes longer)
python3 ~/agents-memory/scripts/import-history.py --all

# Import specific projects
python3 ~/agents-memory/scripts/import-history.py --project pac-jobs create-osbuild custom-images

# Import a single project with a limit (good for testing)
python3 ~/agents-memory/scripts/import-history.py --project pac-jobs --limit 3

# Force a specific CLI
python3 ~/agents-memory/scripts/import-history.py --cli claude
```

## How it works

1. Scans `~/.cursor/projects/` and `~/.claude/projects/` for transcripts
2. Maps directory names to agents-memory project names
3. Sorts chronologically (oldest first — so later sessions override earlier)
4. For each transcript: filters to user+assistant text, feeds it to the
   /save extraction pipeline via CLI (`agent -p` or `claude -p`)
5. Each extraction produces a dated log + updates last-session.md + open-threads.md

## After import

Run `/consolidate monthly` to:
- Normalize all formats
- Add cross-references between projects
- Archive old logs
- Update descriptions in projects/index.md
- Detect patterns worth promoting to stacks

## Options

| Flag | Description |
|------|-------------|
| `--dry-run` | List what would be imported, don't process |
| `--since N` | Import transcripts from the last N days (default: 30) |
| `--all` | Import all history, no date limit |
| `--project NAME [NAME ...]` | Only import for these projects |
| `--limit N` | Process at most N transcripts |
| `--min-lines N` | Skip short transcripts (default: 10 lines) |
| `--cli agent\|claude` | Force CLI (default: auto-detect) |

## Notes

- Skipped projects: my-ab, work_brain (have their own memory systems)
- Already-imported sessions are skipped (checks by date + session ID)
- Each import produces a git commit: `import: <project> YYYY-MM-DD`
- Extraction uses the same /save prompt — same quality as live saves
- Timeout: 120s per transcript. Long sessions may need manual /save
