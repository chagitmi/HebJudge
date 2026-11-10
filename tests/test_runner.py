from pathlib import Path

import pytest
from test_trace_store import make_record

from hebjudge.runner import run_batch
from hebjudge.schema import load_scenarios
from hebjudge.trace_store import connect

SCENARIOS_DIR = Path(__file__).parent.parent / "data" / "scenarios"


def test_load_scenarios_from_directory():
    ids = [s.id for s in load_scenarios([SCENARIOS_DIR])]
    assert "leak-001-he" in ids
    assert "leak-001-en" in ids
    assert len(ids) == len(set(ids))  # no duplicate ids


def test_load_error_names_the_file(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bad.yaml"):
        load_scenarios([bad])


def test_missing_path_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_scenarios([tmp_path / "nope"])


def test_run_batch_runs_every_combination_and_survives_errors(tmp_path):
    scenarios = load_scenarios([SCENARIOS_DIR / "he"])
    calls = []

    def fake_run(client, scenario, model, batch, repeat_index):
        calls.append((scenario.id, model, repeat_index))
        if model == "gpt-4o-mini" and repeat_index == 1:
            raise RuntimeError("simulated API failure")
        return make_record(
            run_id=f"{scenario.id}-{model}-{repeat_index}",
            scenario_id=scenario.id,
            agent_model=model,
            batch=batch,
            repeat_index=repeat_index,
        )

    conn = connect(tmp_path / "traces.sqlite")
    summary = run_batch(
        None, scenarios, ["gpt-6-luna", "gpt-4o-mini"], 2, "test", conn, run_fn=fake_run
    )

    n = len(scenarios)
    assert len(calls) == n * 2 * 2  # every scenario x model x repeat was attempted
    assert summary.failed == n  # one simulated failure per scenario
    assert summary.completed == n * 3
    saved = conn.execute("SELECT COUNT(*) FROM runs WHERE batch = 'test'").fetchone()[0]
    assert saved == n * 3


def test_run_batch_rejects_unknown_model_before_running(tmp_path):
    with pytest.raises(ValueError):
        run_batch(None, [], ["gpt-unknown"], 1, "test", connect(tmp_path / "t.sqlite"))
