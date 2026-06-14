from core.openai_runtime.progress import ClassicProgressAccumulator


def test_progress_accumulator_appends_prefix_delta_only():
    progress = ClassicProgressAccumulator()

    text = progress.apply("", "turn 1")
    text = progress.apply(text, "turn 1 + more")

    assert text == "turn 1 + more"


def test_progress_accumulator_reset_starts_new_progress_block():
    progress = ClassicProgressAccumulator()

    text = progress.apply("intro", "old")
    text = progress.apply(text, "fresh", reset=True)

    assert text == "intro\n\nold\n\nfresh"


def test_progress_accumulator_replaces_divergent_snapshot_without_duplication():
    progress = ClassicProgressAccumulator()

    text = progress.apply("intro", "old snapshot")
    text = progress.apply(text, "new snapshot")

    assert text == "intro\n\nnew snapshot"
    assert "old snapshot" not in text
