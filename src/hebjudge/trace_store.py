"""Trace store: every run saved in full to a local SQLite database (SPEC 6.1)."""

import sqlite3
from dataclasses import asdict, dataclass, fields
from pathlib import Path

DEFAULT_DB_PATH = Path("data/runs/traces.sqlite")


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    batch: str
    repeat_index: int
    created_at: str
    hebjudge_version: str
    scenario_id: str
    pair_id: str | None
    language: str
    category: str
    scenario_hash: str
    system_prompt_hash: str
    agent_model: str
    agent_model_version: str
    agent_settings: str  # JSON
    user_message: str
    final_text: str
    tool_calls: str  # JSON
    agent_input_tokens: int
    agent_output_tokens: int
    agent_latency_s: float
    agent_rounds: int
    hit_round_limit: bool
    checks: str  # JSON
    attack_succeeded_in_code: bool
    needs_judge: bool
    judge_model_version: str | None
    judge_verdict: str | None
    judge_confidence: str | None
    judge_rationale: str | None
    judge_input_tokens: int | None
    judge_output_tokens: int | None
    cost_usd: float
    rejudged_from: str | None = None  # run_id of the original run, for re-evaluated records


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    batch TEXT NOT NULL,
    repeat_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    hebjudge_version TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    pair_id TEXT,
    language TEXT NOT NULL,
    category TEXT NOT NULL,
    scenario_hash TEXT NOT NULL,
    system_prompt_hash TEXT NOT NULL,
    agent_model TEXT NOT NULL,
    agent_model_version TEXT NOT NULL,
    agent_settings TEXT NOT NULL,
    user_message TEXT NOT NULL,
    final_text TEXT NOT NULL,
    tool_calls TEXT NOT NULL,
    agent_input_tokens INTEGER NOT NULL,
    agent_output_tokens INTEGER NOT NULL,
    agent_latency_s REAL NOT NULL,
    agent_rounds INTEGER NOT NULL,
    hit_round_limit INTEGER NOT NULL,
    checks TEXT NOT NULL,
    attack_succeeded_in_code INTEGER NOT NULL,
    needs_judge INTEGER NOT NULL,
    judge_model_version TEXT,
    judge_verdict TEXT,
    judge_confidence TEXT,
    judge_rationale TEXT,
    judge_input_tokens INTEGER,
    judge_output_tokens INTEGER,
    cost_usd REAL NOT NULL,
    rejudged_from TEXT
)
"""

COLUMNS = [f.name for f in fields(RunRecord)]

# Columns added after the table was first created. Older databases get them on connect.
ADDED_COLUMNS = {"rejudged_from": "TEXT"}


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    for name, sql_type in ADDED_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {sql_type}")
    conn.commit()


def connect(path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the database, creating the file and table if needed, and add any new columns."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    _migrate(conn)
    return conn


def save_run(conn: sqlite3.Connection, record: RunRecord) -> None:
    placeholders = ", ".join("?" for _ in COLUMNS)
    conn.execute(
        f"INSERT INTO runs ({', '.join(COLUMNS)}) VALUES ({placeholders})",
        [asdict(record)[c] for c in COLUMNS],
    )
    conn.commit()


def record_from_row(row: sqlite3.Row) -> RunRecord:
    """Rebuild a RunRecord from a stored row."""
    return RunRecord(**{name: row[name] for name in COLUMNS})
