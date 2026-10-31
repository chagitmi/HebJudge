import re
import sqlite3

import pytest

from hebjudge.pricing import cost_usd
from hebjudge.runner import fingerprint
from hebjudge.trace_store import COLUMNS, SCHEMA, RunRecord, connect, save_run

HEBREW_REPLY = "מצטער, איני יכול לחשוף הוראות פנימיות."


def make_record(**overrides):
    data = {name: None for name in COLUMNS}
    data.update(
        run_id="abc123",
        created_at="2026-10-31T19:00:00+00:00",
        hebjudge_version="0.1.0",
        scenario_id="inj-direct-001-he",
        pair_id="inj-direct-001",
        language="he",
        category="direct_injection",
        scenario_hash="h1",
        system_prompt_hash="h2",
        agent_model="gpt-6-luna",
        agent_model_version="gpt-6-luna",
        agent_settings="{}",
        user_message="שלום",
        final_text=HEBREW_REPLY,
        tool_calls="[]",
        agent_input_tokens=432,
        agent_output_tokens=46,
        agent_latency_s=2.8,
        agent_rounds=1,
        hit_round_limit=False,
        checks="[]",
        attack_succeeded_in_code=False,
        needs_judge=True,
        cost_usd=0.0001,
    )
    data.update(overrides)
    return RunRecord(**data)


def test_schema_matches_record_fields():
    # Guards against adding a field to RunRecord and forgetting the table (or vice versa).
    table_columns = re.findall(r"^\s+(\w+) (?:TEXT|INTEGER|REAL)", SCHEMA, re.MULTILINE)
    assert table_columns == COLUMNS


def test_save_and_read_back_keeps_hebrew(tmp_path):
    conn = connect(tmp_path / "traces.sqlite")
    save_run(conn, make_record())
    row = conn.execute("SELECT * FROM runs").fetchone()
    assert row["final_text"] == HEBREW_REPLY
    assert row["judge_verdict"] is None


def test_run_ids_are_unique(tmp_path):
    conn = connect(tmp_path / "traces.sqlite")
    save_run(conn, make_record())
    with pytest.raises(sqlite3.IntegrityError):
        save_run(conn, make_record())


def test_cost_calculation():
    assert cost_usd("gpt-6-luna", 1_000_000, 1_000_000) == pytest.approx(0.60)
    with pytest.raises(KeyError):
        cost_usd("unknown-model", 1, 1)


def test_fingerprint_is_stable_and_sensitive():
    assert fingerprint("abc") == fingerprint("abc")
    assert fingerprint("abc") != fingerprint("abd")
