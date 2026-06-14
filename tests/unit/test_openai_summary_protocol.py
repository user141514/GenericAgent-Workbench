from core.openai_agentmain import _extract_summary_line


def test_openai_summary_line_extracts_and_compacts_summary_tag():
    text = "<summary>\nRead core/agent_loop.py; preparing focused fix.\n</summary>\n\nVisible answer."

    assert _extract_summary_line(text) == "Read core/agent_loop.py; preparing focused fix."


def test_openai_summary_line_falls_back_to_visible_text_without_tag():
    assert _extract_summary_line("Visible answer only.") == "Visible answer only."
