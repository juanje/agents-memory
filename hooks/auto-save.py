#!/usr/bin/env python3
"""
auto-save.py — Auto-save hook for agents-memory.

Triggered by: sessionEnd/Stop (always), afterAgentResponse (with threshold).
Reads the conversation transcript, filters to user+assistant text, and
invokes the platform CLI to extract memory into project files.

Works on both Cursor and claude-code. Skips projects with .skip file.

Dependencies: python3 (stdlib only), platform CLI (agent or claude)
"""

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path


DEFAULT_SAVE_THRESHOLD = 10
MEMORY_DIR = Path(os.environ.get("AGENT_MEMORY_DIR", Path.home() / "agents-memory"))
STATE_DIR = MEMORY_DIR / "hooks" / ".state"


def load_config() -> dict:
    config_path = MEMORY_DIR / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {}


SAVE_THRESHOLD = load_config().get("auto_save_threshold", DEFAULT_SAVE_THRESHOLD)


def read_file(path: Path) -> str:
    try:
        return path.read_text().strip()
    except (IOError, OSError):
        return ""


def read_hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, IOError):
        return {}


def detect_platform(hook_input: dict) -> dict:
    """Resolve platform, project dir, and transcript path from env + stdin."""
    if os.environ.get("CURSOR_PROJECT_DIR"):
        return {
            "cli": "agent",
            "project_dir": os.environ["CURSOR_PROJECT_DIR"],
            "transcript": (
                hook_input.get("transcript_path")
                or os.environ.get("CURSOR_TRANSCRIPT_PATH", "")
            ),
        }
    return {
        "cli": "claude",
        "project_dir": hook_input.get("cwd", os.getcwd()),
        "transcript": hook_input.get("transcript_path", ""),
    }


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {"message_count": 0, "last_save_at": 0, "last_processed_line": 0}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")


def filter_cursor_transcript(lines: list[str]) -> str:
    conversation = []
    for line in lines:
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


def filter_claude_transcript(lines: list[str]) -> str:
    conversation = []
    skip_types = {
        "system",
        "attachment",
        "file-history-snapshot",
        "last-prompt",
        "permission-mode",
    }
    for line in lines:
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


def filter_transcript(path: Path, cli: str, from_line: int = 0) -> str:
    try:
        all_lines = path.read_text().splitlines()
    except IOError:
        return ""
    lines = all_lines[from_line:]
    if cli == "agent":
        return filter_cursor_transcript(lines)
    return filter_claude_transcript(lines)


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _acquire_project_lock(project_name: str) -> bool:
    """Try to acquire a per-project lock. Returns True if acquired."""
    lock_file = STATE_DIR / f"{project_name}.lock"
    if lock_file.exists():
        try:
            lock_data = json.loads(lock_file.read_text())
            pid = lock_data.get("pid", 0)
            if _is_pid_alive(pid):
                return False
        except (json.JSONDecodeError, IOError):
            pass
    return True


def _write_project_lock(project_name: str, pid: int) -> None:
    lock_file = STATE_DIR / f"{project_name}.lock"
    lock_file.write_text(json.dumps({"pid": pid}) + "\n")


def invoke_extraction(cli: str, prompt: str, project_name: str) -> bool:
    """Launch extraction agent in background, working inside ~/agents-memory."""
    if not _acquire_project_lock(project_name):
        return False

    env = os.environ.copy()
    env["AGENT_MEMORY_SAVE"] = "1"
    memory_dir = str(MEMORY_DIR)
    cmd = [cli, "-p", prompt]
    if cli == "agent":
        cmd.extend(["--workspace", memory_dir, "--force"])
    else:
        cmd.extend(["--allowedTools", "Write", "Edit", "Bash(git *)"])
    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=memory_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _write_project_lock(project_name, proc.pid)
        return True
    except (FileNotFoundError, OSError):
        return False


def main() -> None:
    if os.environ.get("AGENT_MEMORY_SAVE") == "1":
        return

    hook_input = read_hook_input()
    platform = detect_platform(hook_input)

    hook_event = hook_input.get("hook_event_name", "")
    project_name = Path(platform["project_dir"]).name

    project_dir = MEMORY_DIR / "projects" / project_name
    if (project_dir / ".skip").exists():
        return

    transcript_path = Path(platform["transcript"]) if platform["transcript"] else None
    if not transcript_path or not transcript_path.exists():
        return

    today = date.today()
    transcript_mtime = date.fromtimestamp(transcript_path.stat().st_mtime)
    if transcript_mtime < today:
        return

    conversation_id = (
        hook_input.get("conversation_id") or hook_input.get("session_id") or "unknown"
    )

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / f"{conversation_id}.json"
    state = load_state(state_file)

    periodic_events = {"afterAgentResponse", "Stop"}
    forced_events = {"sessionEnd", "SessionEnd", "preCompact", "PreCompact"}
    is_periodic = hook_event in periodic_events
    is_forced = hook_event in forced_events

    if is_periodic:
        state["message_count"] += 1
        save_state(state_file, state)
        messages_since_save = state["message_count"] - state["last_save_at"]
        if messages_since_save < SAVE_THRESHOLD:
            return

    if not is_periodic and not is_forced:
        return

    from_line = state["last_processed_line"]
    filtered = filter_transcript(transcript_path, platform["cli"], from_line)
    if not filtered:
        return

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "logs").mkdir(exist_ok=True)
    today_str = date.today().isoformat()

    save_instructions = read_file(MEMORY_DIR / "commands" / "save.md")
    if not save_instructions:
        save_instructions = (
            "Extract decisions, corrections, learnings, and open threads. "
            "Write to last-session.md, open-threads.md, and logs/."
        )

    extraction_prompt = (
        f"You are a memory extraction agent for the project '{project_name}'. "
        f"The project memory is at {project_dir}/.\n\n"
        f"Follow these instructions:\n\n{save_instructions}\n\n"
        f"Apply them to the following conversation transcript:\n\n"
        f"--- CONVERSATION ---\n{filtered}\n--- END ---\n\n"
        f"After writing, run: cd {MEMORY_DIR} && git add -A && "
        f'git commit -m "auto-save: {project_name} {today_str}"\n'
    )

    invoke_extraction(platform["cli"], extraction_prompt, project_name)

    total_lines = len(transcript_path.read_text().splitlines())
    state["last_save_at"] = state["message_count"]
    state["last_processed_line"] = total_lines
    save_state(state_file, state)


if __name__ == "__main__":
    main()
