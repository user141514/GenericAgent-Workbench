from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PerformanceFinding:
    rule: str
    path: str
    message: str
    severity: str = "high"


DEFAULT_MAX_TOTAL_BYTES = 1_500_000
DEFAULT_MAX_JS_BYTES = 450_000
DEFAULT_MAX_CSS_BYTES = 80_000
DEFAULT_MAX_ASSET_COUNT = 32


def _asset_files(dist_dir: Path) -> list[Path]:
    if not dist_dir.exists():
        return []
    return [path for path in dist_dir.rglob("*") if path.is_file()]


def check_react_dist_budget(
    dist_dir: str | Path,
    *,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_js_bytes: int = DEFAULT_MAX_JS_BYTES,
    max_css_bytes: int = DEFAULT_MAX_CSS_BYTES,
    max_asset_count: int = DEFAULT_MAX_ASSET_COUNT,
) -> list[PerformanceFinding]:
    root = Path(dist_dir)
    findings: list[PerformanceFinding] = []
    files = _asset_files(root)

    if not files:
        return [
            PerformanceFinding(
                "missing_react_dist",
                str(root),
                "React production build output is missing. Run npm run build before release.",
            )
        ]

    index_html = root / "index.html"
    if not index_html.exists():
        findings.append(
            PerformanceFinding(
                "missing_index_html",
                str(index_html),
                "React build is missing index.html.",
            )
        )

    total_bytes = sum(path.stat().st_size for path in files)
    if total_bytes > max_total_bytes:
        findings.append(
            PerformanceFinding(
                "react_dist_total_budget",
                str(root),
                f"React dist size is {total_bytes} bytes, above budget {max_total_bytes}.",
            )
        )

    if len(files) > max_asset_count:
        findings.append(
            PerformanceFinding(
                "react_dist_asset_count",
                str(root),
                f"React dist has {len(files)} files, above budget {max_asset_count}.",
                severity="medium",
            )
        )

    for path in files:
        size = path.stat().st_size
        suffix = path.suffix.lower()
        rel = str(path.relative_to(root))
        if suffix == ".js" and size > max_js_bytes:
            findings.append(
                PerformanceFinding(
                    "react_js_bundle_budget",
                    rel,
                    f"JavaScript asset is {size} bytes, above budget {max_js_bytes}.",
                )
            )
        elif suffix == ".css" and size > max_css_bytes:
            findings.append(
                PerformanceFinding(
                    "react_css_bundle_budget",
                    rel,
                    f"CSS asset is {size} bytes, above budget {max_css_bytes}.",
                    severity="medium",
                )
            )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release performance budget gate.")
    parser.add_argument("--react-dist", default="frontends/react_app/dist")
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--max-js-bytes", type=int, default=DEFAULT_MAX_JS_BYTES)
    parser.add_argument("--max-css-bytes", type=int, default=DEFAULT_MAX_CSS_BYTES)
    parser.add_argument("--max-asset-count", type=int, default=DEFAULT_MAX_ASSET_COUNT)
    args = parser.parse_args(argv)

    findings = check_react_dist_budget(
        args.react_dist,
        max_total_bytes=args.max_total_bytes,
        max_js_bytes=args.max_js_bytes,
        max_css_bytes=args.max_css_bytes,
        max_asset_count=args.max_asset_count,
    )
    for finding in findings:
        print(f"[{finding.severity}] {finding.rule}: {finding.path}: {finding.message}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
