from __future__ import annotations

import argparse
import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PLACEHOLDER_VALUES = {
    "",
    "changeme",
    "change-me",
    "placeholder",
    "your-key-here",
    "your-token-here",
    "your-secret-here",
    "your-password-here",
    "xxx",
    "xxxx",
}

API_KEY_RE = re.compile(r"\b(?:sk|rk|sf)-[A-Za-z0-9_-]{20,}\b")
ASSIGNMENT_RE = re.compile(
    r"(?im)^[ \t]*(?P<name>[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*)[ \t]*[:=][ \t]*[\"']?(?P<value>[^\"'\s#]+)"
)

DENIED_PUBLISH_PATTERNS = (
    ".env",
    ".env.*",
    "*/.env",
    "*/.env.*",
    "*.env",
    "*mykey*",
    "*secret*",
    "*token*",
    "*.pem",
    "*.key",
    "__pycache__",
    "__pycache__/**",
    "*/__pycache__",
    "*/__pycache__/**",
    "*.pyc",
    "*.pyo",
    "temp",
    "temp/**",
    "*/temp",
    "*/temp/**",
    "logs",
    "logs/**",
    "*/logs",
    "*/logs/**",
    "memory/chat_history.json",
    "*/memory/chat_history.json",
    "memory/catalog.sqlite",
    "*/memory/catalog.sqlite",
    "memory/L4_raw_sessions/**",
    "*/memory/L4_raw_sessions/**",
    "memory/history_memory_inbox.md",
    "*/memory/history_memory_inbox.md",
    "memory/global_mem.txt",
    "*/memory/global_mem.txt",
    "memory/global_mem_insight.txt",
    "*/memory/global_mem_insight.txt",
)


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    message: str
    severity: str = "high"


def scan_text_for_secrets(text: str, source: str = "<memory>") -> list[Finding]:
    findings: list[Finding] = []
    for match in API_KEY_RE.finditer(text):
        findings.append(
            Finding(
                rule="api_key_pattern",
                path=source,
                message=f"Possible API key-like token at character {match.start()}",
            )
        )

    for match in ASSIGNMENT_RE.finditer(text):
        raw_name = match.group("name")
        name = raw_name.lower()
        value = match.group("value").strip().strip("\"'")
        if _is_non_secret_name(name) or _is_non_secret_expression(value, name):
            continue
        if _is_placeholder(value):
            continue
        rule = "password_assignment" if "password" in name or "passwd" in name else "secret_assignment"
        findings.append(
            Finding(
                rule=rule,
                path=source,
                message=f"Possible secret value assigned to {raw_name}",
            )
        )
    return findings


def validate_npm_manifest(package_json: str | Path) -> list[Finding]:
    path = Path(package_json)
    data = json.loads(path.read_text(encoding="utf-8"))
    findings: list[Finding] = []

    publishable = not bool(data.get("private", False))
    files = _as_string_list(data.get("files"))
    build_files = _as_string_list(_nested_get(data, ["build", "files"]))
    build_resources = _as_electron_resource_paths(_nested_get(data, ["build", "extraResources"]))

    if publishable and not files:
        findings.append(
            Finding(
                rule="missing_files_whitelist",
                path=str(path),
                message="Publishable npm packages must define a strict files whitelist.",
            )
        )

    for entry in files + build_files + build_resources:
        normalized = _normalize_publish_path(entry)
        if normalized.startswith("!"):
            continue
        if _is_denied_publish_path(normalized):
            findings.append(
                Finding(
                    rule="denied_publish_path",
                    path=entry,
                    message="Package whitelist includes runtime, local-state, or secret-like path.",
                )
            )
    return findings


def validate_publish_file_list(paths: list[str], source: str = "<npm-pack>") -> list[Finding]:
    findings: list[Finding] = []
    for entry in paths:
        normalized = _normalize_publish_path(entry)
        lowered = normalized.lower()
        if lowered.startswith("/") or re.match(r"^[a-z]:/", lowered):
            findings.append(
                Finding(
                    rule="absolute_publish_path",
                    path=entry,
                    message="Package file list contains an absolute path.",
                )
            )
        if normalized.startswith("../") or "/../" in normalized:
            findings.append(
                Finding(
                    rule="parent_traversal_publish_path",
                    path=entry,
                    message="Package file list contains parent traversal.",
                )
            )
        if lowered.startswith("node_modules/") or "/node_modules/" in lowered:
            findings.append(
                Finding(
                    rule="node_modules_published",
                    path=entry,
                    message="Package file list must not include node_modules.",
                )
            )
        if _is_denied_publish_path(normalized):
            findings.append(
                Finding(
                    rule="denied_publish_file",
                    path=entry,
                    message=f"{source} includes runtime, local-state, or secret-like path.",
                )
            )
    return findings


def scan_file(path: str | Path) -> list[Finding]:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [Finding(rule="read_error", path=str(p), message=str(exc), severity="medium")]
    return scan_text_for_secrets(text, source=str(p))


def scan_paths(paths: list[str | Path]) -> list[Finding]:
    findings: list[Finding] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and not _skip_scan_file(child):
                    findings.extend(scan_file(child))
        elif path.is_file() and not _skip_scan_file(path):
            findings.extend(scan_file(path))
    return findings


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _as_electron_resource_paths(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    paths: list[str] = []
    for item in value:
        if isinstance(item, str):
            paths.append(item)
        elif isinstance(item, dict):
            for key in ("from", "to"):
                raw = item.get(key)
                if isinstance(raw, str):
                    paths.append(raw)
            paths.extend(_as_string_list(item.get("filter")))
    return paths


def _nested_get(data: dict[str, Any], keys: list[str]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _normalize_publish_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    if normalized.startswith("./"):
        return normalized[2:]
    return normalized


def _is_denied_publish_path(path: str) -> bool:
    lowered = path.lower()
    return any(fnmatch.fnmatch(lowered, pattern.lower()) for pattern in DENIED_PUBLISH_PATTERNS)


def _is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in PLACEHOLDER_VALUES:
        return True
    return lowered.startswith("your-") or lowered.startswith("<") or lowered.startswith("${")


def _is_non_secret_name(name: str) -> bool:
    if name.endswith(("tokens", "_tokens", "token_count", "_token_count", "_token_file", "token_file")):
        return True
    return name in {
        "max_tokens",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_tokens",
        "estimated_tokens",
        "estimated_prompt_tokens",
        "estimated_response_tokens",
        "tokenize",
    }


def _is_non_secret_expression(value: str, name: str = "") -> bool:
    lowered = value.strip().rstrip(",").lower()
    is_password = "password" in name or "passwd" in name
    if lowered.isdigit() and not is_password:
        return True
    if lowered in {"none", "true", "false", "null"}:
        return True
    if lowered == name:
        return True
    if lowered in {"str", "int", "float", "bool", "dict", "list", "tuple", "set", "any"}:
        return True
    expression_prefixes = (
        "os.environ",
        "os.getenv",
        "getenv",
        "cfg.get",
        "mykeys.get",
        "settings_env.get",
        "getattr",
        "str(",
        "int(",
        "float(",
        "bool(",
        "data.get",
        "request.",
        "self.",
    )
    return lowered.startswith(expression_prefixes) or "(" in lowered


def _skip_scan_file(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    if parts & {".git", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}:
        return True
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".exe", ".dll", ".pyd"}:
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release safety scanner.")
    parser.add_argument("--manifest", action="append", default=[], help="Validate npm/electron package.json.")
    parser.add_argument("--scan", action="append", default=[], help="Scan a file or directory for secret-like values.")
    args = parser.parse_args(argv)

    findings: list[Finding] = []
    for manifest in args.manifest:
        findings.extend(validate_npm_manifest(manifest))
    if args.scan:
        findings.extend(scan_paths(args.scan))

    for item in findings:
        print(f"[{item.severity}] {item.rule}: {item.path} - {item.message}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
