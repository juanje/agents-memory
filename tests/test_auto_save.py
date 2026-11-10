"""Tests for hooks/auto-save.py — TDD: written before fixes."""

import json
import os
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

VALID_CLAUDE_CODE_EVENTS = {
    "SessionStart", "SessionEnd", "Stop", "PreCompact", "PostCompact",
    "PreToolUse", "PostToolUse", "Notification", "PreModelSwitch",
    "PostModelSwitch", "PostToolBatch", "MessageDisplay", "DirectoryAdded",
    "PermissionDenied", "PermissionRequest", "StopFailure", "SubagentStart",
    "SubagentStop", "UserPromptSubmit", "TaskCreated", "TaskCompleted",
    "TeammateIdle", "InstructionsLoaded", "ConfigChange", "CwdChanged",
    "FileChanged", "WorktreeCreate", "WorktreeRemove", "Elicitation",
    "ElicitationResult", "Setup", "UserPromptExpansion",
}

VALID_CURSOR_EVENTS = {
    "sessionStart", "sessionEnd", "preCompact", "stop", "afterAgentResponse",
}


# --- Test 1: invoke_extraction must include Read in --allowedTools ---


class TestInvokeExtractionAllowedTools:
    def test_claude_cmd_includes_read(self, auto_save_module, memory_dir):
        """The extraction agent needs Read to check existing files before writing."""
        captured_cmd = []

        def fake_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            mock = MagicMock()
            mock.pid = 12345
            return mock

        with patch("auto_save.subprocess.Popen", side_effect=fake_popen):
            auto_save_module.invoke_extraction("claude", "test prompt", "test-project")

        assert "Read" in captured_cmd, (
            "Read must be in --allowedTools so the extraction agent can read "
            "existing files (latest-sessions.md, open-threads.md, logs/index.md)"
        )

    def test_claude_cmd_includes_write_edit_bash(self, auto_save_module, memory_dir):
        """Sanity: Write, Edit, and Bash(git *) must also be present."""
        captured_cmd = []

        def fake_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            mock = MagicMock()
            mock.pid = 12345
            return mock

        with patch("auto_save.subprocess.Popen", side_effect=fake_popen):
            auto_save_module.invoke_extraction("claude", "test prompt", "test-project")

        assert "Write" in captured_cmd
        assert "Edit" in captured_cmd
        assert "Bash(git *)" in captured_cmd


# --- Tests 2-3: Event name validity ---


class TestEventNames:
    def _get_event_sets(self, auto_save_module):
        """Extract the event sets from main() source code.

        Since the sets are defined inline in main(), we inspect the source.
        This is a pragmatic approach — the alternative (running main with
        mocked everything) is tested in the integration tests below.
        """
        import inspect
        source = inspect.getsource(auto_save_module.main)
        local_ns = {}
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("periodic_events") and "=" in stripped:
                exec(stripped, {}, local_ns)
            elif stripped.startswith("forced_events") and "=" in stripped:
                exec(stripped, {}, local_ns)
        return local_ns.get("periodic_events", set()), local_ns.get("forced_events", set())

    def test_all_events_are_valid_across_platforms(self, auto_save_module):
        """Every event in the sets must exist in at least one platform."""
        all_valid = VALID_CLAUDE_CODE_EVENTS | VALID_CURSOR_EVENTS
        periodic, forced = self._get_event_sets(auto_save_module)
        all_events = periodic | forced
        invalid = all_events - all_valid
        assert not invalid, f"Events not valid on any platform: {invalid}"

    def test_periodic_events_cover_both_platforms(self, auto_save_module):
        """Periodic events must include triggers for both Claude Code and Cursor."""
        periodic, _ = self._get_event_sets(auto_save_module)
        assert periodic & VALID_CLAUDE_CODE_EVENTS, "Missing Claude Code periodic event"
        assert periodic & VALID_CURSOR_EVENTS, "Missing Cursor periodic event"

    def test_forced_events_cover_both_platforms(self, auto_save_module):
        """Forced events must include triggers for both Claude Code and Cursor."""
        _, forced = self._get_event_sets(auto_save_module)
        assert forced & VALID_CLAUDE_CODE_EVENTS, "Missing Claude Code forced event"
        assert forced & VALID_CURSOR_EVENTS, "Missing Cursor forced event"


# --- Tests 4-8: Event routing integration tests ---


def _make_hook_input(event_name, session_id="test-session-123", cwd="/tmp/test-project", transcript_path=None):
    return {
        "hook_event_name": event_name,
        "session_id": session_id,
        "cwd": cwd,
        "transcript_path": str(transcript_path) if transcript_path else "",
    }


def _run_main(auto_save_module, hook_input, memory_dir, transcript_file=None, env_extras=None):
    """Run auto-save main() with controlled inputs. Returns whether Popen was called."""
    popen_called = False
    captured_cmd = []

    def fake_popen(cmd, **kwargs):
        nonlocal popen_called
        popen_called = True
        captured_cmd.extend(cmd)
        mock = MagicMock()
        mock.pid = 99999
        return mock

    env = {
        "AGENT_MEMORY_DIR": str(memory_dir),
        "HOME": str(memory_dir.parent),
    }
    if env_extras:
        env.update(env_extras)

    if transcript_file:
        hook_input["transcript_path"] = str(transcript_file)

    stdin_data = json.dumps(hook_input)

    with (
        patch.dict(os.environ, env, clear=True),
        patch("auto_save.subprocess.Popen", side_effect=fake_popen),
        patch("sys.stdin", StringIO(stdin_data)),
    ):
        auto_save_module.MEMORY_DIR = memory_dir
        auto_save_module.STATE_DIR = memory_dir / "hooks" / ".state"
        auto_save_module.main()

    return popen_called, captured_cmd


class TestEventRouting:
    def test_stop_event_increments_counter_and_skips_below_threshold(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """Stop should increment message_count but not trigger save below threshold."""
        hook_input = _make_hook_input("Stop", transcript_path=transcript_file)
        popen_called, _ = _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        assert not popen_called, "Should not save when message_count < threshold"

        state_file = memory_dir / "hooks" / ".state" / "test-session-123.json"
        if state_file.exists():
            state = json.loads(state_file.read_text())
            assert state["message_count"] == 1

    def test_stop_event_triggers_save_at_threshold(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """Stop should trigger save when threshold is reached."""
        state_dir = memory_dir / "hooks" / ".state"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "test-session-123.json"
        state_file.write_text(json.dumps({
            "message_count": auto_save_module.SAVE_THRESHOLD - 1,
            "last_save_at": 0,
            "last_processed_line": 0,
        }))

        hook_input = _make_hook_input("Stop", transcript_path=transcript_file)
        popen_called, _ = _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        assert popen_called, "Should save when message_count reaches threshold"

    def test_session_end_forces_save(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """SessionEnd should always trigger save, regardless of threshold."""
        hook_input = _make_hook_input("SessionEnd", transcript_path=transcript_file)
        popen_called, _ = _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        assert popen_called, "SessionEnd must force save regardless of message count"

    def test_precompact_forces_save(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """PreCompact should always trigger save, regardless of threshold."""
        hook_input = _make_hook_input("PreCompact", transcript_path=transcript_file)
        popen_called, _ = _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        assert popen_called, "PreCompact must force save regardless of message count"

    def test_unknown_event_is_ignored(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """Events not in periodic or forced sets should be ignored."""
        hook_input = _make_hook_input("SomeRandomEvent", transcript_path=transcript_file)
        popen_called, _ = _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        assert not popen_called, "Unknown events must not trigger save"

    # --- Cursor event routing ---

    def test_cursor_session_end_forces_save(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """Cursor's sessionEnd (camelCase) should force save."""
        hook_input = _make_hook_input("sessionEnd", transcript_path=transcript_file)
        popen_called, _ = _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        assert popen_called, "Cursor sessionEnd must force save"

    def test_cursor_precompact_forces_save(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """Cursor's preCompact (camelCase) should force save."""
        hook_input = _make_hook_input("preCompact", transcript_path=transcript_file)
        popen_called, _ = _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        assert popen_called, "Cursor preCompact must force save"

    def test_cursor_after_agent_response_uses_threshold(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """Cursor's afterAgentResponse should use threshold like Stop."""
        hook_input = _make_hook_input("afterAgentResponse", transcript_path=transcript_file)
        popen_called, _ = _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        assert not popen_called, "afterAgentResponse should not save below threshold"

    def test_cursor_stop_uses_threshold(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """Cursor's stop (lowercase) should use threshold like Stop."""
        hook_input = _make_hook_input("stop", transcript_path=transcript_file)
        popen_called, _ = _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        assert not popen_called, "Cursor stop should not save below threshold"


# --- Session/conversation ID handling ---


class TestSessionIdUsage:
    def test_state_file_uses_session_id(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """State file must be named from session_id (Claude Code)."""
        hook_input = _make_hook_input("Stop", session_id="my-session-abc")
        hook_input["transcript_path"] = str(transcript_file)

        _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        state_file = memory_dir / "hooks" / ".state" / "my-session-abc.json"
        assert state_file.exists(), (
            f"State file should be named from session_id. "
            f"Found: {list((memory_dir / 'hooks' / '.state').glob('*.json'))}"
        )

    def test_state_file_uses_conversation_id_as_fallback(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """Cursor sends conversation_id instead of session_id — must work as fallback."""
        hook_input = {
            "hook_event_name": "stop",
            "conversation_id": "cursor-conv-456",
            "cwd": str(project_dir.parent.parent.parent / "test-project"),
            "transcript_path": str(transcript_file),
        }

        _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        state_file = memory_dir / "hooks" / ".state" / "cursor-conv-456.json"
        assert state_file.exists(), (
            "Cursor uses conversation_id — must fall back to it when session_id is absent"
        )

    def test_session_id_takes_precedence_over_conversation_id(
        self, auto_save_module, memory_dir, project_dir, transcript_file
    ):
        """When both are present, session_id wins (Claude Code is the primary platform)."""
        hook_input = _make_hook_input("Stop", session_id="primary-id")
        hook_input["conversation_id"] = "fallback-id"
        hook_input["transcript_path"] = str(transcript_file)

        _run_main(auto_save_module, hook_input, memory_dir, transcript_file)

        primary = memory_dir / "hooks" / ".state" / "primary-id.json"
        fallback = memory_dir / "hooks" / ".state" / "fallback-id.json"
        assert primary.exists(), "session_id should take precedence"
        assert not fallback.exists(), "conversation_id should not be used when session_id exists"
