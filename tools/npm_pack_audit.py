from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.security_scan import Finding, validate_publish_file_list


REQUIRED_PACKAGE_FILES = {
    "package.json",
    "README.md",
    "bin/gagent-desktop.js",
    "electron/main.cjs",
    "dist/index.html",
    "backend/core/api/server.py",
    "backend/core/api/app.py",
    "backend/requirements.txt",
    "backend/requirements-desktop.txt",
}


def audit_npm_pack(package_dir: str | Path) -> list[Finding]:
    root = Path(package_dir)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    result = subprocess.run(
        [npm, "pack", "--dry-run", "--json"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return [
            Finding(
                "npm_pack_failed",
                str(root),
                (result.stderr or result.stdout or "npm pack --dry-run failed").strip(),
            )
        ]

    try:
        payload = json.loads(result.stdout)
        files = [str(item["path"]) for item in payload[0].get("files", [])]
    except Exception as exc:
        return [Finding("npm_pack_json_parse_failed", str(root), str(exc))]

    findings = validate_publish_file_list(files, source="npm pack dry-run")
    file_set = set(files)
    for required in sorted(REQUIRED_PACKAGE_FILES):
        if required not in file_set:
            findings.append(
                Finding(
                    "missing_required_package_file",
                    required,
                    "npm package dry-run is missing a required launcher artifact.",
                )
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit npm pack --dry-run file list.")
    parser.add_argument("--package-dir", default="packages/gagent-desktop")
    args = parser.parse_args(argv)

    findings = audit_npm_pack(args.package_dir)
    for finding in findings:
        print(f"[{finding.severity}] {finding.rule}: {finding.path} - {finding.message}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
