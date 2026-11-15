import json
from pathlib import Path

import pytest
from test_trace_store import make_record

from hebjudge.calibration import (
    cohen_kappa,
    labeling_items,
    render_labeling_html,
    score,
    select_sample,
)
from hebjudge.schema import load_scenarios

SCENARIOS_DIR = Path(__file__).parent.parent / "data" / "scenarios"


def rows_for_sampling():
    rows = []
    for language in ("he", "en"):
        for verdict in ("fail", "pass"):
            for k in range(12):
                rows.append(
                    make_record(
                        run_id=f"{language}-{verdict}-{k}",
                        scenario_id=f"leak-001-{language}",
                        agent_model=f"{verdict}-model-{k}",  # distinct cells
                        language=language,
                        category=["leakage", "direct_injection"][k % 2],
                        judge_verdict=verdict,
                    ).__dict__
                )
    # a code-decided run and a second repeat of a sampled cell must never be chosen
    rows.append(make_record(run_id="code", judge_verdict=None).__dict__)
    rows.append(
        make_record(
            run_id="zz-repeat",
            scenario_id="leak-001-he",
            agent_model="model-0",
            language="he",
            judge_verdict="fail",
        ).__dict__
    )
    return rows


def test_sample_is_balanced_reproducible_and_split():
    rows = rows_for_sampling()
    sample = select_sample(rows, per_language=8)
    by_id = {r["run_id"]: r for r in rows}
    strata = {}
    for e in sample:
        r = by_id[e["run_id"]]
        strata[(r["language"], r["judge_verdict"])] = (
            strata.get((r["language"], r["judge_verdict"]), 0) + 1
        )
    assert strata == {("he", "fail"): 4, ("he", "pass"): 4, ("en", "fail"): 4, ("en", "pass"): 4}
    assert {e["split"] for e in sample} == {"tune", "test"}
    assert "code" not in by_id or all(e["run_id"] != "code" for e in sample)
    assert sample == select_sample(rows, per_language=8)  # same seed, same sample
    assert sample != select_sample(rows, per_language=8, seed=1)


def test_cohen_kappa():
    assert cohen_kappa(["pass", "fail"], ["pass", "fail"]) == 1
    assert cohen_kappa(["pass", "pass", "fail", "fail"], ["pass", "fail", "pass", "fail"]) == 0
    assert cohen_kappa(["pass", "pass"], ["pass", "pass"]) is None  # no variation
    assert cohen_kappa([], []) is None


def test_labeling_page_is_blind_and_escaped():
    scenarios = {s.id: s for s in load_scenarios([SCENARIOS_DIR])}
    row = make_record(
        run_id="r1",
        scenario_id="leak-001-he",
        language="he",
        final_text="</script><b>שלום</b>",
        judge_verdict="fail",
        judge_rationale="SECRET-RATIONALE",
        agent_model_version="SECRET-MODEL",
    ).__dict__
    items = labeling_items([{"run_id": "r1", "split": "tune"}], {"r1": row}, scenarios)
    assert "judge_verdict" not in items[0] and "agent_model" not in items[0]
    page = render_labeling_html(items, "test-sample")
    assert "SECRET-RATIONALE" not in page and "SECRET-MODEL" not in page
    assert "</script><b>" not in page  # cannot break out of the embedded data
    assert "שלום" in page


def test_score_agreement_kappa_and_disagreements():
    rows = {
        "a": {
            "judge_verdict": "fail",
            "language": "he",
            "scenario_id": "s1",
            "judge_rationale": "x",
        },
        "b": {
            "judge_verdict": "pass",
            "language": "he",
            "scenario_id": "s2",
            "judge_rationale": "y",
        },
        "c": {
            "judge_verdict": "fail",
            "language": "en",
            "scenario_id": "s3",
            "judge_rationale": "z",
        },
        "d": {
            "judge_verdict": "pass",
            "language": "en",
            "scenario_id": "s4",
            "judge_rationale": "w",
        },
        "e": {
            "judge_verdict": "pass",
            "language": "en",
            "scenario_id": "s5",
            "judge_rationale": "v",
        },
    }
    sample = [{"run_id": k, "split": "test"} for k in rows]
    labels = {"a": "fail", "b": "pass", "c": "pass", "d": "pass", "e": "unsure"}
    result = score(labels, sample, rows)
    assert result["groups"]["all"]["n"] == 4
    assert result["groups"]["all"]["agreement"] == pytest.approx(0.75)
    assert result["groups"]["he"]["kappa"] == 1
    assert result["unsure"] == 1
    assert [d["run_id"] for d in result["disagreements"]] == ["c"]
    assert json.dumps(result["groups"])  # serializable
