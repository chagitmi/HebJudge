"""The committed example of generated scenarios must match what the generator produces today.

If templates or the example profile change, this test fails until the example is regenerated:

    hebjudge target scenarios examples/targets/prompt-agent.yaml --out examples/generated/smile-clinic
"""

from pathlib import Path

from hebjudge.schema import load_scenarios
from hebjudge.targets import load_target_file
from hebjudge.templates import generate, load_templates

ROOT = Path(__file__).parent.parent
EXAMPLE_DIR = ROOT / "examples" / "generated" / "smile-clinic"


def test_committed_example_is_up_to_date():
    profile = load_target_file(ROOT / "examples" / "targets" / "prompt-agent.yaml").profile
    expected, _ = generate(profile, load_templates())
    committed = load_scenarios([EXAMPLE_DIR])
    assert {s.id: s for s in committed} == {s.id: s for s in expected}, (
        "examples/generated/smile-clinic is out of date; regenerate it (see this file's docstring)"
    )
