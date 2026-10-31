import pytest

from hebjudge.judge import build_judge_input, judge
from hebjudge.schema import load_scenario
from hebjudge.target_agent.tools import ToolCall

SCENARIO_PATH = "data/scenarios/he/inj-direct-001-he.yaml"
HEBREW_REPLY = "מצטער, איני יכול לחשוף הוראות פנימיות."


def test_judge_input_contains_rubric_and_hebrew_reply():
    scenario = load_scenario(SCENARIO_PATH)
    text = build_judge_input(scenario, HEBREW_REPLY, [])
    assert scenario.judge_rubric in text
    assert HEBREW_REPLY in text
    assert text.index("<transcript>") < text.index(HEBREW_REPLY) < text.index("</transcript>")


def test_judge_input_keeps_hebrew_in_tool_results():
    scenario = load_scenario(SCENARIO_PATH)
    call = ToolCall("check_order_status", {"order_id": "1001"}, {"notes": "הערה בעברית"})
    assert "הערה בעברית" in build_judge_input(scenario, "", [call])


def test_judge_refuses_scenario_without_rubric():
    scenario = load_scenario(SCENARIO_PATH).model_copy(update={"judge_rubric": None})
    with pytest.raises(ValueError):
        judge(client=None, scenario=scenario, final_text="", tool_calls=[])