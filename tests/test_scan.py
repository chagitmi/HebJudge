"""Tests for scans (D-43). All offline: the toy agent and a fake judge; nothing is sent anywhere."""

import json
from pathlib import Path

import pytest

import hebjudge.runner as runner
from hebjudge import scan
from hebjudge.cli import main
from hebjudge.judge import JudgeResult, JudgeVerdict, build_judge_input
from hebjudge.targets import TargetFile, load_target_file
from hebjudge.templates import load_templates
from hebjudge.trace_store import connect

ROOT = Path(__file__).parent.parent
CLINIC = ROOT / "examples" / "targets" / "prompt-agent.yaml"
TOY = ROOT / "examples" / "targets" / "toy-python.yaml"


@pytest.fixture
def fake_judge(monkeypatch):
    calls = []

    def judge(client, scenario, final_text, tool_calls, policy=None):
        calls.append(policy)
        verdict = JudgeVerdict(rationale="r", verdict="pass", confidence="high")
        return JudgeResult(verdict, "fake-judge", 1000, 100)

    monkeypatch.setattr(runner, "judge", judge)
    monkeypatch.setenv("OPENAI_API_KEY", "not-used")
    return calls


# --- selection and cost ------------------------------------------------------


def test_levels_select_the_expected_scenarios():
    profile = load_target_file(CLINIC).profile
    templates = load_templates()
    quick, _ = scan.select_scenarios(profile, templates, scan.LEVELS["quick"])
    standard, _ = scan.select_scenarios(profile, templates, scan.LEVELS["standard"])
    assert len(quick) == 25
    assert len(standard) == 70
    assert {s.pair_id.rsplit("-a", 1)[0] for s in quick if s.pair_id.startswith("tpl-")} == set(
        scan.QUICK_TEMPLATES
    )
    benign = [s for s in quick if s.category == "benign_control"]
    assert len([s for s in benign if s.language == "he"]) == 2
    assert scan.LEVELS["deep"].repeats == 3


def test_cost_estimate_knows_only_what_it_can_price():
    clinic = load_target_file(CLINIC)
    estimate = scan.estimate_cost(clinic, 25)
    assert estimate.judge_usd == pytest.approx(0.05)
    assert 0 < estimate.agent_usd < 0.01
    toy = load_target_file(TOY)
    assert scan.estimate_cost(toy, 10).agent_usd is None
    local = TargetFile.model_validate(
        {
            "name": "local",
            "target": {
                "adapter": "openai_compatible",
                "model": "gpt-4o-mini",
                "base_url": "http://localhost:11434/v1",
                "system_prompt": "x",
            },
        }
    )
    assert scan.estimate_cost(local, 10).agent_usd is None  # not billed by OpenAI


# --- permission and budget ---------------------------------------------------


def test_permission_is_remembered_per_target(tmp_path):
    path = tmp_path / "permissions.json"
    toy, clinic = load_target_file(TOY), load_target_file(CLINIC)
    assert not scan.has_permission(path, toy)
    scan.record_permission(path, toy)
    assert scan.has_permission(path, toy)
    assert not scan.has_permission(path, clinic)


def test_fingerprint_ignores_headers():
    def http(headers):
        return TargetFile.model_validate(
            {
                "name": "api",
                "target": {
                    "adapter": "http",
                    "url": "http://localhost/chat",
                    "headers": headers,
                    "body": {"m": "{{message}}"},
                    "reply_path": "r",
                },
            }
        )

    assert scan.target_fingerprint(http({"A": "1"})) == scan.target_fingerprint(http({"A": "2"}))


def test_budget_stops_new_runs():
    record = type("R", (), {"cost_usd": 0.03})()
    guarded = scan.with_budget(lambda: record, max_cost=0.05)
    guarded()
    guarded()  # spent 0.06 now
    with pytest.raises(scan.BudgetExceeded):
        guarded()


# --- judge -------------------------------------------------------------------


def test_judge_gets_the_owner_policy_instead_of_the_store_policy():
    profile = load_target_file(CLINIC).profile
    scenarios, _ = scan.select_scenarios(profile, load_templates(), scan.LEVELS["quick"])
    text = build_judge_input(scenarios[0], "שלום", None, scan.agent_policy(profile))
    assert "<agent_policy>" in text and "dental clinic" in text
    assert "<store_policy>" not in text and "Refunds are allowed" not in text


# --- CLI ---------------------------------------------------------------------


def test_dry_run_sends_nothing(tmp_path, capsys, fake_judge):
    db = tmp_path / "runs.db"
    assert main(["scan", str(TOY), "--dry-run", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "Nothing was sent" in out and "tpl-leak-002-he" in out
    assert not db.exists()
    assert fake_judge == []


def test_scan_without_permission_sends_nothing(tmp_path, monkeypatch, capsys, fake_judge):
    def no_answer(prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_answer)
    db = tmp_path / "runs.db"
    assert main(["scan", str(TOY), "--yes", "--db", str(db)]) == 1
    assert "Not confirmed" in capsys.readouterr().out
    assert not db.exists()


def test_max_cost_below_estimate_is_refused(tmp_path, capsys, fake_judge):
    db = tmp_path / "runs.db"
    args = ["scan", str(TOY), "--yes", "--confirm-permission", "--max-cost", "0.001"]
    assert main([*args, "--db", str(db)]) == 1
    assert "exceeds --max-cost" in capsys.readouterr().out


def test_scan_end_to_end_on_the_toy_agent(tmp_path, monkeypatch, capsys, fake_judge):
    monkeypatch.chdir(ROOT)
    db = tmp_path / "runs.db"
    args = ["scan", str(TOY), "--yes", "--confirm-permission", "--batch", "toy-scan"]
    assert main([*args, "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "Reveals its instructions or secrets: 2 of 4" in out  # fake system message, he + en
    assert "Leaks protected data: 2 of 4" in out  # the JSON template, he + en
    assert "Refuses legitimate requests: 0 of 3" in out
    # The judge received the owner's policy, not the store policy.
    assert fake_judge and all(
        p is not None and "example online store" in p.role for p in fake_judge
    )
    with connect(db) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM runs WHERE batch = 'toy-scan'").fetchone()[0] == 19
        )
    assert (tmp_path / "scans" / "toy-scan" / "tpl-leak-002-he.yaml").exists()
    stored = json.loads((tmp_path / "permissions.json").read_text(encoding="utf-8"))
    assert list(stored.values())[0]["name"] == "Toy agent (rule-based)"
