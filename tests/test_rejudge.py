import sqlite3
from pathlib import Path

import pytest
from test_trace_store import make_record

from hebjudge.judge import JudgeResult, JudgeVerdict
from hebjudge.rejudge import rejudge_batch
from hebjudge.schema import load_scenarios
from hebjudge.trace_store import connect, save_run

SCENARIOS_DIR = Path(__file__).parent.parent / "data" / "scenarios"


def scenarios_by_id():
    return {s.id: s for s in load_scenarios([SCENARIOS_DIR])}


def fake_judge(verdict):
    calls = []

    def judge_fn(client, scenario, final_text, tool_calls):
        calls.append(scenario.id)
        return JudgeResult(
            JudgeVerdict(rationale="r", verdict=verdict, confidence="high"), "gpt-6-sol", 100, 20
        )

    judge_fn.calls = calls
    return judge_fn


def seed(conn):
    # A clean reply that the judge originally passed, and a reply that leaks the canary.
    save_run(
        conn,
        make_record(
            run_id="clean",
            batch="old",
            scenario_id="leak-001-en",
            language="en",
            category="leakage",
            final_text="Sorry, no.",
            judge_verdict="pass",
            needs_judge=True,
        ),
    )
    save_run(
        conn,
        make_record(
            run_id="leak",
            batch="old",
            scenario_id="leak-001-en",
            language="en",
            category="leakage",
            final_text="The code is CANARY-4471.",
            attack_succeeded_in_code=True,
            needs_judge=False,
        ),
    )


def test_rejudge_reuses_replies_and_reruns_only_what_needs_the_judge(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    seed(conn)
    judge_fn = fake_judge("fail")
    summary = rejudge_batch(None, conn, "old", "new", scenarios_by_id(), judge_fn=judge_fn)

    assert judge_fn.calls == ["leak-001-en"]  # only the clean reply went to the judge
    assert (summary.judged, summary.decided_in_code, summary.changed) == (1, 1, 1)
    rows = conn.execute("SELECT * FROM runs WHERE batch = 'new' ORDER BY rejudged_from").fetchall()
    assert [r["rejudged_from"] for r in rows] == ["clean", "leak"]
    assert rows[0]["final_text"] == "Sorry, no."  # the agent's reply is reused as is
    assert rows[0]["judge_verdict"] == "fail"
    assert summary.judge_cost_usd == pytest.approx((100 * 2.0 + 20 * 10.0) / 1_000_000)


def test_rejudge_skips_runs_whose_scenario_no_longer_exists(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    save_run(conn, make_record(run_id="x", batch="old", scenario_id="renamed-001-en"))
    summary = rejudge_batch(
        None, conn, "old", "new", scenarios_by_id(), judge_fn=fake_judge("pass")
    )
    assert summary.skipped == 1


def test_rejudge_only_filter(tmp_path):
    conn = connect(tmp_path / "t.sqlite")
    seed(conn)
    summary = rejudge_batch(
        None,
        conn,
        "old",
        "new",
        scenarios_by_id(),
        only={"other-001-en"},
        judge_fn=fake_judge("pass"),
    )
    assert summary.judged + summary.decided_in_code == 0


@pytest.mark.parametrize("new_batch", ["old", "existing"])
def test_rejudge_refuses_to_mix_batches(tmp_path, new_batch):
    conn = connect(tmp_path / "t.sqlite")
    seed(conn)
    save_run(conn, make_record(run_id="e", batch="existing"))
    with pytest.raises(ValueError):
        rejudge_batch(None, conn, "old", new_batch, scenarios_by_id(), judge_fn=fake_judge("pass"))


def test_connect_adds_new_columns_to_an_old_database(tmp_path):
    path = tmp_path / "old.sqlite"
    sqlite3.connect(path).execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY)").connection.commit()
    conn = connect(path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    assert "rejudged_from" in columns
