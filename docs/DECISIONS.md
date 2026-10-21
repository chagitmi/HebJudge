# Decision Log

A running record of project decisions and the reasoning behind them. New entries are added at the top of the relevant section; superseded decisions are marked, not deleted.

Format: **Decision**, **Why**, **Alternatives considered**.

---

## 2026-10-21: Specification phase

### D-01: Project concept: evaluation and red-teaming of agents in Hebrew

- **Decision:** Build an open-source tool and benchmark that evaluates LLM agents in Hebrew.
- **Why:** Existing evaluation tools and public benchmarks focus on English, or on evaluating models rather than agents. Hebrew has specific issues (no niqqud, code-switching, RTL/LTR mixing) that are poorly measured. The project works as a learning exercise, a portfolio piece, and possibly a future product.
- **Alternatives considered:** CV-matching agent, GitHub code-review agent, Hebrew invoice extraction, RAG customer-support agent, research agent, email/calendar agent. Rejected as less distinctive for a portfolio, or more crowded.

### D-02: Research questions

- **Decision:** Primary: are agents more or less vulnerable to prompt injection in Hebrew than in English? Secondary: how reliable is an LLM judge in Hebrew, and does reliability differ between languages?
- **Why:** The primary question is easy to communicate. The secondary one adds methodological depth, and judge calibration is needed anyway.
- **Alternatives considered:** (b) which task types fail more in Hebrew (too broad); (c) judge reliability alone (less connected to agent testing).

### D-03: Project name: HebJudge

- **Decision:** Name the project **HebJudge**, subtitle "Hebrew agent evaluation & red-teaming".
- **Why:** English-letter name for international discoverability (GitHub, LinkedIn, recruiters); "Heb" signals the niche; the subtitle explains scope.
- **Alternatives considered:** Ivrit-Eval (too close to the existing ivrit.ai project), Hebrew-eval (too generic, crowded space), Shofet (Hebrew word in Latin letters, less professional internationally), Hebrew-Judge, Hebrew-Agent-Eval.
- **Open:** availability on GitHub, PyPI and Hugging Face still to be verified directly.

### D-04: Target agent: online-store customer-service agent

- **Decision:** One synthetic agent that answers questions about orders, refunds and policy, with mock tools and a planted canary secret.
- **Why:** Realistic, has tools whose misuse is measurable, and holds information that can leak. One agent is enough for the first study.
- **Alternatives considered:** Internal company assistant (needs RAG and documents, more work); appointment-scheduling assistant (less interesting from a security view).

### D-05: Scenario mix: 120 parallel scenarios plus 30 Hebrew-only

- **Decision:** 60 Hebrew/English pairs with identical intent, plus 30 Hebrew-only scenarios probing language-specific weaknesses.
- **Why:** Parallel pairs support a fair language comparison (primary question). Hebrew-only scenarios locate where Hebrew specifically causes trouble.

### D-06: Single-turn scenarios only in v1

- **Decision:** No multi-turn conversations in the first version.
- **Why:** Cleaner, cheaper, easier to compare. Multi-turn multiplies design complexity and cost.
- **Revisit:** v2.

### D-07: Deterministic checks before the LLM judge

- **Decision:** Anything decidable in code (canary leakage, forbidden tool calls, format validity) is checked in code. The judge handles only what code cannot.
- **Why:** Cheaper, exact, and reduces dependence on judge error.

### D-08: Judge calibration against human labels

- **Decision:** Manually label 50 to 80 transcripts (about half Hebrew, half English), tune on half and measure on the other half, report agreement and Cohen's kappa per language.
- **Why:** Without human ground truth there is no evidence the judge is right. Held-out measurement avoids overfitting the judge prompt.

### D-09: OpenAI as the only model provider in v1

- **Decision:** Use OpenAI models for both tested models and the judge (a different model for judging than for testing).
- **Why:** Only available API key; keeps v1 simple.
- **Known risk:** Same-family self-preference bias remains possible. Documented as a limitation and measured through calibration. The adapter layer allows adding a second provider.

### D-10: Documentation language: English

- **Decision:** README and spec in English, with a short Hebrew summary at the end of the README.
- **Why:** The audience on GitHub and LinkedIn is international; the Hebrew niche is already in the name and subtitle.

### D-11: CLI in v1, user interface in v2

- **Decision:** Command-line interface only for the first version; a friendlier UI (Streamlit or Gradio) is a planned bonus.
- **Why:** Keeps the core scope small without losing the idea.

### D-12: Success is defined by work quality, not by the result

- **Decision:** A null or opposite finding (no Hebrew/English difference, or Hebrew more robust) counts as success if the work is reproducible, calibrated, transparent and well-documented.
- **Why:** Prevents inflating results, and makes the project credible as research.

### D-13: Build approach: thin slice first

- **Decision:** Build one scenario, one agent, one check and one judge end to end, then scale to 150 scenarios.
- **Why:** Surfaces integration problems early, before large investments in data.
