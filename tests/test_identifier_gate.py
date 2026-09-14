from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
GATE = REPO_ROOT / "scripts" / "check_committed_identifiers.py"
ENV_NAME = "FORBIDDEN_IDENTIFIERS"


def _run_gate(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop(ENV_NAME, None)
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        cwd=cwd or REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _repo_declaring(tmp_path: Path, visibility: str) -> Path:
    """A throwaway repo root whose publication.toml declares `visibility`.

    The gate resolves its root with `git rev-parse --show-toplevel`, so the dir
    must be a real repo for the declaration to be found.
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "publication.toml").write_text(
        f'[publication]\nremote_owner = "x"\nauthor_email = ["a@b"]\n'
        f'visibility = "{visibility}"\n',
        encoding="utf-8",
    )
    return tmp_path


def test_identifier_gate_is_optional_when_repo_is_not_public(tmp_path: Path) -> None:
    """An unconfigured gate stays a no-op where publication is not yet declared.

    Keeps a fresh clone or a fork without the secret usable.
    """
    root = _repo_declaring(tmp_path, "private-until-review")
    result = _run_gate(cwd=root)

    assert result.returncode == 0
    assert "skipping identifier gate" in result.stderr


def test_identifier_gate_fails_closed_when_repo_is_public(tmp_path: Path) -> None:
    """The same unconfigured gate must FAIL once the repo declares public.

    Fail-closed used to need an explicit --require-denylist flag, which nothing
    in CI ever passed: the behaviour was tested but not wired. It is now driven
    by publication.toml, so the repos that need it get it without remembering a
    flag. This is the negative control for the test above — the declared
    visibility is the only difference between them.
    """
    root = _repo_declaring(tmp_path, "public")
    result = _run_gate(cwd=root)

    assert result.returncode == 1
    assert "empty or unset" in result.stderr
    assert "silent pass" in result.stderr
