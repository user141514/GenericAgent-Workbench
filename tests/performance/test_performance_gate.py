from pathlib import Path

from tools.performance_gate import check_react_dist_budget


def test_react_dist_budget_allows_small_build(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
    (assets / "index.js").write_text("console.log('ok')", encoding="utf-8")
    (assets / "index.css").write_text("body{}", encoding="utf-8")

    assert check_react_dist_budget(dist) == []


def test_react_dist_budget_flags_large_js(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
    (assets / "large.js").write_bytes(b"x" * 11)

    findings = check_react_dist_budget(dist, max_js_bytes=10)

    assert [finding.rule for finding in findings] == ["react_js_bundle_budget"]


def test_react_dist_budget_requires_build_output(tmp_path: Path) -> None:
    findings = check_react_dist_budget(tmp_path / "missing")

    assert [finding.rule for finding in findings] == ["missing_react_dist"]
