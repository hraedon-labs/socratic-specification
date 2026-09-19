from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.spec_tools import render_decision_brief, render_spec

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
INSTALLER = REPO_ROOT / "scripts" / "install-spec-gate.sh"


def test_installed_gate_uses_bundled_schemas_and_correct_brief_renderer(
    tmp_path: Path,
) -> None:
    target = tmp_path / "consumer"
    target.mkdir()
    subprocess.run(["git", "init", "-q", str(target)], check=True)

    spec = yaml.safe_load((FIXTURES / "valid-spec-v2.yaml").read_text())
    (target / "spec.yaml").write_text(
        yaml.safe_dump(spec, sort_keys=False), encoding="utf-8"
    )
    (target / "spec.md").write_text(render_spec(spec), encoding="utf-8")
    brief_path = target / "decision-brief.md"
    brief_path.write_text(render_decision_brief(spec), encoding="utf-8")

    subprocess.run(["bash", str(INSTALLER), str(target)], check=True)
    assert (target / ".spec-gate" / "schemas" / "spec-v2.schema.json").is_file()

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python_link = bin_dir / "python3"
    python_link.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    python_link.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

    gate = target / ".spec-gate" / "spec-gate.sh"
    result = subprocess.run(
        ["bash", str(gate)], cwd=target, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr

    brief_path.write_text(brief_path.read_text() + "stale\n")
    stale = subprocess.run(
        ["bash", str(gate)], cwd=target, env=env, capture_output=True, text=True, check=False
    )
    assert stale.returncode == 1
    assert "generated view is stale" in stale.stderr
    assert "spec_tools.py brief" in stale.stderr


def test_installer_is_idempotent_and_removes_stale_schema_copies(tmp_path: Path) -> None:
    target = tmp_path / "consumer"
    target.mkdir()
    subprocess.run(["git", "init", "-q", str(target)], check=True)

    subprocess.run(["bash", str(INSTALLER), str(target)], check=True)
    stale = target / ".spec-gate" / "schemas" / "stale.schema.json"
    stale.write_text("stale")
    subprocess.run(["bash", str(INSTALLER), str(target)], check=True)

    assert not stale.exists()
    assert not (target / ".spec-gate" / "schemas" / "schemas").exists()
    assert (target / ".spec-gate" / "schemas" / "spec-v2.schema.json").is_file()
