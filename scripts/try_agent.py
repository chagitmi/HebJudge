"""Run the target agent once on a scenario and print the result. Costs a few cents."""

import argparse
import sys

from dotenv import load_dotenv
from openai import OpenAI

from hebjudge.checks import run_checks
from hebjudge.schema import load_scenario
from hebjudge.target_agent.agent import run_agent


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Hebrew-safe output, also when redirected to a file

    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", help="Path to a scenario YAML file")
    parser.add_argument("--model", default="gpt-6-luna")
    args = parser.parse_args()

    load_dotenv()
    scenario = load_scenario(args.scenario)
    result = run_agent(OpenAI(), args.model, scenario.language, scenario.turns[0].content)
    outcome = run_checks(scenario, result.final_text, result.tool_calls)

    print(f"Scenario: {scenario.id}")
    print(f"Model:    {result.model_version}")
    print(f"Rounds:   {result.rounds} (hit limit: {result.hit_round_limit})")
    print(f"Tokens:   {result.input_tokens} in / {result.output_tokens} out")
    print(f"Latency:  {result.latency_s:.1f}s")
    print(f"Tools:    {[(c.name, c.arguments) for c in result.tool_calls] or 'none'}")
    for check in outcome.results:
        print(f"Check:    {check.check_type}: {check.detail}")
    print(f"Verdict:  attack succeeded={outcome.attack_succeeded}, needs judge={outcome.needs_judge}")
    print("--- Agent reply ---")
    print(result.final_text)


if __name__ == "__main__":
    main()