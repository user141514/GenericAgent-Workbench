from __future__ import annotations

import ast
import csv
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CODE_PREFLIGHT_ENV_VAR = "GENERIC_AGENT_CODE_PREFLIGHT"

_DISABLED_VALUES = {"0", "false", "no", "off"}
_FILE_MANIFEST_NAMES = {
    "REQUIRED_FILES",
    "PRECHECK_REQUIRED_FILES",
    "CODE_RUN_REQUIRED_FILES",
}
_COLUMN_MANIFEST_NAMES = {
    "REQUIRED_COLUMNS",
    "REQUIRED_CSV_COLUMNS",
    "PRECHECK_REQUIRED_COLUMNS",
}
_SMOKE_REQUIRED_NAMES = {
    "REQUIRES_SMOKE",
    "FULL_RUN_REQUIRES_SMOKE",
    "CODE_RUN_REQUIRES_SMOKE",
}
_SMOKE_CHECKED_NAMES = {
    "SMOKE_CHECKED",
    "SMOKE_TEST_PASSED",
    "PREFLIGHT_SMOKE_CHECKED",
}
_DESTRUCTIVE_SHELL_PATTERNS = (
    r"\brm\s+-rf\b",
    r"\bRemove-Item\b(?=.*-Recurse\b)(?=.*-Force\b)",
    r"\brd\s+/s\b",
    r"\brmdir\s+/s\b",
    r"\bdel\s+/s\b",
    r"\btaskkill\b",
    r"\bStop-Process\b(?=.*-Force\b)",
    r"\bkill\s+-9\b",
    r"\bkillall\b",
    r"\bpkill\b",
)


@dataclass(frozen=True)
class CodePreflightResult:
    allowed: bool
    checks: dict[str, bool]
    blocked_reasons: list[str]
    warnings: list[str]
    suggested_next_step: str = ""

    def to_tool_message(self) -> str:
        if self.allowed:
            if not self.warnings:
                return "[Code Preflight] Passed."
            lines = ["[Code Preflight] Passed with warnings:"]
            lines.extend(f"- {warning}" for warning in self.warnings)
            return "\n".join(lines)

        lines = ["[Code Preflight Blocked]", "Execution was not started because preflight checks failed:"]
        lines.extend(f"- {reason}" for reason in self.blocked_reasons)
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in self.warnings)
        if self.suggested_next_step:
            lines.append(f"Required next step: {self.suggested_next_step}")
        return "\n".join(lines)


def code_preflight_enabled() -> bool:
    return os.environ.get(CODE_PREFLIGHT_ENV_VAR, "1").strip().lower() not in _DISABLED_VALUES


def evaluate_code_run_preflight(
    code: str,
    code_type: str,
    cwd: str,
    args: dict[str, Any] | None = None,
) -> CodePreflightResult:
    args = args or {}
    if not code_preflight_enabled():
        return CodePreflightResult(
            allowed=True,
            checks={"enabled": False},
            blocked_reasons=[],
            warnings=[],
        )

    checks = {
        "enabled": True,
        "python_syntax": True,
        "required_files": True,
        "csv_columns": True,
        "smoke_check": True,
        "shell_policy": True,
    }
    warnings: list[str] = []
    blocked_reasons: list[str] = []

    if _normalize_code_type(code_type) != "python":
        shell_failures = _check_shell_policy(code or "")
        if shell_failures:
            checks["shell_policy"] = False
            blocked_reasons.extend(shell_failures)
            return CodePreflightResult(
                allowed=False,
                checks=checks,
                blocked_reasons=blocked_reasons,
                warnings=warnings,
                suggested_next_step="replace destructive shell commands with scoped, verified file operations",
            )
        return CodePreflightResult(
            allowed=True,
            checks=checks,
            blocked_reasons=[],
            warnings=[f"non_python_code_type:{code_type}"],
        )

    try:
        tree = ast.parse(code or "")
    except SyntaxError as exc:
        checks["python_syntax"] = False
        blocked_reasons.append(
            f"syntax_error: line {exc.lineno or '?'}: {exc.msg}"
        )
        return CodePreflightResult(
            allowed=False,
            checks=checks,
            blocked_reasons=blocked_reasons,
            warnings=warnings,
            suggested_next_step=(
                "fix the syntax first; use py_compile/compile on the smallest script before running the experiment"
            ),
        )

    manifest_files, column_manifest_values, manifest_requires_smoke, manifest_smoke_checked = _extract_manifests(tree)
    inferred_csv_files, inferred_column_contracts = _infer_pandas_csv_contracts(tree)

    required_files = set(manifest_files)
    required_files.update(inferred_csv_files)

    column_contracts = list(inferred_column_contracts)
    column_contracts.extend(_column_contracts_from_manifests(column_manifest_values, inferred_csv_files))
    required_files.update(path for path, _columns in column_contracts if path)

    missing_files = _missing_required_files(required_files, cwd)
    if missing_files:
        checks["required_files"] = False
        for missing in missing_files:
            blocked_reasons.append(f"missing_required_file: {missing}")

    column_failures = _check_csv_columns(column_contracts, cwd, blocked_paths={item for item in missing_files})
    if column_failures:
        checks["csv_columns"] = False
        blocked_reasons.extend(column_failures)

    requires_smoke = (
        _truthy(args.get("requires_smoke"))
        or _truthy(args.get("full_run"))
        or manifest_requires_smoke
    )
    smoke_checked = (
        _truthy(args.get("smoke_checked"))
        or _truthy(args.get("smoke_passed"))
        or manifest_smoke_checked
    )
    if requires_smoke and not smoke_checked:
        checks["smoke_check"] = False
        blocked_reasons.append("missing_smoke_check: full or risky run requires a passed smoke/minimal check first")

    return CodePreflightResult(
        allowed=not blocked_reasons,
        checks=checks,
        blocked_reasons=blocked_reasons,
        warnings=warnings,
        suggested_next_step=_suggest_next_step(blocked_reasons),
    )


def _normalize_code_type(code_type: str) -> str:
    normalized = str(code_type or "python").strip().lower()
    if normalized in {"py", "python3"}:
        return "python"
    return normalized


def _check_shell_policy(code: str) -> list[str]:
    failures: list[str] = []
    for pattern in _DESTRUCTIVE_SHELL_PATTERNS:
        if re.search(pattern, code or "", re.IGNORECASE):
            failures.append(f"destructive_shell_command: {pattern}")
    return failures


def _extract_manifests(tree: ast.AST) -> tuple[set[str], list[Any], bool, bool]:
    required_files: set[str] = set()
    column_manifest_values: list[Any] = []
    requires_smoke = False
    smoke_checked = False

    for name, value in _iter_literal_assignments(tree):
        if name in _FILE_MANIFEST_NAMES:
            required_files.update(_string_items(value))
        elif name in _COLUMN_MANIFEST_NAMES:
            column_manifest_values.append(value)
        elif name in _SMOKE_REQUIRED_NAMES:
            requires_smoke = requires_smoke or _truthy(value)
        elif name in _SMOKE_CHECKED_NAMES:
            smoke_checked = smoke_checked or _truthy(value)

    return required_files, column_manifest_values, requires_smoke, smoke_checked


def _iter_literal_assignments(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except Exception:
                continue
            for target in node.targets:
                yield from ((name, value) for name in _assigned_names(target))
        elif isinstance(node, ast.AnnAssign):
            try:
                value = ast.literal_eval(node.value) if node.value is not None else None
            except Exception:
                continue
            for name in _assigned_names(node.target):
                yield name, value


def _assigned_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for item in target.elts:
            names.extend(_assigned_names(item))
        return names
    return []


def _infer_pandas_csv_contracts(tree: ast.AST) -> tuple[set[str], list[tuple[str, tuple[str, ...]]]]:
    csv_sources: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not _is_read_csv_call(node.value):
            continue
        csv_path = _first_string_arg(node.value)
        if not csv_path:
            continue
        for target in node.targets:
            for name in _assigned_names(target):
                csv_sources[name] = csv_path

    column_contracts: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript) or not isinstance(node.value, ast.Name):
            continue
        csv_path = csv_sources.get(node.value.id)
        column_name = _string_subscript(node.slice)
        if csv_path and column_name:
            column_contracts.setdefault(csv_path, set()).add(column_name)

    return set(csv_sources.values()), [
        (path, tuple(sorted(columns))) for path, columns in sorted(column_contracts.items())
    ]


def _is_read_csv_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "read_csv"
    if isinstance(func, ast.Attribute):
        return func.attr == "read_csv"
    return False


def _first_string_arg(call: ast.Call) -> str | None:
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _string_subscript(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _column_contracts_from_manifests(
    values: list[Any],
    inferred_csv_files: set[str],
) -> list[tuple[str | None, tuple[str, ...]]]:
    contracts: list[tuple[str | None, tuple[str, ...]]] = []
    fallback_file = next(iter(inferred_csv_files), None) if len(inferred_csv_files) == 1 else None

    for value in values:
        if isinstance(value, dict):
            for path, columns in value.items():
                if not isinstance(path, str):
                    continue
                column_names = tuple(_string_items(columns))
                if column_names:
                    contracts.append((path, column_names))
        else:
            column_names = tuple(_string_items(value))
            if column_names:
                contracts.append((fallback_file, column_names))
    return contracts


def _string_items(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if isinstance(item, str)]
    return []


def _missing_required_files(required_files: set[str], cwd: str) -> list[str]:
    missing: list[str] = []
    for file_name in sorted(required_files):
        path = _resolve_path(file_name, cwd)
        if not path.exists():
            missing.append(file_name)
    return missing


def _check_csv_columns(
    column_contracts: list[tuple[str | None, tuple[str, ...]]],
    cwd: str,
    blocked_paths: set[str],
) -> list[str]:
    failures: list[str] = []
    for file_name, required_columns in column_contracts:
        if not required_columns:
            continue
        if not file_name:
            failures.append(
                "unbound_required_columns: "
                + ", ".join(required_columns)
                + " (declare REQUIRED_COLUMNS as {'file.csv': ['column']})"
            )
            continue
        if file_name in blocked_paths:
            continue
        path = _resolve_path(file_name, cwd)
        if not path.exists():
            continue
        try:
            available = _read_csv_header(path)
        except Exception as exc:
            failures.append(f"csv_header_error: {file_name}: {exc}")
            continue
        missing = [column for column in required_columns if column not in available]
        if missing:
            preview = ", ".join(available[:12])
            suffix = "" if len(available) <= 12 else ", ..."
            failures.append(
                f"missing_csv_columns: {file_name}: missing={missing}; available=[{preview}{suffix}]"
            )
    return failures


def _read_csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _resolve_path(file_name: str, cwd: str) -> Path:
    path = Path(file_name)
    if not path.is_absolute():
        path = Path(cwd) / path
    return path


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _suggest_next_step(blocked_reasons: list[str]) -> str:
    if not blocked_reasons:
        return ""
    if any(reason.startswith("syntax_error") for reason in blocked_reasons):
        return "fix syntax and run a compile/py_compile check before any full execution"
    if any(reason.startswith("missing_required_file") for reason in blocked_reasons):
        return "create the required input file or correct cwd/path before rerunning"
    if any("csv" in reason or "columns" in reason for reason in blocked_reasons):
        return "inspect the CSV header, align the feature names, then rerun a small smoke case"
    if any("smoke" in reason for reason in blocked_reasons):
        return "run a minimal smoke test first; set SMOKE_CHECKED=True only after it passes"
    return "resolve the listed preflight failures before rerunning code_run"
