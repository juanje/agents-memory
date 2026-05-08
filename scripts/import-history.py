#!/usr/bin/env python3
"""
import-history.py — Import historical transcripts into agents-memory.

Scans Cursor and claude-code transcript directories, maps them to
agents-memory projects, and processes them chronologically through the
/save extraction pipeline.

Usage:
    python3 ~/agents-memory/scripts/import-history.py [options]

Options:
    --dry-run       List what would be imported without processing
    --project NAME  Only import for a specific project
    --since DAYS    Only import transcripts from the last N days (default: 30)
    --all           Import all history (no date limit)
    --limit N       Process at most N transcripts (useful for testing)
    --min-lines N   Skip transcripts shorter than N lines (default: 10)
    --cli CLI       Force CLI to use (agent|claude). Default: auto-detect

After import, run `/consolidate monthly` to normalize all imported data.
"""

import argparse
import json
import os
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path


MEMORY_DIR = Path(os.environ.get("AGENT_MEMORY_DIR", Path.home() / "agents-memory"))
CURSOR_PROJECTS = Path.home() / ".cursor" / "projects"
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


def should_skip(project_name: str) -> bool:
    """Check if project has a .skip file (has its own memory system)."""
    skip_file = MEMORY_DIR / "projects" / project_name / ".skip"
    return skip_file.exists()


def find_cursor_transcripts() -> list[dict]:
    """Find all Cursor transcript files with metadata."""
    results = []
    if not CURSOR_PROJECTS.exists():
        return results

    for project_dir in CURSOR_PROJECTS.iterdir():
        if not project_dir.is_dir():
            continue
        transcripts_dir = project_dir / "agent-transcripts"
        if not transcripts_dir.exists():
            continue

        project_name = derive_project_name(project_dir.name, "cursor")
        if not project_name or should_skip(project_name):
            continue

        for session_dir in transcripts_dir.iterdir():
            if not session_dir.is_dir():
                continue
            transcript = session_dir / f"{session_dir.name}.jsonl"
            if not transcript.exists():
                continue

            mtime = datetime.fromtimestamp(transcript.stat().st_mtime)
            line_count = sum(1 for _ in open(transcript))

            results.append(
                {
                    "path": transcript,
                    "project": project_name,
                    "platform": "cursor",
                    "date": mtime.date(),
                    "lines": line_count,
                    "session_id": session_dir.name,
                }
            )

    return results


def find_claude_transcripts() -> list[dict]:
    """Find all claude-code transcript files with metadata."""
    results = []
    if not CLAUDE_PROJECTS.exists():
        return results

    for project_dir in CLAUDE_PROJECTS.iterdir():
        if not project_dir.is_dir():
            continue

        project_name = derive_project_name(project_dir.name, "claude")
        if not project_name or should_skip(project_name):
            continue

        for item in project_dir.iterdir():
            if item.is_file() and item.suffix == ".jsonl":
                mtime = datetime.fromtimestamp(item.stat().st_mtime)
                line_count = sum(1 for _ in open(item))
                results.append(
                    {
                        "path": item,
                        "project": project_name,
                        "platform": "claude",
                        "date": mtime.date(),
                        "lines": line_count,
                        "session_id": item.stem,
                    }
                )
            elif item.is_dir() and item.name != "subagents":
                transcript = item / f"{item.name}.jsonl"
                if not transcript.exists():
                    # Look for any .jsonl in the dir
                    jsonls = list(item.glob("*.jsonl"))
                    if jsonls:
                        transcript = jsonls[0]
                    else:
                        continue

                if not transcript.exists():
                    continue

                mtime = datetime.fromtimestamp(transcript.stat().st_mtime)
                line_count = sum(1 for _ in open(transcript))
                results.append(
                    {
                        "path": transcript,
                        "project": project_name,
                        "platform": "claude",
                        "date": mtime.date(),
                        "lines": line_count,
                        "session_id": item.name,
                    }
                )

    return results


def derive_project_name(dir_name: str, platform: str) -> str:
    """Extract project name from platform directory naming conventions."""
    if platform == "cursor":
        # Format: Users-juanjeojeda-git-<project-name>
        parts = dir_name.split("-")
        # Find "git" marker and take everything after
        try:
            git_idx = parts.index("git")
            name = "-".join(parts[git_idx + 1 :])
            # Remove trailing qualifiers like "-clean"
            for suffix in ["-clean-wiki", "-clean"]:
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
            return name if name else None
        except ValueError:
            return None
    else:
        # claude-code: -Users-juanjeojeda-git-<project-name>
        # or -Users-juanjeojeda-<project-name>
        parts = dir_name.lstrip("-").split("-")
        try:
            git_idx = parts.index("git")
            name = "-".join(parts[git_idx + 1 :])
            for suffix in ["-clean-wiki", "-clean"]:
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
            return name if name else None
        except ValueError:
            return None


def filter_cursor_transcript(path: Path) -> str:
    """Filter Cursor transcript to user+assistant text."""
    conversation = []
    for line in open(path):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = entry.get("role", "")
        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") != "text":
                continue
            text = block.get("text", "").strip()
            if not text or text.startswith("<"):
                continue
            prefix = "USER" if role == "user" else "AGENT"
            conversation.append(f"{prefix}: {text}")
    return "\n\n".join(conversation)


def filter_claude_transcript(path: Path) -> str:
    """Filter claude-code transcript to user+assistant text."""
    conversation = []
    skip_types = {
        "system",
        "attachment",
        "file-history-snapshot",
        "last-prompt",
        "permission-mode",
    }
    for line in open(path):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry_type = entry.get("type", "")
        if entry_type in skip_types:
            continue
        if entry_type == "user":
            content = entry.get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip():
                conversation.append(f"USER: {content.strip()}")
            continue
        if entry_type == "assistant":
            content = entry.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        conversation.append(f"AGENT: {text}")
    return "\n\n".join(conversation)


def filter_transcript(entry: dict) -> str:
    """Filter a transcript based on platform."""
    if entry["platform"] == "cursor":
        return filter_cursor_transcript(entry["path"])
    return filter_claude_transcript(entry["path"])


def already_imported(entry: dict) -> bool:
    """Check if this transcript was already imported (by session log date)."""
    project_dir = MEMORY_DIR / "projects" / entry["project"]
    log_file = project_dir / "logs" / f"{entry['date'].isoformat()}.md"
    if not log_file.exists():
        return False
    # Check if this session ID is mentioned in the log
    content = log_file.read_text()
    return entry["session_id"] in content


def build_extraction_prompt(
    project_name: str, filtered: str, session_date: str, session_id: str
) -> str:
    """Build the prompt for the extraction agent."""
    save_instructions = ""
    save_path = MEMORY_DIR / "commands" / "save.md"
    if save_path.exists():
        save_instructions = save_path.read_text()

    if not save_instructions:
        save_instructions = (
            "Extract decisions, corrections, learnings, and open threads. "
            "Write to last-session.md, open-threads.md, and logs/."
        )

    return (
        f"You are importing a historical session into the memory system for "
        f"project '{project_name}'. The session date is {session_date} "
        f"(session ID: {session_id}).\n\n"
        f"IMPORTANT: Use {session_date} as the date for log files and "
        f"last-session.md header — NOT today's date. This is a historical "
        f"import.\n\n"
        f"Follow these instructions:\n\n{save_instructions}\n\n"
        f"Apply them to the following conversation transcript:\n\n"
        f"--- CONVERSATION ---\n{filtered}\n--- END ---\n\n"
        f"After writing, run: cd {MEMORY_DIR} && git add -A && "
        f'git commit -m "import: {project_name} {session_date}"\n'
    )


def process_transcript(entry: dict, cli: str, dry_run: bool = False) -> bool:
    """Process a single transcript through the extraction pipeline."""
    filtered = filter_transcript(entry)
    if not filtered or len(filtered) < 100:
        return False

    session_date = entry["date"].isoformat()
    project_name = entry["project"]

    if dry_run:
        print(
            f"  Would import: {project_name} {session_date} "
            f"({entry['lines']} lines, {entry['platform']})"
        )
        return True

    # Ensure project dir exists
    project_dir = MEMORY_DIR / "projects" / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "logs").mkdir(exist_ok=True)

    prompt = build_extraction_prompt(
        project_name, filtered, session_date, entry["session_id"]
    )

    cmd = [cli, "-p", prompt]
    if cli == "agent":
        cmd.extend(["--workspace", str(MEMORY_DIR), "--force"])
    else:
        cmd.extend(["--allowedTools", "Read", "Write", "Edit", "Bash(git *)"])

    env = os.environ.copy()
    env["AGENT_MEMORY_SAVE"] = "1"

    print(
        f"  Processing: {project_name} {session_date} "
        f"({entry['lines']} lines, {entry['platform']})...",
        end=" ",
        flush=True,
    )

    try:
        result = subprocess.run(
            cmd,
            env=env,
            cwd=str(MEMORY_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print("OK")
            return True
        else:
            print(f"FAILED (exit {result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        print("TIMEOUT")
        return False
    except (FileNotFoundError, OSError) as e:
        print(f"ERROR: {e}")
        return False


def detect_cli() -> str:
    """Detect available CLI tool."""
    for cli in ["claude", "agent"]:
        try:
            subprocess.run([cli, "--version"], capture_output=True, timeout=5)
            return cli
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return "claude"


def main():
    parser = argparse.ArgumentParser(description="Import historical transcripts")
    parser.add_argument(
        "--dry-run", action="store_true", help="List what would be imported"
    )
    parser.add_argument(
        "--project",
        nargs="+",
        help="Only import for these projects (one or more names)",
    )
    parser.add_argument(
        "--since",
        type=int,
        default=30,
        help="Import transcripts from the last N days (default: 30)",
    )
    parser.add_argument(
        "--all", action="store_true", help="Import all history (no date limit)"
    )
    parser.add_argument("--limit", type=int, help="Max transcripts to process")
    parser.add_argument(
        "--min-lines", type=int, default=10, help="Skip transcripts shorter than this"
    )
    parser.add_argument(
        "--cli", choices=["agent", "claude"], help="CLI to use for extraction"
    )
    parser.add_argument(
        "--skip-imported",
        action="store_true",
        default=True,
        help="Skip already-imported sessions (default)",
    )
    args = parser.parse_args()

    cli = args.cli or detect_cli()
    print(f"CLI: {cli}")
    print(f"Memory: {MEMORY_DIR}")
    print()

    # Gather all transcripts
    print("Scanning transcripts...")
    all_transcripts = find_cursor_transcripts() + find_claude_transcripts()

    # Filter by date
    if not args.all:
        cutoff = date.today() - timedelta(days=args.since)
        all_transcripts = [t for t in all_transcripts if t["date"] >= cutoff]
        print(f"Date filter: last {args.since} days (since {cutoff})")
    else:
        print("Date filter: none (--all)")

    # Filter by size and project
    transcripts = [t for t in all_transcripts if t["lines"] >= args.min_lines]
    if args.project:
        projects_set = set(args.project)
        transcripts = [t for t in transcripts if t["project"] in projects_set]

    # Sort chronologically
    transcripts.sort(key=lambda t: (t["date"], t["project"]))

    # Skip already imported
    if args.skip_imported:
        before = len(transcripts)
        transcripts = [t for t in transcripts if not already_imported(t)]
        skipped = before - len(transcripts)
        if skipped:
            print(f"Skipped {skipped} already-imported transcripts")

    if args.limit:
        transcripts = transcripts[: args.limit]

    # Summary
    projects = {}
    for t in transcripts:
        projects.setdefault(t["project"], []).append(t)

    print(f"\nFound {len(transcripts)} transcripts across {len(projects)} projects:")
    for proj, entries in sorted(projects.items()):
        dates = f"{entries[0]['date']} → {entries[-1]['date']}"
        print(f"  {proj}: {len(entries)} sessions ({dates})")

    if not transcripts:
        print("\nNothing to import.")
        return

    if args.dry_run:
        print("\n--- DRY RUN ---")
        for t in transcripts:
            process_transcript(t, cli, dry_run=True)
        print(f"\nTotal: {len(transcripts)} transcripts would be imported.")
        print("Run without --dry-run to execute.")
        return

    # Process
    print(f"\nProcessing {len(transcripts)} transcripts...")
    success = 0
    failed = 0
    for i, t in enumerate(transcripts, 1):
        print(f"[{i}/{len(transcripts)}]", end=" ")
        if process_transcript(t, cli):
            success += 1
        else:
            failed += 1

    print(f"\nDone: {success} imported, {failed} failed.")
    print("\nRun `/consolidate monthly` to normalize all imported data.")


if __name__ == "__main__":
    main()
