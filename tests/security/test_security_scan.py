from pathlib import Path

from tools.security_scan import (
    Finding,
    scan_text_for_secrets,
    validate_npm_manifest,
    validate_publish_file_list,
)


def test_secret_scanner_flags_obvious_api_keys_and_passwords():
    text = """
OPENAI_API_KEY=sk-test-abcdefghijklmnopqrstuvwxyz1234567890
smtp_password = "plain-mail-password"
"""

    findings = scan_text_for_secrets(text, source="sample.env")

    assert any(item.rule == "api_key_pattern" for item in findings)
    assert any(item.rule == "password_assignment" for item in findings)
    assert all(isinstance(item, Finding) for item in findings)


def test_secret_scanner_allows_templates_without_values():
    text = """
OPENAI_API_KEY=
SMTP_PASSWORD=
PLACEHOLDER=your-token-here
"""

    findings = scan_text_for_secrets(text, source=".env.template")

    assert findings == []


def test_secret_scanner_ignores_token_metrics_and_env_reads():
    text = """
max_tokens = 8192
input_tokens = 0
api_key = os.environ.get("OPENAI_API_KEY", "").strip()
CLIENT_SECRET = str(mykeys.get("client_secret", "") or "").strip()
"""

    findings = scan_text_for_secrets(text, source="runtime.py")

    assert findings == []


def test_secret_scanner_still_flags_literal_passwords():
    findings = scan_text_for_secrets('PASSWORD = "136168"', source="bad.py")

    assert [item.rule for item in findings] == ["password_assignment"]


def test_npm_manifest_requires_files_whitelist_when_publishable(tmp_path):
    package_json = tmp_path / "package.json"
    package_json.write_text(
        '{"name":"gagent-demo","version":"0.1.0","private":false}',
        encoding="utf-8",
    )

    findings = validate_npm_manifest(package_json)

    assert any(item.rule == "missing_files_whitelist" for item in findings)


def test_npm_manifest_rejects_runtime_and_secret_paths(tmp_path):
    package_json = tmp_path / "package.json"
    package_json.write_text(
        """
{
  "name": "gagent-demo",
  "version": "0.1.0",
  "private": false,
  "files": ["dist/**/*", "temp/**/*", "mykey.py", ".env"]
}
""",
        encoding="utf-8",
    )

    findings = validate_npm_manifest(package_json)
    denied = [item for item in findings if item.rule == "denied_publish_path"]

    assert {item.path for item in denied} >= {"temp/**/*", "mykey.py", ".env"}


def test_npm_manifest_allows_negated_cache_exclusions(tmp_path):
    package_json = tmp_path / "package.json"
    package_json.write_text(
        """
{
  "name": "gagent-demo",
  "version": "0.1.0",
  "private": false,
  "files": ["backend/**/*", "!backend/**/__pycache__/**", "!backend/**/*.pyc"]
}
""",
        encoding="utf-8",
    )

    assert validate_npm_manifest(package_json) == []


def test_npm_manifest_scans_electron_extra_resources(tmp_path):
    package_json = tmp_path / "package.json"
    package_json.write_text(
        """
{
  "name": "gagent-demo",
  "version": "0.1.0",
  "private": false,
  "files": ["dist/**/*"],
  "build": {
    "extraResources": [
      { "from": "backend", "to": "backend" },
      { "from": "temp", "to": "temp" },
      { "from": "python-runtime", "to": "python-runtime", "filter": ["**/*", "!**/*.pyc"] }
    ]
  }
}
""",
        encoding="utf-8",
    )

    findings = validate_npm_manifest(package_json)

    assert any(item.rule == "denied_publish_path" and item.path == "temp" for item in findings)


def test_publish_file_list_rejects_python_cache_artifacts():
    findings = validate_publish_file_list(
        [
            "package.json",
            "backend/core/api/__pycache__/server.cpython-313.pyc",
            "backend/core/api/server.pyc",
        ]
    )

    assert [item.rule for item in findings] == ["denied_publish_file", "denied_publish_file"]


def test_current_react_electron_manifest_keeps_package_private_and_build_whitelisted():
    package_json = Path("frontends/react_app/package.json")

    findings = validate_npm_manifest(package_json)

    assert findings == []
