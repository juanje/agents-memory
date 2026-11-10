import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def memory_dir(tmp_path):
    """Create a temporary agents-memory directory structure."""
    mem = tmp_path / "agents-memory"
    mem.mkdir()
    (mem / "projects").mkdir()
    (mem / "hooks" / ".state").mkdir(parents=True)
    (mem / "commands").mkdir()

    save_cmd = mem / "commands" / "save.md"
    save_cmd.write_text("# /save\nExtract and save session memory.\n")

    return mem


@pytest.fixture
def project_dir(memory_dir):
    """Create a minimal project directory."""
    proj = memory_dir / "projects" / "test-project"
    proj.mkdir(parents=True)
    (proj / "logs").mkdir()
    (proj / "index.md").write_text("# test-project\n- Stack: python\n")
    (proj / "latest-sessions.md").write_text("# Latest sessions\n\n(No sessions recorded yet.)\n")
    (proj / "open-threads.md").write_text("# Open threads\n\n(None.)\n")
    return proj


@pytest.fixture
def transcript_file(tmp_path):
    """Create a minimal transcript file with today's date."""
    transcript = tmp_path / "transcript.jsonl"
    entries = [
        {"type": "user", "message": {"role": "user", "content": "hello"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "hi there"}]}},
    ]
    transcript.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return transcript


@pytest.fixture
def auto_save_module(memory_dir):
    """Import auto-save module with MEMORY_DIR patched."""
    import importlib.util

    hooks_dir = Path(__file__).parent.parent / "hooks"
    spec = importlib.util.spec_from_file_location("auto_save", hooks_dir / "auto-save.py")
    with patch.dict(os.environ, {"AGENT_MEMORY_DIR": str(memory_dir)}):
        mod = importlib.util.module_from_spec(spec)
        sys.modules["auto_save"] = mod
        spec.loader.exec_module(mod)
        mod.MEMORY_DIR = memory_dir
        mod.STATE_DIR = memory_dir / "hooks" / ".state"
        yield mod
    del sys.modules["auto_save"]
