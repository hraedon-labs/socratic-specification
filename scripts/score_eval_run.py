#!/usr/bin/env python3
"""Validate and score one recorded Socratic-process evaluation run.

Semantic judgment stays human: the run record says whether an obligation was
surfaced and cites evidence. This tool checks that every case item was judged
exactly once, applies deadline rules, and reports attention cost separately.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parents[1]
STAGE_RANK = {
    "elicitation": 0,
    "pre_synthesis": 1,
    "work_decomposition": 2,
    "pre_handoff": 3,
    "implementation": 4,
    "not_surfaced": 5,
}


def load_mapping(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except UnicodeError as exc:
        raise ValueError(f"{path}: cannot read YAML: invalid UTF-8 ({exc})") from exc
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: cannot read YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{path}: top level must be a mapping")
    return value


def schema_errors(data: dict[str, Any], schema_path: Path, label: str) -> list[str]:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except UnicodeError as exc:
        return [f"{label}: {schema_path}: invalid schema: invalid UTF-8 ({exc})"]
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{label}: {schema_path}: invalid schema: {exc}"]
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [
            f"{label}: {schema_path}: invalid schema: "
            f"{getattr(exc, 'message', str(exc))}"
        ]
    except TypeError as exc:
        return [f"{label}: {schema_path}: invalid schema: {exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{label}: {error.json_path}: {error.message}"
        for error in sorted(
            validator.iter_errors(data), key=lambda item: _path_sort_key(item.absolute_path)
        )
    ]


def _path_sort_key(parts: object) -> tuple[tuple[int, str], ...]:
    return tuple(
        (0, str(part)) if isinstance(part, int) else (1, str(part))
        for part in parts
    )


def _versioned_schema(root: Path, artifact: str, version: object) -> Path | None:
    if version is None:
        version = 1
    if isinstance(version, bool) or not isinstance(version, (int, float)):
        return None
    filenames = {
        ("case", 1): "case.schema.json",
        ("case", 2): "case-v2.schema.json",
        ("run", 1): "run.schema.json",
        ("run", 2): "run-v2.schema.json",
    }
    filename = filenames.get((artifact, version))
    return root / "evals" / filename if filename else None


def _id_errors(
    expected: set[str], observations: list[dict[str, Any]], label: str
) -> list[str]:
    observed = [item.get("id") for item in observations]
    errors: list[str] = []
    duplicates = sorted(
        (identifier for identifier, count in Counter(observed).items() if count > 1),
        key=str,
    )
    if duplicates:
        errors.append(f"duplicate {label} judgments: {duplicates}")
    missing = sorted(expected - set(observed))
    if missing:
        errors.append(f"missing {label} judgments: {missing}")
    unknown = sorted(set(observed) - expected)
    if unknown:
        errors.append(f"unknown {label} judgments: {unknown}")
    return errors


def score_eval_run(
    case: dict[str, Any], run: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if run.get("case_id") != case.get("id"):
        errors.append(
            f"run.case_id {run.get('case_id')!r} does not match case.id {case.get('id')!r}"
        )
    case_version = case.get("case_version")
    run_version = run.get("run_version")
    if case_version is not None and run_version is not None and case_version != run_version:
        errors.append(
            "case_version and run_version must match "
            f"({case_version!r} != {run_version!r})"
        )

    expected_obligation_ids = [
        item.get("id") for item in case.get("expected_obligations", [])
    ]
    expected_anti_ids = [item.get("id") for item in case.get("anti_obligations", [])]
    for ids, label in (
        (expected_obligation_ids, "expected obligation"),
        (expected_anti_ids, "expected anti-obligation"),
    ):
        duplicates = sorted(
            (identifier for identifier, count in Counter(ids).items() if count > 1),
            key=str,
        )
        if duplicates:
            errors.append(f"duplicate {label} IDs: {duplicates}")
    if errors:
        return None, errors

    expected_obligations = {
        item["id"]: item for item in case.get("expected_obligations", []) if item.get("id")
    }
    expected_anti = {item["id"] for item in case.get("anti_obligations", []) if item.get("id")}
    obligation_observations = run.get("obligations", [])
    anti_observations = run.get("anti_obligations", [])
    errors.extend(_id_errors(set(expected_obligations), obligation_observations, "obligation"))
    errors.extend(_id_errors(expected_anti, anti_observations, "anti-obligation"))
    if errors:
        return None, errors

    observations_by_id = {item["id"]: item for item in obligation_observations}
    obligation_details: list[dict[str, Any]] = []
    critical_total = 0
    critical_on_time = 0
    important_total = 0
    important_on_time = 0
    missed: list[str] = []
    late: list[str] = []
    weighted_signal = 0

    for obligation_id, expected in expected_obligations.items():
        observed = observations_by_id[obligation_id]
        severity = expected["severity"]
        if severity == "critical":
            critical_total += 1
        else:
            important_total += 1
        surfaced = observed["status"] == "surfaced"
        on_time = surfaced and STAGE_RANK[observed["stage"]] <= STAGE_RANK[expected["deadline"]]
        if on_time:
            points = 3 if severity == "critical" else 1
            weighted_signal += points
            if severity == "critical":
                critical_on_time += 1
            else:
                important_on_time += 1
            outcome = "on_time"
        elif surfaced:
            points = -5 if severity == "critical" else 0
            weighted_signal += points
            late.append(obligation_id)
            outcome = "late"
        else:
            points = -5 if severity == "critical" else 0
            weighted_signal += points
            missed.append(obligation_id)
            outcome = "missed"
        obligation_details.append(
            {
                "id": obligation_id,
                "severity": severity,
                "deadline": expected["deadline"],
                "observed_stage": observed["stage"],
                "outcome": outcome,
                "points": points,
            }
        )

    committed_anti = sorted(
        item["id"] for item in anti_observations if item["status"] == "committed"
    )
    weighted_signal -= 3 * len(committed_anti)
    questions = run.get("human_questions", [])
    maximum_questions = case.get("attention_budget", {}).get("maximum_human_questions")
    over_budget_by = (
        max(0, len(questions) - maximum_questions)
        if isinstance(maximum_questions, int)
        else None
    )
    unnecessary_questions = [
        item["question"]
        for item in questions
        if item["necessity"] == "discoverable_from_context"
    ]
    weighted_signal -= len(unnecessary_questions)

    report = {
        "case_id": case["id"],
        "process_revision": run["process_revision"],
        "obligation_recall": {
            "critical_on_time": critical_on_time,
            "critical_total": critical_total,
            "important_on_time": important_on_time,
            "important_total": important_total,
            "late": late,
            "missed": missed,
        },
        "obligation_details": obligation_details,
        "anti_obligations": {
            "committed_count": len(committed_anti),
            "committed_ids": committed_anti,
        },
        "human_attention": {
            "question_count": len(questions),
            "maximum_human_questions": maximum_questions,
            "over_budget_by": over_budget_by,
            "unnecessary_question_count": len(unnecessary_questions),
            "unnecessary_questions": unnecessary_questions,
            "corrections": run["corrections"],
        },
        "artifact_validation": run["artifact_validation"],
        "weighted_signal": weighted_signal,
    }
    return report, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("run", type=Path)
    args = parser.parse_args(argv)

    try:
        case = load_mapping(args.case)
        run = load_mapping(args.run)
    except (TypeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    case_schema = _versioned_schema(ROOT, "case", case.get("case_version"))
    run_schema = _versioned_schema(ROOT, "run", run.get("run_version"))
    errors: list[str] = []
    if case_schema is None:
        errors.append(
            f"{args.case}: $.case_version: unsupported case schema version "
            f"{case.get('case_version')!r}; supported versions are 1 and 2"
        )
    else:
        errors.extend(schema_errors(case, case_schema, str(args.case)))
    if run_schema is None:
        errors.append(
            f"{args.run}: $.run_version: unsupported run schema version "
            f"{run.get('run_version')!r}; supported versions are 1 and 2"
        )
    else:
        errors.extend(schema_errors(run, run_schema, str(args.run)))
    if not errors:
        report, errors = score_eval_run(case, run)
    else:
        report = None
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
