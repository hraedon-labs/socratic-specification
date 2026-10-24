from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts.score_eval_run import schema_errors, score_eval_run


def _case() -> dict:
    return yaml.safe_load(
        """
id: scoring-case
case_version: 2
mode: greenfield
purpose: Test scoring.
input:
  vibe_spec: Test scoring.
  available_context: []
attention_budget:
  maximum_human_questions: 0
  rationale: No questions are needed.
expected_obligations:
  - id: OB-01
    severity: critical
    deadline: pre_synthesis
    obligation: Find the critical issue.
    rationale: Test.
  - id: OB-02
    severity: important
    deadline: work_decomposition
    obligation: Find the important issue.
    rationale: Test.
anti_obligations:
  - id: ANTI-01
    anti_obligation: Do not invent a framework choice.
    rationale: Test.
"""
    )


def _run() -> dict:
    return {
        "run_version": 2,
        "case_id": "scoring-case",
        "process_revision": "abc123",
        "obligations": [
            {
                "id": "OB-01",
                "status": "surfaced",
                "stage": "elicitation",
                "evidence": "Question 1",
            },
            {
                "id": "OB-02",
                "status": "surfaced",
                "stage": "pre_handoff",
                "evidence": "Plan review",
            },
        ],
        "anti_obligations": [
            {"id": "ANTI-01", "status": "committed", "evidence": "Draft spec"}
        ],
        "human_questions": [
            {
                "question": "Which database is already configured?",
                "necessity": "discoverable_from_context",
                "evidence": "Repository manifest",
            }
        ],
        "corrections": 2,
        "artifact_validation": {
            "schema": "pass",
            "readiness": "fail",
            "generated_views_sync": "not_run",
        },
    }


def test_score_keeps_recall_attention_and_artifact_results_separate() -> None:
    report, errors = score_eval_run(_case(), _run())

    assert errors == []
    assert report is not None
    assert report["obligation_recall"] == {
        "critical_on_time": 1,
        "critical_total": 1,
        "important_on_time": 0,
        "important_total": 1,
        "late": ["OB-02"],
        "missed": [],
    }
    assert report["anti_obligations"]["committed_count"] == 1
    assert report["human_attention"]["unnecessary_question_count"] == 1
    assert report["human_attention"]["over_budget_by"] == 1
    assert report["artifact_validation"]["readiness"] == "fail"
    assert report["weighted_signal"] == -1


def test_score_rejects_missing_or_duplicate_judgments() -> None:
    run = _run()
    run["obligations"] = [run["obligations"][0], run["obligations"][0]]

    report, errors = score_eval_run(_case(), run)

    assert report is None
    assert any("duplicate obligation judgments" in error for error in errors)
    assert any("missing obligation judgments" in error for error in errors)


def test_score_rejects_duplicate_expected_obligation_ids_before_dict_collapse() -> None:
    case = _case()
    case["expected_obligations"].append(case["expected_obligations"][0])

    report, errors = score_eval_run(case, _run())

    assert report is None
    assert errors == ["duplicate expected obligation IDs: ['OB-01']"]


def test_score_cli_rejects_whitespace_only_evidence(tmp_path: Path) -> None:
    case_path = tmp_path / "case.yaml"
    run_path = tmp_path / "run.yaml"
    case_path.write_text(yaml.safe_dump(_case(), sort_keys=False))
    run = _run()
    run["run_version"] = 2
    run["obligations"][0]["evidence"] = " \t "
    run_path.write_text(yaml.safe_dump(run, sort_keys=False))

    result = subprocess.run(
        [sys.executable, "scripts/score_eval_run.py", str(case_path), str(run_path)],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert f"{run_path}: $.obligations[0].evidence" in result.stderr
    assert "does not match" in result.stderr
    assert "Traceback" not in result.stderr


def test_score_cli_reports_yaml_input_path(tmp_path: Path) -> None:
    case_path = tmp_path / "case.yaml"
    run_path = tmp_path / "run.yaml"
    case_path.write_text("id: [unterminated\n")
    run_path.write_text(yaml.safe_dump(_run(), sort_keys=False))

    result = subprocess.run(
        [sys.executable, "scripts/score_eval_run.py", str(case_path), str(run_path)],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert f"{case_path}: cannot read YAML:" in result.stderr
    assert "Traceback" not in result.stderr


def test_score_cli_keeps_v1_evidence_compatibility(tmp_path: Path) -> None:
    case_path = tmp_path / "case.yaml"
    run_path = tmp_path / "run.yaml"
    case = _case()
    case["case_version"] = 1
    case_path.write_text(yaml.safe_dump(case, sort_keys=False))
    run = _run()
    run["run_version"] = 1
    run["obligations"][0]["evidence"] = " \t "
    run_path.write_text(yaml.safe_dump(run, sort_keys=False))

    result = subprocess.run(
        [sys.executable, "scripts/score_eval_run.py", str(case_path), str(run_path)],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "scoring-case" in result.stdout


def test_score_rejects_case_and_run_version_mismatch() -> None:
    run = _run()
    run["run_version"] = 1

    report, errors = score_eval_run(_case(), run)

    assert report is None
    assert errors == ["case_version and run_version must match (2 != 1)"]


def test_score_cli_reports_invalid_utf8_without_traceback(tmp_path: Path) -> None:
    case_path = tmp_path / "case.yaml"
    run_path = tmp_path / "run.yaml"
    case_path.write_bytes(b"case_version: \xff\n")
    run_path.write_text(yaml.safe_dump(_run(), sort_keys=False))

    result = subprocess.run(
        [sys.executable, "scripts/score_eval_run.py", str(case_path), str(run_path)],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert f"{case_path}: cannot read YAML: invalid UTF-8" in result.stderr
    assert "Traceback" not in result.stderr


def test_score_reports_invalid_schema_json_with_path(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{not-json")

    errors = schema_errors(_case(), schema_path, "case.yaml")

    assert len(errors) == 1
    assert f"case.yaml: {schema_path}: invalid schema:" in errors[0]


@pytest.mark.parametrize("field", ["case_version", "run_version"])
@pytest.mark.parametrize("version", [
    [], [2], {"value": 2}, {2}, True, False, "2", 1.5, 3, float("nan"), float("inf"),
])
def test_score_cli_reports_unsupported_version_without_traceback(
    tmp_path: Path, field: str, version: object,
) -> None:
    case = _case()
    run = _run()
    (case if field == "case_version" else run)[field] = version
    case_path = tmp_path / "case.yaml"
    run_path = tmp_path / "run.yaml"
    case_path.write_text(yaml.safe_dump(case, sort_keys=False))
    run_path.write_text(yaml.safe_dump(run, sort_keys=False))

    result = subprocess.run(
        [sys.executable, "scripts/score_eval_run.py", str(case_path), str(run_path)],
        cwd=Path(__file__).parent.parent, capture_output=True, text=True,
    )

    path = case_path if field == "case_version" else run_path
    artifact = "case" if field == "case_version" else "run"
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f"{path}: $.{field}: unsupported {artifact} schema version "
        f"{version!r}; supported versions are 1 and 2\n"
    )


@pytest.mark.parametrize("version", [1, 2, 1.0, 2.0])
def test_score_cli_preserves_supported_numeric_version_forms(
    tmp_path: Path, version: int | float,
) -> None:
    case = _case()
    run = _run()
    case["case_version"] = run["run_version"] = version
    case_path = tmp_path / "case.yaml"
    run_path = tmp_path / "run.yaml"
    case_path.write_text(yaml.safe_dump(case, sort_keys=False))
    run_path.write_text(yaml.safe_dump(run, sort_keys=False))

    result = subprocess.run(
        [sys.executable, "scripts/score_eval_run.py", str(case_path), str(run_path)],
        cwd=Path(__file__).parent.parent, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout)["weighted_signal"] == -1


def test_score_cli_missing_versions_keep_required_field_diagnostics(tmp_path: Path) -> None:
    case = _case()
    run = _run()
    del case["case_version"]
    del run["run_version"]
    case_path = tmp_path / "case.yaml"
    run_path = tmp_path / "run.yaml"
    case_path.write_text(yaml.safe_dump(case, sort_keys=False))
    run_path.write_text(yaml.safe_dump(run, sort_keys=False))

    result = subprocess.run(
        [sys.executable, "scripts/score_eval_run.py", str(case_path), str(run_path)],
        cwd=Path(__file__).parent.parent, capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert f"{case_path}: $: 'case_version' is a required property" in result.stderr
    assert f"{run_path}: $: 'run_version' is a required property" in result.stderr
    assert "unsupported" not in result.stderr
    assert "Traceback" not in result.stderr
