"""Data tests: every scenario file is valid, and every Hebrew/English pair is consistent."""

from pathlib import Path

import pytest

from hebjudge.schema import Scenario, load_scenario

SCENARIOS_DIR = Path(__file__).parent.parent / "data" / "scenarios"

# Everything except the language-specific fields must match between the two sides of a pair.
PAIRED_FIELDS = [
    "category",
    "attacker_goal",
    "success_checks",
    "judge_rubric",
    "expected_safe_behavior",
    "severity",
]


def load_paired(language: str) -> dict[str, Scenario]:
    scenarios = [load_scenario(p) for p in sorted((SCENARIOS_DIR / language).glob("*.yaml"))]
    for s in scenarios:
        assert s.pair_id is not None, f"{s.id} is in {language}/ but has no pair_id"
        assert s.language == language, f"{s.id} is in {language}/ but has language={s.language}"
    return {s.pair_id: s for s in scenarios}


def test_every_scenario_has_a_twin():
    he, en = load_paired("he"), load_paired("en")
    assert sorted(he) == sorted(en), (
        f"missing English twins: {sorted(set(he) - set(en))}; "
        f"missing Hebrew twins: {sorted(set(en) - set(he))}"
    )


@pytest.mark.parametrize("field", PAIRED_FIELDS)
def test_paired_fields_match(field):
    he, en = load_paired("he"), load_paired("en")
    for pair_id in he.keys() & en.keys():
        assert getattr(he[pair_id], field) == getattr(en[pair_id], field), (
            f"{pair_id}: '{field}' differs between Hebrew and English"
        )
