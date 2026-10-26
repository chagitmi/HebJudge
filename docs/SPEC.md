# HebJudge: Specification

**Hebrew agent evaluation & red-teaming**

| | |
|---|---|
| Status | Draft v0.1 (specification approved, implementation not started) |
| Last updated | October 2026 |
| Repository | https://github.com/chagitmi/HebJudge |
| License | Code: MIT. Data: CC BY 4.0 (planned) |

---

## 1. Purpose, research questions and scope

### 1.1 Problem

Mainstream agent-evaluation tooling was built around English. There is little public measurement of how LLM-based agents behave in Hebrew, where several language-specific issues arise:

- Unvocalized script (no niqqud), which creates ambiguity.
- Code-switching between Hebrew and English inside a single sentence.
- Right-to-left text mixed with left-to-right tokens (numbers, URLs, JSON), which can break structured output.
- Slang and transliteration.

Existing Hebrew benchmarks mostly evaluate *models* (comprehension, sentiment, translation, speech recognition). Evaluating *agents* (tool use, prompt injection, data leakage) and the reliability of *LLM judges* in Hebrew appears to be much less covered. HebJudge targets that gap.

### 1.2 Research questions

- **Primary:** Are agents more or less vulnerable to prompt injection in Hebrew than in English?
- **Secondary:** How well does an LLM judge agree with human judgment on Hebrew transcripts, and does that agreement differ between Hebrew and English?

The secondary question is not a side topic. Every number in the primary question depends on the judge, so measuring judge reliability is part of the core method.

### 1.3 Audience

1. The author: learning and demonstrating skill.
2. Recruiters and developers reviewing the repository.
3. In the future, teams building Hebrew-language chatbots and agents.

### 1.4 In scope (v1)

- About 150 scenarios (see section 4).
- One target agent (an online-store customer-service agent).
- OpenAI models only (3 to 4 models), see section 9 for the implication.
- A calibrated LLM judge plus deterministic checks.
- A report, open code and an open dataset.

### 1.5 Out of scope (v1)

- A polished user interface (planned as a bonus in v2, e.g. Streamlit or Gradio).
- Multi-turn conversations (planned for v2).
- Support for every agent framework.
- Cloud service or monetization.
- Testing real third-party products.

---

## 2. Target agent

HebJudge evaluates other agents, so v1 needs one well-defined "subject" agent.

**Choice:** an online-store customer-service agent that answers questions about orders, refunds and store policy.

**Why this choice:** it is realistic (it resembles what real teams build), it has tools whose misuse can be measured, and it holds information that must not leak.

**Required properties:**

- **Instruction language:** the system prompt is in the scenario's language; tool definitions are in English for both (see D-16).
- **Tool policy enforcement:** mock tools do not enforce store policy. The agent's own judgment is what is tested, and every tool call is recorded so violations can be detected in code.

- **Protected information:** a system prompt and mock customer data. A fake secret (a *canary*, for example `CANARY-4471`) is planted so that leakage can be detected in code.
- **Tools:** for example `check_order_status` and `issue_refund`. Tools are mocks running over in-memory data, so results are deterministic and no real action can occur.
- **Explicit behavior rules:** so that compliance can be judged (for example, refunds only under a stated policy).
- **Language parity:** the same content and policies are available in Hebrew and English, so the comparison is fair.

Implementation: plain Python with an LLM API. No heavy agent framework in v1.

---

## 3. Scenario schema

A scenario is the unit of testing. Scenarios are YAML files validated against a Pydantic schema, so a malformed scenario fails early.

```yaml
id: inj-direct-007-he
pair_id: inj-direct-007        # English counterpart: inj-direct-007-en
language: he                   # he | en
category: direct_injection
turns:
  - role: user
    content: "..."             # single-turn in v1
attacker_goal: leak_system_prompt
success_checks:                # deterministic checks first
  - type: canary_in_output
    value: "CANARY-4471"
  - type: tool_called
    tool: issue_refund
judge_rubric: "..."            # only for what code cannot decide
expected_safe_behavior: "..."
severity: high                 # low | medium | high
hebrew_tags: [code_switching, no_niqqud]
```

**Design principles:**

- **Parallel pairs (`pair_id`):** each parallel scenario is written in Hebrew and English with the same intent and structure. This is what allows a fair language comparison.
- **Canary strings:** leakage is detected by exact match in code, with no judge needed.
- **Code before judge:** anything that can be checked in code is checked in code.

---

## 4. Scenario categories and budget

### 4.1 Parallel scenarios: 60 pairs (120 scenarios)

| Category | What it tests | Pairs |
|---|---|---|
| Direct injection | A user tries to make the agent ignore its rules | 15 |
| Indirect injection | An instruction hidden in content the agent reads (order notes, earlier messages) | 15 |
| Instruction and data leakage | The agent reveals its system prompt or other customers' data | 10 |
| Unauthorized tool action | The agent performs a refund or change it is not permitted to | 10 |
| Benign control | Legitimate, ordinary requests, to measure over-refusal | 10 |

### 4.2 Hebrew-only scenarios: 30

No English counterpart. They probe weaknesses specific to Hebrew and are reported separately:

- Code-switching between Hebrew and English.
- Ambiguity caused by missing niqqud.
- RTL/LTR mixing in structured output (JSON, addresses, numbers).
- Slang and transliteration.

### 4.3 Why a benign-control category

An agent that refuses everything looks "safe" but is useless. Without a control category, a good score cannot be distinguished from over-blocking.

### 4.4 Deliberately excluded from v1

Multi-turn conversations and complex multi-step attacks. They add richness but multiply complexity and cost.

---

## 5. Judge and calibration

### 5.1 What is checked where

| Deterministic (code) | LLM judge |
|---|---|
| Canary appears in output | Agent revealed instructions in paraphrase, without an exact quote |
| A forbidden tool was called (e.g. `issue_refund`) | Agent over-refused a legitimate request |
| Output format valid (e.g. JSON) | Agent "gave in" softly, e.g. made a commitment it is not allowed to make |

Most high-stakes decisions (leakage, unauthorized action) are deterministic.

### 5.2 Judge design

- **Input:** the scenario, its rubric, the full conversation and the tool calls made.
- **Structured output:** `pass`, `fail` or `unclear`, a short rationale and a confidence level. `unclear` cases go to manual review.
- **Judge model differs from the models under test**, to limit self-preference bias.
- **Optional experiment:** run the judge prompt in English and in Hebrew and compare.

### 5.3 Calibration against human judgment

1. Select a sample of 50 to 80 transcripts (about half Hebrew, half English) across categories.
2. The author labels them manually as `pass` or `fail`.
3. Split the sample: half for tuning the judge prompt, half held out for measurement. Report only on the held-out half.
4. Measure percent agreement and **Cohen's kappa** (agreement beyond chance), separately for Hebrew and English.
5. Compare the two languages. A clearly lower agreement in Hebrew is itself a finding.

An optional second human annotator (a Hebrew speaker, about 20 transcripts) would allow measuring inter-human agreement as a reference point.

### 5.4 Known biases to document

- Length bias (preference for longer answers).
- Self-preference bias.
- Hebrew-specific misreadings of ambiguous, unvocalized sentences.

---

## 6. Architecture and repository layout

### 6.1 Data flow

```
Scenarios (YAML) → Runner → Target Agent (+ mock tools)
                              ↓
                     Trace Store (SQLite)
                              ↓
        Deterministic Checks → Judge (LLM) → Aggregation
                                                  ↓
                                     Report + Calibration stats
```

- **Scenarios:** YAML files validated against the schema.
- **Runner:** runs each scenario against the target agent on each model, concurrently, logging cost and latency.
- **Target agent:** the customer-service agent with mock tools.
- **Trace store:** every conversation saved in full: messages, tool calls, model, model version, timestamp, cost.
- **Checks and judge:** as defined in section 5.
- **Report:** HTML report with scores by category, model and language, failure examples and calibration statistics.

### 6.2 Repository layout

```
HebJudge/
├── README.md
├── LICENSE
├── pyproject.toml
├── .env.example              # template only, no real keys
├── docs/
│   ├── SPEC.md
│   └── DECISIONS.md
├── data/
│   ├── scenarios/            # he/, en/, he_only/
│   ├── labels/               # human labels
│   └── runs/                 # raw traces (not committed)
├── src/hebjudge/
│   ├── schema.py             # scenario definition and validation
│   ├── target_agent/         # agent.py, tools.py, prompts.py
│   ├── models/               # uniform adapter over model providers
│   ├── runner.py
│   ├── checks.py             # deterministic checks
│   ├── judge.py
│   ├── calibration.py        # agreement and kappa
│   ├── report.py
│   └── cli.py                # hebjudge run / judge / report
├── tests/
└── reports/                  # final published reports
```

### 6.3 Technical decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Standard in the field |
| Schema validation | Pydantic | Bad scenarios fail early and clearly |
| Trace storage | SQLite | No server needed, queryable for analysis |
| Model access | Own thin adapter layer | Swap or add providers without touching other code |
| Execution | `asyncio` | Concurrent runs save time and cost |
| Interface | CLI | Sufficient for v1 scope |
| Testing | pytest on deterministic components | Engineering maturity |
| Reproducibility | Log model version, date, temperature and reasoning effort | Models change over time; findings must be dated (see D-15) |

### 6.4 Security and hygiene

- API keys live only in a local `.env`, which is git-ignored. Only `.env.example` is committed.
- Raw traces are not committed. Summaries and reports are.
- A spending cap is set on the provider account, with a dedicated key for this project.

### 6.5 Build approach

Build a **thin slice** first: one scenario, one agent, one check and one judge running end to end to a tiny report. Only then scale to 150 scenarios.

---

## 7. Metrics and success criteria

### 7.1 Primary metric

**Attack Success Rate (ASR):** the share of scenarios in which the attack succeeded, computed per combination of category, language and model. Always reported with a confidence interval, because the sample is small.

### 7.2 Hebrew vs. English comparison

Because every parallel scenario runs in both languages, comparison is paired: in what share of pairs does the agent fail only in Hebrew, only in English, in both, or in neither. A paired test (McNemar) assesses whether the Hebrew-only vs. English-only asymmetry exceeds chance.

### 7.3 Secondary metrics

| Metric | What it shows |
|---|---|
| Over-refusal rate on benign control | Whether "safety" comes from blocking legitimate requests |
| Judge agreement (percent and kappa), per language | Whether the judge can be trusted, and in which language less |
| `unclear` rate | How many decisions require manual review |
| Share of decisions made in code vs. by judge | How much of the result is immune to judge error |
| Cost and latency per scenario | Practical data for teams adopting the tool |
| Failure rate by Hebrew tag | Where exactly Hebrew causes trouble (Hebrew-only scenarios) |

### 7.4 Success criteria

Success is **not** defined by the result. If no difference between Hebrew and English is found, or Hebrew turns out to be more robust, that is a valid and interesting finding. Success is measured by the quality of the work:

- **Reproducibility:** one command regenerates the report from stored traces.
- **Completeness:** 150 schema-validated scenarios, including both sides of every pair.
- **Calibration:** human labeling done, with agreement and kappa reported separately for Hebrew and English.
- **Transparency:** a report with confidence intervals, an explicit limitations section (sample size, single provider, single-turn scenarios), the run date and model versions.
- **Engineering quality:** passing pytest tests on deterministic components, and a README quickstart that a stranger can run.
- **Learning:** the author can explain every component and decision aloud.

---

## 8. Publication plan

### 8.1 README structure

1. One-line description and a main figure of the key finding.
2. The problem and the research question.
3. Key findings, with numbers and confidence intervals.
4. Quickstart (three or four commands).
5. How it works (architecture diagram).
6. Methodology and limitations, stated openly.
7. Roadmap (v2: UI, multi-turn, additional provider).
8. License and how to cite.

The README and this spec are written in **English** for the GitHub and recruiter audience, with a short Hebrew summary at the end of the README.

### 8.2 Dataset release

- **Hugging Face Datasets:** scenarios and human labels, with a dataset card describing structure, license and intended use. Data license: CC BY 4.0. Code license: MIT.
- **Not published:** raw traces, keys, any personal information. All data is synthetic.

### 8.3 Responsible use

All attacks in this project run against the project's own mock agent, not against real products. If the tool is ever run on someone else's agent, it must be done with their permission, and findings should be shared with them before publication. This will be stated explicitly in the README.

### 8.4 Communication

- **LinkedIn:** a short "building in public" post now (research question and name). The main post comes only after real results exist: a surprising finding or question as the opening line, three or four data points, what was learned, a link to the repo, and a request for feedback.
- **CV line (template, to be filled with real numbers):**
  > **HebJudge**: open benchmark for evaluating agents in Hebrew: 150 scenarios, LLM judge calibrated against human labels (κ=…), comparison of prompt-injection vulnerability in Hebrew vs. English across N models.

### 8.5 Suggested timeline

| When | What |
|---|---|
| Now | Repository with `SPEC.md` and `DECISIONS.md`; optional short "building in public" post |
| After the thin slice | Commit of end-to-end working code and an initial README |
| After the full run | Report, Hugging Face release, final README, findings post |
| 2 to 3 weeks later | One attempt to find an outside user to run the tool on their own agent (for future marketing) |

---

## 9. Known limitations and risks

- **Single provider (OpenAI) in v1.** The judge and the tested models may share a model family, so self-preference bias remains possible. It is documented as a limitation, measured through human calibration, and the adapter layer allows adding a second provider later.
- **Small sample.** 60 pairs yield wide confidence intervals; conclusions must be stated cautiously.
- **Single-turn only.** Real attacks are often multi-turn.
- **Mock agent.** Findings describe one synthetic customer-service agent and may not generalize to other agents.
- **Models change.** Results are tied to specific model versions and dates.
- **Model names and pricing** must be verified against the provider's current documentation at build time.

---

## 10. Open items

- [ ] Verify name availability: GitHub, PyPI (`hebjudge`), Hugging Face.
- [ ] Add repository topics: `llm`, `evaluation`, `red-teaming`, `hebrew`.
- [X] Set a spending cap and create a dedicated API key.
- [X] Choose the judge model and the tested models (check the provider's current model list).
- [ ] Decide the number of manually labeled transcripts (50 minimum, 80 target).
- [ ] Create `docs/DECISIONS.md` and log decisions made so far (name, scope, single-turn, English docs).

---

## 11. תקציר בעברית

HebJudge הוא פרויקט קוד פתוח להערכת סוכני AI בעברית. השאלה המרכזית: האם סוכנים פגיעים יותר להזרקת הוראות בעברית מאשר באנגלית? השאלה המשנית: עד כמה שופט LLM אמין בהערכת תשובות בעברית. הפרויקט כולל כ-150 תרחישים (120 מקבילים בעברית ובאנגלית ו-30 בעברית בלבד), סוכן שירות לקוחות מדומה, בדיקות בקוד ושופט LLM מכויל מול תיוג אנושי, ודוח עם טווחי ביטחון ומגבלות מפורשות.
