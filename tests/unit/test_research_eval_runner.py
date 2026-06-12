from __future__ import annotations

import json

from tests.evaluation.research_eval_runner import run_offline_ab
from tests.evaluation.research_workflow_cases import RESEARCH_WORKFLOW_CASES


def test_research_workflow_cases_have_positive_and_negative_controls():
    expected = {case.expected_trigger for case in RESEARCH_WORKFLOW_CASES}
    control_types = {case.control_type for case in RESEARCH_WORKFLOW_CASES}

    assert expected == {False, True}
    assert {"positive", "hard", "negative"} <= control_types


def test_offline_ab_runner_writes_comparison_files(tmp_path, monkeypatch):
    monkeypatch.delenv("GENERIC_AGENT_RESEARCH_WORKFLOW", raising=False)
    result = run_offline_ab(output_root=tmp_path)
    output_dir = result["output_dir"]

    assert (output_dir / "baseline.json").is_file()
    assert (output_dir / "gated.json").is_file()
    assert (output_dir / "comparison.json").is_file()
    assert (output_dir / "comparison.md").is_file()

    comparison = json.loads((output_dir / "comparison.json").read_text(encoding="utf-8"))
    assert comparison["quality_delta"]["workflow_score_mean"] >= 0.15
    assert comparison["quality_delta"]["minimal_experiment_score"] >= 0.2
    assert comparison["quality_delta"]["failure_ledger_score"] >= 0.2
    assert comparison["gated"]["negative_false_positive_rate"] <= 0.1
    assert comparison["gated"]["context_chars_p95"] <= 1800
    assert comparison["gated"]["latency_p95_ms"] <= 25


def test_offline_ab_runner_does_not_write_tracked_eval_report(tmp_path):
    result = run_offline_ab(output_root=tmp_path)

    assert result["output_dir"].parent == tmp_path
    assert result["output_dir"].name.startswith("research_eval_")
