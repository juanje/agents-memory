#!/usr/bin/env python3
"""
session-start.py — sessionStart hook for agents-memory.

Fires at the beginning of every new conversation. Reads project memory
and returns composed additional_context for the agent.

Output: JSON to stdout with {"additional_context": "..."} or {}.
"""

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path


MEMORY_DIR = Path(os.environ.get("AGENT_MEMORY_DIR", Path.home() / "agents-memory"))

RULES = """\
## Agent Memory

You have persistent memory for this project at ~/agents-memory/.
Context was loaded automatically (see below). You already know the
structure — navigate directly to the file you need, don't grep or search.

Memory paths:
- ~/agents-memory/projects/{project}/index.md — this project's context, decisions, logs
- ~/agents-memory/stacks/{stack}/index.md — stack-level standards and patterns
- ~/agents-memory/global/preferences.md — general preferences

To persist this session's work, use /save when you're done.

If the user corrects something about the project, stack, or preferences
("we don't do X anymore", "add Y to our standards", "that's wrong"),
update the relevant memory file immediately — don't wait for /save.
Memory corrections are system maintenance and happen inline.

If this is a NEW project (you see "[auto-detected — confirm with user]"
or "[ask user]" in the project index below), briefly confirm the stack
and team with the user at the start, then update the index.md.
"""


def read_file(path: Path) -> str:
    """Read a file, return empty string if missing or unreadable."""
    try:
        return path.read_text().strip()
    except (IOError, OSError):
        return ""


def detect_stack(project_dir: Path) -> str:
    """Auto-detect stack from project files."""
    markers = {
        "python": ["pyproject.toml", "setup.py", "requirements.txt"],
        "typescript": ["package.json", "tsconfig.json"],
        "go": ["go.mod"],
        "rust": ["Cargo.toml"],
        "java": ["pom.xml", "build.gradle"],
        "shell": [],  # fallback if .sh files dominate
    }

    for stack, files in markers.items():
        for f in files:
            if (project_dir / f).exists():
                return stack

    # Check for shell dominance
    sh_files = list(project_dir.glob("*.sh")) + list(project_dir.glob("scripts/*.sh"))
    if len(sh_files) >= 3:
        return "shell"

    return ""


def find_project(project_name: str) -> Path | None:
    """Find a project directory by name in memory."""
    project_dir = MEMORY_DIR / "projects" / project_name
    if project_dir.exists() and (project_dir / "index.md").exists():
        return project_dir
    return None


def create_project(project_name: str, workspace_dir: Path) -> Path:
    """Create a minimal project entry for a new project."""
    project_dir = MEMORY_DIR / "projects" / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "logs").mkdir(exist_ok=True)

    stack = detect_stack(workspace_dir)

    index_content = f"# {project_name}\n\n"
    if stack:
        index_content += f"- Stack: {stack} [auto-detected — confirm with user]\n"
    index_content += (
        "- Team: [ask user]\n"
        "- Last session: (new project)\n\n"
        "Files:\n"
        "- last-session.md — summary of the most recent session\n"
        "- open-threads.md — unfinished work, pending questions\n"
        "- logs/index.md — session history\n"
    )

    (project_dir / "index.md").write_text(index_content)
    (project_dir / "last-session.md").write_text(
        "# Last session\n\n(No sessions recorded yet. Use /save when done.)\n"
    )
    (project_dir / "open-threads.md").write_text("# Open threads\n\n(None yet.)\n")
    (project_dir / "logs" / "index.md").write_text(
        f"# Session logs — {project_name}\n\n| Date | Summary |\n|---|---|\n"
    )

    # Update projects/index.md
    projects_index = MEMORY_DIR / "projects" / "index.md"
    entry = f"- projects/{project_name}/index.md — (new project)"
    if stack:
        entry += f" ({stack})"
    entry += "\n"

    if projects_index.exists():
        current = projects_index.read_text()
        if project_name not in current:
            projects_index.write_text(current.rstrip() + "\n" + entry)
    else:
        projects_index.write_text(f"# Projects\n\n{entry}")

    return project_dir


def extract_field_from_index(project_index: str, field: str) -> str:
    """Parse a field value from a project's index.md content."""
    for line in project_index.splitlines():
        if line.strip().startswith(f"- {field}:"):
            value = line.split(":", 1)[1].strip()
            # For stack: extract just the base name (e.g., "python" from "python (3.12)")
            # Strip annotations in parentheses or brackets
            if field == "Stack":
                value = value.split("(")[0].split("[")[0].strip().split(",")[0].strip()
            return value
    return ""


def compose_context(project_dir: Path, project_name: str) -> str:
    """Compose the full additional_context from project + stack + team + global."""

    # Read project index to extract stack and team
    project_index = read_file(project_dir / "index.md")
    stack = extract_field_from_index(project_index, "Stack")
    team = extract_field_from_index(project_index, "Team")

    # Build rules with resolved paths (no placeholders)
    rules = RULES.replace("{project}", project_name)
    if stack:
        rules = rules.replace("{stack}", stack)
    else:
        # Remove the stack line if no stack detected
        rules = "\n".join(line for line in rules.splitlines() if "{stack}" not in line)

    parts = [rules, "---\n"]

    # Project context
    if project_index:
        parts.append(project_index)
        parts.append("")

    # Last session
    last_session = read_file(project_dir / "last-session.md")
    if last_session and "No sessions recorded" not in last_session:
        parts.append(last_session)
        parts.append("")

    # Open threads
    open_threads = read_file(project_dir / "open-threads.md")
    if open_threads and "(None" not in open_threads:
        parts.append(open_threads)
        parts.append("")

    # Stack standards
    if stack:
        stack_index = read_file(MEMORY_DIR / "stacks" / stack / "index.md")
        if stack_index:
            parts.append(stack_index)
            parts.append("")

    # Team conventions
    if team:
        team_index = read_file(MEMORY_DIR / "teams" / team / "index.md")
        if team_index:
            parts.append(team_index)
            parts.append("")

    # Global preferences
    prefs = read_file(MEMORY_DIR / "global" / "preferences.md")
    if prefs:
        parts.append(prefs)

    return "\n".join(parts)


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def check_consolidation_due() -> str | None:
    """Return cycle name if consolidation is overdue, else None."""
    state_file = MEMORY_DIR / "hooks" / ".state" / "consolidate.json"
    if not state_file.exists():
        return "daily"
    try:
        state = json.loads(state_file.read_text())
    except (json.JSONDecodeError, IOError):
        return "daily"

    running_pid = state.get("running_pid")
    if running_pid and _is_pid_alive(running_pid):
        return None

    last_run_str = state.get("last_run", "")
    if not last_run_str:
        return "daily"
    try:
        last_run = date.fromisoformat(last_run_str)
    except ValueError:
        return "daily"
    days = (date.today() - last_run).days
    if days >= 28:
        return "monthly"
    if days >= 7:
        return "weekly"
    if days >= 1:
        return "daily"
    return None


def launch_consolidation(cycle: str) -> None:
    """Launch /consolidate in background via platform CLI."""
    consolidate_cmd = read_file(MEMORY_DIR / "commands" / "consolidate.md")
    if not consolidate_cmd:
        return
    prompt = (
        f"Run a {cycle} consolidation on the memory system at {MEMORY_DIR}/. "
        f"Follow these instructions:\n\n{consolidate_cmd}"
    )
    if os.environ.get("CURSOR_PROJECT_DIR"):
        cli = "agent"
        cmd = [cli, "-p", prompt, "--workspace", str(MEMORY_DIR), "--force"]
    else:
        cli = "claude"
        cmd = [
            cli,
            "-p",
            prompt,
            "--allowedTools",
            "Read",
            "Write",
            "Edit",
            "Bash(git *)",
        ]
    env = os.environ.copy()
    env["AGENT_MEMORY_SAVE"] = "1"
    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=str(MEMORY_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (FileNotFoundError, OSError):
        return

    state_file = MEMORY_DIR / "hooks" / ".state" / "consolidate.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        state = json.loads(state_file.read_text())
    except (json.JSONDecodeError, IOError, FileNotFoundError):
        state = {}
    state["running_pid"] = proc.pid
    state_file.write_text(json.dumps(state) + "\n")


def main() -> None:
    # Read hook input from stdin
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, IOError):
        hook_input = {}

    # Determine workspace directory
    # Cursor: env var CURSOR_PROJECT_DIR
    # claude-code: cwd field in hook input JSON, or CLAUDE_PROJECT_DIR env var
    workspace_dir = Path(
        os.environ.get("CURSOR_PROJECT_DIR", "")
        or hook_input.get("cwd", "")
        or os.environ.get("CLAUDE_PROJECT_DIR", "")
        or os.getcwd()
    )

    project_name = workspace_dir.name

    # Find or create project
    project_dir = find_project(project_name)
    if not project_dir:
        project_dir = create_project(project_name, workspace_dir)

    # Projects with .skip have their own memory system — don't inject context
    if (project_dir / ".skip").exists():
        print(json.dumps({}))
        return

    # Compose and return context
    context = compose_context(project_dir, project_name)

    # Launch background consolidation if overdue
    cycle = check_consolidation_due()
    if cycle:
        launch_consolidation(cycle)

    # Output format differs by platform
    if os.environ.get("CURSOR_PROJECT_DIR"):
        # Cursor: flat JSON with additional_context
        output = {"additional_context": context}
    else:
        # claude-code: nested hookSpecificOutput
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
