from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
GATE = REPO_ROOT / "scripts" / "check_committed_identifiers.py"
ENV_NAME = "FORBIDDEN_IDENTIFIERS"


def _run_gate(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop(ENV_NAME, None)
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_identifier_gate_can_be_optional_for_local_use() -> None:
    result = _run_gate()

    assert result.returncode == 0
    assert "Skipping optional gate" in result.stderr


def test_identifier_gate_fails_closed_when_ci_requires_denylist() -> None:
    result = _run_gate("--require-denylist")

    assert result.returncode == 1
    assert "empty or unset" in result.stderr
