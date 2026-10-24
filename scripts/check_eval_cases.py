#!/usr/bin/env python3
"""Validate the process evaluation corpus and registry contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parents[1]


def _format_path(parts: object) -> str:
    result = "$"
    for part in parts:
        result += f"[{part}]" if isinstance(part, int) else f".{part}"
    return result


def _path_sort_key(parts: object) -> tuple[tuple[int, str], ...]:
    return tuple(
        (0, str(part)) if isinstance(part, int) else (1, str(part))
        for part in parts
    )


def load_mapping(path: Path) -> tuple[dict | None, list[str]]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except UnicodeError as exc:
        return None, [f"{path}: cannot read YAML: invalid UTF-8 ({exc})"]
    except (OSError, yaml.YAMLError) as exc:
        return None, [f"{path}: cannot read YAML: {exc}"]
    if not isinstance(data, dict):
        return None, [f"{path}: top level must be a mapping"]
    return data, []


def load_schema(path: Path) -> tuple[dict | None, list[str]]:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeError as exc:
        return None, [f"{path}: invalid schema: invalid UTF-8 ({exc})"]
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"{path}: invalid schema: {exc}"]
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return None, [
            f"{path}: invalid schema: {getattr(exc, 'message', str(exc))}"
        ]
    except TypeError as exc:
        return None, [f"{path}: invalid schema: {exc}"]
    return schema, []


def validate(
    data_or_path: dict | Path, path_or_schema: Path, schema_path: Path | None = None
) -> list[str]:
    if schema_path is None:
        path = Path(data_or_path)
        schema_path = path_or_schema
        data, load_errors = load_mapping(path)
        if load_errors:
            return load_errors
        assert data is not None
    else:
        data = data_or_path
        path = path_or_schema
    schema, schema_errors = load_schema(schema_path)
    if schema_errors:
        return [f"{path}: {error}" for error in schema_errors]
    assert schema is not None
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{path}: {_format_path(error.absolute_path)}: {error.message}"
        for error in sorted(
            validator.iter_errors(data), key=lambda error: _path_sort_key(error.absolute_path)
        )
    ]


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


def main() -> int:
    errors: list[str] = []
    schema_paths = {
        ROOT / "evals/case.schema.json",
        ROOT / "evals/case-v2.schema.json",
        ROOT / "evals/run.schema.json",
        ROOT / "evals/run-v2.schema.json",
    }
    valid_schemas: dict[Path, bool] = {}
    for schema_path in sorted(schema_paths):
        _, schema_errors = load_schema(schema_path)
        valid_schemas[schema_path] = not schema_errors
        errors.extend(schema_errors)
    case_ids: set[str] = set()
    for path in sorted((ROOT / "evals/cases").glob("*.yaml")):
        data, load_errors = load_mapping(path)
        errors.extend(load_errors)
        if data is None:
            continue
        version = data.get("case_version")
        case_schema = _versioned_schema(ROOT, "case", version)
        if case_schema is None:
            errors.append(
                f"{path}: $.case_version: unsupported case schema version {version!r}; "
                "supported versions are 1 and 2"
            )
            continue
        if not valid_schemas.get(case_schema, False):
            continue
        validation_errors = validate(data, path, case_schema)
        errors.extend(validation_errors)
        if validation_errors:
            continue
        case_id = data.get("id")
        if case_id in case_ids:
            errors.append(f"{path}: duplicate case ID {case_id}")
        case_ids.add(case_id)
        for field in ("expected_obligations", "anti_obligations"):
            item_ids = [item.get("id") for item in data.get(field, [])]
            if len(set(item_ids)) != len(item_ids):
                errors.append(f"{path}: duplicate IDs in {field}")

    registry_path = ROOT / "extensions/index.yaml"
    registry, load_errors = load_mapping(registry_path)
    errors.extend(load_errors)
    if registry is None:
        registry = {}
    validation_errors = validate(registry, registry_path, ROOT / "schemas/extension-registry-v1.schema.json")
    errors.extend(validation_errors)
    if validation_errors:
        registry = {}
    entries = registry.get("entries", [])
    entry_ids = {entry.get("id") for entry in entries}
    if len(entry_ids) != len(entries):
        errors.append("extensions/index.yaml: duplicate entry ID")
    for entry in entries:
        for dependency in entry.get("composes", []):
            if dependency not in entry_ids:
                errors.append(f"extensions/index.yaml: {entry.get('id')} composes unknown {dependency}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"validated {len(case_ids)} evaluation cases and {len(entries)} extension entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
