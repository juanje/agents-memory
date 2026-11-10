#!/usr/bin/env python3
"""
install.py — Install or update agents-memory.

Creates an independent instance at ~/agents-memory/ (or $AGENT_MEMORY_DIR)
by copying code files from this source repo. The instance is its own git
repo — no shared remote, no shared history with the source.

On first run: creates the directory, copies code, scaffolds data structure,
git init + initial commit, configures platform hooks and command symlinks.

On subsequent runs: updates code files only (hooks, scripts, commands,
formats), preserves all data (projects, stacks, teams, preferences),
commits the update, and refreshes platform hooks if the config changed.

Usage:
    python3 scripts/install.py              # install or update
    python3 scripts/install.py --dry-run    # preview changes
    python3 scripts/install.py --uninstall  # remove hooks and symlinks
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


SOURCE_DIR = Path(__file__).resolve().parent.parent

INSTANCE_DIR = Path(os.environ.get("AGENT_MEMORY_DIR", Path.home() / "agents-memory"))

CODE_FILES = [
    "hooks/auto-save.py",
    "hooks/session-start.py",
    "scripts/install.py",
    "scripts/import-history.py",
    "commands/save.md",
    "commands/consolidate.md",
    "commands/import-history.md",
    "formats.md",
    ".gitignore",
]

SCAFFOLD_FILES = {
    "index.md": "# agents-memory\n\nRoot: ~/agents-memory/\n\n## Scopes\n\n"
        "- global/preferences.md — Git workflow, code style, tools\n"
        "- stacks/index.md — Per-language standards (python, typescript, etc.)\n"
        "- teams/index.md — Team conventions\n"
        "- projects/index.md — All projects with one-line descriptions\n",
    "config.json": '{\n  "auto_save_threshold": 10\n}\n',
    "projects/index.md": "# Projects\n\n(No projects registered yet. The sessionStart hook creates entries\n"
        "automatically when you first open a project.)\n",
    "stacks/index.md": "# Stacks\n\nPer-language/platform standards. Create a subdirectory for each stack\n"
        "as you work on projects using it.\n\n"
        "(No stacks registered yet. The sessionStart hook auto-detects stacks\n"
        "from project files and loads standards if available.)\n",
    "teams/index.md": "# Teams\n\nTeam conventions and processes. Create a subdirectory for each team\n"
        "as needed.\n\n(No teams registered yet.)\n",
    "global/preferences.md": "# Preferences\n\n## Git\n\n"
        "- Conventional commits (feat:, fix:, refactor:, docs:, etc.)\n"
        "- Feature branches, squash merge to main\n"
        "- Small PRs — one concern per PR\n\n"
        "## Code style\n\n- Explicit over implicit\n- Comments explain WHY, not WHAT\n",
}

SCAFFOLD_DIRS = [
    "projects",
    "stacks",
    "teams",
    "global",
    "hooks",
    "hooks/.state",
    "scripts",
    "commands",
]

COMMANDS = ["save.md", "consolidate.md", "import-history.md"]

CURSOR_HOOKS = {
    "version": 1,
    "hooks": {
        "sessionStart": [
            {"command": f"python3 {INSTANCE_DIR}/hooks/session-start.py"}
        ],
        "afterAgentResponse": [
            {"command": f"python3 {INSTANCE_DIR}/hooks/auto-save.py", "timeout": 30}
        ],
        "preCompact": [
            {"command": f"python3 {INSTANCE_DIR}/hooks/auto-save.py", "timeout": 30}
        ],
        "sessionEnd": [
            {"command": f"python3 {INSTANCE_DIR}/hooks/auto-save.py", "timeout": 30}
        ],
    },
}

CLAUDE_HOOKS = {
    "SessionStart": [
        {
            "matcher": "startup|resume|compact",
            "hooks": [
                {
                    "type": "command",
                    "command": f"python3 {INSTANCE_DIR}/hooks/session-start.py",
                }
            ],
        }
    ],
    "Stop": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"python3 {INSTANCE_DIR}/hooks/auto-save.py",
                }
            ],
        }
    ],
    "PreCompact": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"python3 {INSTANCE_DIR}/hooks/auto-save.py",
                }
            ],
        }
    ],
    "SessionEnd": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"python3 {INSTANCE_DIR}/hooks/auto-save.py",
                    "timeout": 10,
                }
            ],
        }
    ],
}

CURSOR_OBSOLETE_EVENTS: set[str] = set()


def log(msg: str) -> None:
    print(f"  {msg}")


def read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def write_json(path: Path, data: dict, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


# --- Instance management ---


def create_instance(dry_run: bool) -> bool:
    """Create a fresh instance. Returns True if created."""
    if INSTANCE_DIR.exists():
        return False

    log(f"create {INSTANCE_DIR}/")
    if dry_run:
        return True

    for d in SCAFFOLD_DIRS:
        (INSTANCE_DIR / d).mkdir(parents=True, exist_ok=True)

    for rel_path, content in SCAFFOLD_FILES.items():
        dest = INSTANCE_DIR / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)

    return True


def copy_code_files(dry_run: bool) -> list[str]:
    """Copy code files from source to instance. Returns list of changed files."""
    changed = []
    for rel_path in CODE_FILES:
        src = SOURCE_DIR / rel_path
        dest = INSTANCE_DIR / rel_path

        if not src.exists():
            continue

        src_content = src.read_text()
        if dest.exists() and dest.read_text() == src_content:
            continue

        changed.append(rel_path)
        action = "update" if dest.exists() else "add"
        log(f"{action} {rel_path}")

        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    return changed


def init_git(dry_run: bool) -> None:
    """Initialize git repo in instance directory."""
    if (INSTANCE_DIR / ".git").exists():
        return

    log("git init")
    if dry_run:
        return

    subprocess.run(["git", "init"], cwd=str(INSTANCE_DIR), capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(INSTANCE_DIR), capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init: agents-memory instance"],
        cwd=str(INSTANCE_DIR),
        capture_output=True,
    )


def commit_update(changed_files: list[str], dry_run: bool) -> None:
    """Commit code file updates in the instance repo."""
    if not changed_files or dry_run:
        return

    if not (INSTANCE_DIR / ".git").exists():
        return

    for f in changed_files:
        subprocess.run(["git", "add", f], cwd=str(INSTANCE_DIR), capture_output=True)

    files_summary = ", ".join(Path(f).stem for f in changed_files[:3])
    if len(changed_files) > 3:
        files_summary += f" +{len(changed_files) - 3} more"

    subprocess.run(
        ["git", "commit", "-m", f"update: {files_summary}"],
        cwd=str(INSTANCE_DIR),
        capture_output=True,
    )


# --- Platform hooks ---


def _is_memory_command(command: str) -> bool:
    """Check if a command references this specific instance's hooks."""
    return str(INSTANCE_DIR) in command


def _is_any_memory_command(command: str) -> bool:
    """Check if a command references any agents-memory instance."""
    return str(INSTANCE_DIR) in command or "agents-memory/hooks/" in command


def _find_and_update_hook(existing: list[dict], desired: list[dict]) -> tuple[list[dict], bool]:
    desired_entry = desired[0]
    changed = False
    updated = []

    found = False
    for entry in existing:
        entry_cmds = [h.get("command", "") for h in entry.get("hooks", [])]
        is_ours = any(_is_any_memory_command(c) for c in entry_cmds)
        if is_ours:
            if entry != desired_entry:
                updated.append(desired_entry)
                changed = True
            else:
                updated.append(entry)
            found = True
        else:
            updated.append(entry)

    if not found:
        updated.extend(desired)
        changed = True

    return updated, changed


def install_claude_hooks(dry_run: bool) -> None:
    settings_path = Path.home() / ".claude" / "settings.json"
    settings = read_json(settings_path)
    hooks = settings.setdefault("hooks", {})
    changed = False

    for event, desired in CLAUDE_HOOKS.items():
        existing = hooks.get(event, [])
        updated, did_change = _find_and_update_hook(existing, desired)
        if did_change:
            hooks[event] = updated
            changed = True
            log(f"claude-code: {'update' if existing else 'add'} {event} hook")

    if changed:
        write_json(settings_path, settings, dry_run)
    else:
        log("claude-code: hooks already up to date")


def uninstall_claude_hooks(dry_run: bool) -> None:
    settings_path = Path.home() / ".claude" / "settings.json"
    settings = read_json(settings_path)
    hooks = settings.get("hooks", {})
    changed = False

    for event in list(hooks.keys()):
        original = hooks[event]
        filtered = [
            entry for entry in original
            if not any(_is_memory_command(h.get("command", "")) for h in entry.get("hooks", []))
        ]
        if len(filtered) != len(original):
            if filtered:
                hooks[event] = filtered
            else:
                del hooks[event]
            changed = True
            log(f"claude-code: remove {event} hook")

    if changed:
        write_json(settings_path, settings, dry_run)
    else:
        log("claude-code: no hooks to remove")


def install_cursor_hooks(dry_run: bool) -> None:
    hooks_path = Path.home() / ".cursor" / "hooks.json"
    existing = read_json(hooks_path)

    if existing.get("hooks") == CURSOR_HOOKS["hooks"] and existing.get("version") == 1:
        log("cursor: hooks already up to date")
        return

    if not existing or not existing.get("hooks"):
        result = CURSOR_HOOKS.copy()
    else:
        result = existing.copy()
        result["version"] = 1
        result_hooks = result.setdefault("hooks", {})

        for obsolete in CURSOR_OBSOLETE_EVENTS:
            if obsolete in result_hooks:
                del result_hooks[obsolete]
                log(f"cursor: remove obsolete {obsolete} hook")

        for event, desired_entries in CURSOR_HOOKS["hooks"].items():
            event_hooks = result_hooks.get(event, [])
            for desired in desired_entries:
                desired_cmd = desired["command"]
                found = any(h.get("command") == desired_cmd for h in event_hooks)
                if not found:
                    updated = [
                        desired if _is_any_memory_command(h.get("command", "")) else h
                        for h in event_hooks
                    ]
                    if desired not in updated:
                        updated.append(desired)
                    event_hooks = updated
                else:
                    event_hooks = [
                        desired if h.get("command") == desired_cmd else h
                        for h in event_hooks
                    ]
                result_hooks[event] = event_hooks

    log("cursor: update hooks.json")
    write_json(hooks_path, result, dry_run)


def uninstall_cursor_hooks(dry_run: bool) -> None:
    hooks_path = Path.home() / ".cursor" / "hooks.json"
    existing = read_json(hooks_path)
    if not existing.get("hooks"):
        log("cursor: no hooks to remove")
        return

    hooks = existing["hooks"]
    changed = False

    for event in list(hooks.keys()):
        original = hooks[event]
        filtered = [h for h in original if not _is_memory_command(h.get("command", ""))]
        if len(filtered) != len(original):
            if filtered:
                hooks[event] = filtered
            else:
                del hooks[event]
            changed = True
            log(f"cursor: remove {event} hook")

    if changed:
        if hooks:
            write_json(hooks_path, existing, dry_run)
        elif not dry_run:
            hooks_path.unlink(missing_ok=True)
            log("cursor: removed empty hooks.json")
    else:
        log("cursor: no hooks to remove")


# --- Command symlinks ---


def install_commands(dry_run: bool) -> None:
    platforms = detect_platforms()
    for platform, commands_dir in platforms.items():
        commands_dir.mkdir(parents=True, exist_ok=True) if not dry_run else None
        for cmd in COMMANDS:
            target = INSTANCE_DIR / "commands" / cmd
            link = commands_dir / cmd
            if link.is_symlink():
                if link.resolve() == target.resolve():
                    continue
                log(f"{platform}: update symlink {cmd}")
                if not dry_run:
                    link.unlink()
                    link.symlink_to(target)
            elif link.exists():
                log(f"{platform}: skip {cmd} (file exists, not a symlink)")
            else:
                log(f"{platform}: symlink {cmd}")
                if not dry_run:
                    link.symlink_to(target)


def uninstall_commands(dry_run: bool) -> None:
    platforms = detect_platforms()
    for platform, commands_dir in platforms.items():
        for cmd in COMMANDS:
            link = commands_dir / cmd
            if link.is_symlink():
                target = INSTANCE_DIR / "commands" / cmd
                if link.resolve() == target.resolve():
                    log(f"{platform}: remove symlink {cmd}")
                    if not dry_run:
                        link.unlink()


def detect_platforms() -> dict[str, Path]:
    platforms = {}
    claude_dir = Path.home() / ".claude" / "commands"
    cursor_dir = Path.home() / ".cursor" / "commands"
    if claude_dir.parent.exists():
        platforms["claude-code"] = claude_dir
    if cursor_dir.parent.exists():
        platforms["cursor"] = cursor_dir
    return platforms


# --- Main ---


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install or update agents-memory."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying them")
    parser.add_argument("--uninstall", action="store_true", help="Remove hooks and command symlinks")
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN — no changes will be made\n")

    if args.uninstall:
        print(f"Uninstalling agents-memory from {INSTANCE_DIR}...\n")
        platforms = detect_platforms()
        for platform in platforms:
            if platform == "claude-code":
                uninstall_claude_hooks(args.dry_run)
            elif platform == "cursor":
                uninstall_cursor_hooks(args.dry_run)
        uninstall_commands(args.dry_run)
        print("\nDone. Hooks and symlinks removed.")
        print(f"Instance directory left in place: {INSTANCE_DIR}")
        if args.dry_run:
            print("\nRe-run without --dry-run to apply.")
        return

    print(f"Source:   {SOURCE_DIR}")
    print(f"Instance: {INSTANCE_DIR}\n")

    if SOURCE_DIR.resolve() == INSTANCE_DIR.resolve():
        print("Error: source and instance are the same directory.")
        print("Run this script from the source repo, not from the instance.")
        sys.exit(1)

    is_new = create_instance(args.dry_run)
    if is_new:
        log("created instance directory")

    changed = copy_code_files(args.dry_run)
    if not changed and not is_new:
        log("code files already up to date")

    if is_new:
        init_git(args.dry_run)
    elif changed:
        commit_update(changed, args.dry_run)
        log("committed update")

    print()
    platforms = detect_platforms()
    if not platforms:
        print("No supported platforms found (~/.claude or ~/.cursor).")
    else:
        print(f"Configuring platforms: {', '.join(platforms)}...\n")
        for platform in platforms:
            if platform == "claude-code":
                install_claude_hooks(args.dry_run)
            elif platform == "cursor":
                install_cursor_hooks(args.dry_run)
        install_commands(args.dry_run)

    print("\nDone." + (" Start a new conversation to verify." if is_new else ""))
    if args.dry_run:
        print("\nRe-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
