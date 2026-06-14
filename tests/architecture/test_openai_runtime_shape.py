import ast
from pathlib import Path


def _class_methods(class_name: str) -> list[str]:
    tree = ast.parse(Path("core/openai_agentmain.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [item.name for item in node.body if isinstance(item, ast.FunctionDef)]
    raise AssertionError(f"class not found: {class_name}")


def test_openai_orchestrator_has_single_active_graph_builder_names():
    methods = _class_methods("OpenAIOrchestratedAgent")

    assert methods.count("_build_agent_graph") == 1
    assert methods.count("_build_dynamic_graph") == 1
    assert "_build_legacy_full_agent_graph_reference" not in methods
    assert "_build_legacy_dynamic_graph_reference" not in methods
