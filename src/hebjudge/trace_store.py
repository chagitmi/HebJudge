"""Trace store: every run saved in full to a local SQLite database (SPEC 6.1)."""

import sqlite3
from dataclasses import asdict, dataclass, fields
from pathlib import Path

DEFAULT_DB_PATH = Path("data/runs/traces.sqlite")


@dataclass(frozen=True)
class RunRecord:
    run_id: str
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


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
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
    cost_usd REAL NOT NULL
)
"""

COLUMNS = [f.name for f in fields(RunRecord)]


def connect(path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the database, creating the file and table if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def save_run(conn: sqlite3.Connection, record: RunRecord) -> None:
    placeholders = ", ".join("?" for _ in COLUMNS)
    conn.execute(
        f"INSERT INTO runs ({', '.join(COLUMNS)}) VALUES ({placeholders})",
        [asdict(record)[c] for c in COLUMNS],
    )
    conn.commit()
