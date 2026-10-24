from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts import check_eval_cases


def test_check_eval_cases_reports_bad_yaml_with_path(monkeypatch, tmp_path: Path, capsys) -> None:
    root = tmp_path
    cases = root / "evals" / "cases"
    cases.mkdir(parents=True)
    (cases / "bad.yaml").write_text("id: [unterminated\n")
    for filename in (
        "case.schema.json",
        "case-v2.schema.json",
        "run.schema.json",
        "run-v2.schema.json",
    ):
        (root / "evals" / filename).write_text(
            (Path(__file__).parent.parent / "evals" / filename).read_text()
    )
    extensions = root / "extensions"
    extensions.mkdir()
    (extensions / "index.yaml").write_text(
        (Path(__file__).parent.parent / "extensions/index.yaml").read_text()
    )
    schemas = root / "schemas"
    schemas.mkdir()
    (schemas / "extension-registry-v1.schema.json").write_text(
        (Path(__file__).parent.parent / "schemas" / "extension-registry-v1.schema.json").read_text()
    )
    monkeypatch.setattr(check_eval_cases, "ROOT", root)

    assert check_eval_cases.main() == 1

    captured = capsys.readouterr()
    assert str(cases / "bad.yaml") in captured.err
    assert "cannot read YAML" in captured.err
    assert "Traceback" not in captured.err


def test_check_eval_cases_reports_non_mapping_with_path(monkeypatch, tmp_path: Path, capsys) -> None:
    root = tmp_path
    cases = root / "evals" / "cases"
    cases.mkdir(parents=True)
    (cases / "bad.yaml").write_text("- not\n- a mapping\n")
    for filename in (
        "case.schema.json",
        "case-v2.schema.json",
        "run.schema.json",
        "run-v2.schema.json",
    ):
        (root / "evals" / filename).write_text(
            (Path(__file__).parent.parent / "evals" / filename).read_text()
    )
    extensions = root / "extensions"
    extensions.mkdir()
    (extensions / "index.yaml").write_text(
        (Path(__file__).parent.parent / "extensions/index.yaml").read_text()
    )
    schemas = root / "schemas"
    schemas.mkdir()
    (schemas / "extension-registry-v1.schema.json").write_text(
        (Path(__file__).parent.parent / "schemas" / "extension-registry-v1.schema.json").read_text()
    )
    monkeypatch.setattr(check_eval_cases, "ROOT", root)

    assert check_eval_cases.main() == 1

    captured = capsys.readouterr()
    assert str(cases / "bad.yaml") in captured.err
    assert "top level must be a mapping" in captured.err


def test_check_eval_cases_reports_schema_type_errors_with_path(monkeypatch, tmp_path: Path, capsys) -> None:
    root = tmp_path
    cases = root / "evals" / "cases"
    cases.mkdir(parents=True)
    (cases / "bad.yaml").write_text("id: 1\n")
    for filename in (
        "case.schema.json",
        "case-v2.schema.json",
        "run.schema.json",
        "run-v2.schema.json",
    ):
        (root / "evals" / filename).write_text(
            (Path(__file__).parent.parent / "evals" / filename).read_text()
        )
    extensions = root / "extensions"
    extensions.mkdir()
    (extensions / "index.yaml").write_text(
        (Path(__file__).parent.parent / "extensions/index.yaml").read_text()
    )
    schemas = root / "schemas"
    schemas.mkdir()
    (schemas / "extension-registry-v1.schema.json").write_text(
        (Path(__file__).parent.parent / "schemas" / "extension-registry-v1.schema.json").read_text()
    )
    monkeypatch.setattr(check_eval_cases, "ROOT", root)

    assert check_eval_cases.main() == 1

    captured = capsys.readouterr()
    assert f"{cases / 'bad.yaml'}: $.id:" in captured.err
    assert "is not of type 'string'" in captured.err


def test_check_eval_cases_reports_invalid_utf8_without_traceback(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    root = tmp_path
    cases = root / "evals" / "cases"
    cases.mkdir(parents=True)
    (cases / "bad.yaml").write_bytes(b"id: \xff\n")
    evals = root / "evals"
    for filename in (
        "case.schema.json",
        "case-v2.schema.json",
        "run.schema.json",
        "run-v2.schema.json",
    ):
        (evals / filename).write_bytes(
            (Path(__file__).parent.parent / "evals" / filename).read_bytes()
        )
    extensions = root / "extensions"
    extensions.mkdir()
    (extensions / "index.yaml").write_text("entries: []\n")
    schemas = root / "schemas"
    schemas.mkdir()
    (schemas / "extension-registry-v1.schema.json").write_text(
        (Path(__file__).parent.parent / "schemas" / "extension-registry-v1.schema.json").read_text()
    )
    monkeypatch.setattr(check_eval_cases, "ROOT", root)

    assert check_eval_cases.main() == 1

    captured = capsys.readouterr()
    assert f"{cases / 'bad.yaml'}: cannot read YAML: invalid UTF-8" in captured.err
    assert "Traceback" not in captured.err


def test_check_eval_cases_reports_invalid_schema_json_without_traceback(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    root = tmp_path
    evals = root / "evals"
    evals.mkdir(parents=True)
    (evals / "case.schema.json").write_text("{not-json")
    for filename in ("case-v2.schema.json", "run.schema.json", "run-v2.schema.json"):
        (evals / filename).write_text(
            (Path(__file__).parent.parent / "evals" / filename).read_text()
        )
    cases = evals / "cases"
    cases.mkdir()
    extensions = root / "extensions"
    extensions.mkdir()
    (extensions / "index.yaml").write_text("entries: []\n")
    schemas = root / "schemas"
    schemas.mkdir()
    (schemas / "extension-registry-v1.schema.json").write_text(
        (Path(__file__).parent.parent / "schemas" / "extension-registry-v1.schema.json").read_text()
    )
    monkeypatch.setattr(check_eval_cases, "ROOT", root)

    assert check_eval_cases.main() == 1

    captured = capsys.readouterr()
    assert f"{evals / 'case.schema.json'}: invalid schema:" in captured.err
    assert "Traceback" not in captured.err


def test_check_eval_cases_selects_v1_and_v2_case_schemas(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    root = tmp_path
    evals = root / "evals"
    cases = evals / "cases"
    cases.mkdir(parents=True)
    source_case = yaml.safe_load(
        (Path(__file__).parent.parent / "evals/cases/greenfield-local-tool.yaml").read_text()
    )
    v1_case = dict(source_case)
    v1_case["case_version"] = 1
    (cases / "v1.yaml").write_text(yaml.safe_dump(v1_case, sort_keys=False))
    v2_case = dict(source_case)
    v2_case["case_version"] = 2
    v2_case["id"] = "greenfield-local-tool-v2"
    (cases / "v2.yaml").write_text(yaml.safe_dump(v2_case, sort_keys=False))
    for filename in (
        "case.schema.json",
        "case-v2.schema.json",
        "run.schema.json",
        "run-v2.schema.json",
    ):
        (evals / filename).write_text(
            (Path(__file__).parent.parent / "evals" / filename).read_text()
        )
    extensions = root / "extensions"
    extensions.mkdir()
    (extensions / "index.yaml").write_text(
        (Path(__file__).parent.parent / "extensions/index.yaml").read_text()
    )
    schemas = root / "schemas"
    schemas.mkdir()
    (schemas / "extension-registry-v1.schema.json").write_text(
        (Path(__file__).parent.parent / "schemas" / "extension-registry-v1.schema.json").read_text()
    )
    monkeypatch.setattr(check_eval_cases, "ROOT", root)

    assert check_eval_cases.main() == 0

    assert "validated 2 evaluation cases" in capsys.readouterr().out


def _version_test_root(tmp_path: Path) -> Path:
    source = Path(__file__).parent.parent
    for directory, filenames in (
        ("evals", ("case.schema.json", "case-v2.schema.json", "run.schema.json", "run-v2.schema.json")),
        ("extensions", ("index.yaml",)),
        ("schemas", ("extension-registry-v1.schema.json",)),
    ):
        destination = tmp_path / directory
        destination.mkdir()
        for filename in filenames:
            (destination / filename).write_bytes((source / directory / filename).read_bytes())
    (tmp_path / "evals" / "cases").mkdir()
    return tmp_path


@pytest.mark.parametrize("version", [
    [], [2], {"value": 2}, {2}, True, False, "2", 1.5, 3, float("nan"), float("inf"),
])
def test_check_eval_cases_reports_unsupported_version_without_traceback(
    monkeypatch, tmp_path: Path, capsys, version: object,
) -> None:
    root = _version_test_root(tmp_path)
    case_path = root / "evals" / "cases" / "bad-version.yaml"
    case_path.write_text(yaml.safe_dump({"case_version": version}, sort_keys=False))
    monkeypatch.setattr(check_eval_cases, "ROOT", root)

    assert check_eval_cases.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"{case_path}: $.case_version: unsupported case schema version "
        f"{version!r}; supported versions are 1 and 2\n"
    )


@pytest.mark.parametrize("version", [1, 2, 1.0, 2.0])
def test_check_eval_cases_preserves_supported_numeric_version_forms(
    monkeypatch, tmp_path: Path, capsys, version: int | float,
) -> None:
    root = _version_test_root(tmp_path)
    case = yaml.safe_load(
        (Path(__file__).parent.parent / "evals" / "cases" / "greenfield-local-tool.yaml").read_text()
    )
    case["case_version"] = version
    (root / "evals" / "cases" / "valid.yaml").write_text(yaml.safe_dump(case, sort_keys=False))
    monkeypatch.setattr(check_eval_cases, "ROOT", root)

    assert check_eval_cases.main() == 0

    captured = capsys.readouterr()
    assert "validated 1 evaluation cases" in captured.out
    assert captured.err == ""
