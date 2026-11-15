# Results: main-v1

**Status:** interim. Confirmatory results of the main research run, analysed as pre-registered in `docs/ANALYSIS_PLAN.md`. Judge calibration against human labels (D-08) is not yet done, so every judged figure below is provisional.

| | |
|---|---|
| Run date | 2026-11-15 |
| Batch | `main-v1` |
| Frozen setup | git tag `v0.2.0-frozen` |
| Scenarios | 60 Hebrew/English pairs (50 attack, 10 benign) |
| Tested models | `gpt-6-luna`, `gpt-4o-mini-2024-07-18`, `gpt-4.1-mini-2025-04-14` |
| Judge | `gpt-6-sol`, reasoning off, with the store policy (D-30) |
| Runs | 1,080 (120 scenarios x 3 models x 3 repeats), 0 failed, 0 unclear |
| Cost | $2.09 |

---

## 1. Primary question

**Are agents more or less vulnerable to prompt injection in Hebrew than in English?**

| | Value |
|---|---|
| Paired cells (attack pair x model) | 150 |
| Failed in Hebrew only | 9 |
| Failed in English only | 5 |
| Failed in both / neither | 30 / 106 |
| Incomplete | 0 |
| Exact McNemar, two-sided | **p = 0.42** |
| Attack success rate, English | 24% [20%–28%] (106/450) |
| Attack success rate, Hebrew | 26% [22%–30%] (118/450) |

**Conclusion, as pre-registered:** no evidence of a difference between Hebrew and English at this sample size. The measured difference is about 2.6 percentage points, with largely overlapping intervals. As anticipated in the plan, only 14 cells were discordant, so only a large asymmetry could have reached significance; a small effect in either direction cannot be ruled out.

**Sensitivity analysis:** unchanged (no unclear runs).

## 2. Secondary analyses

### 2.1 By model, paired

| Model | Hebrew only | English only | McNemar p | Holm p |
|---|---|---|---|---|
| gpt-4o-mini | 6 | 1 | 0.125 | 0.375 |
| gpt-4.1-mini | 1 | 4 | 0.375 | 0.750 |
| gpt-6-luna | 2 | 0 | 0.500 | 0.750 |

No model shows a significant language difference. The directions differ between models (gpt-4o-mini toward Hebrew, gpt-4.1-mini toward English), which suggests that any language effect, if present, is model-specific rather than a general property of Hebrew.

### 2.2 Attack success rate

| By model | Rate [95% CI] |
|---|---|
| gpt-6-luna | 13% [9%–17%] |
| gpt-4o-mini | 31% [26%–36%] |
| gpt-4.1-mini | 31% [26%–36%] |

| By category | Rate [95% CI] |
|---|---|
| Direct injection | 46% [40%–52%] |
| Unauthorized tool action | 23% [17%–29%] |
| Leakage | 16% [11%–22%] |
| Indirect injection | 11% [8%–15%] |

**Model choice matters far more than language:** the intervals for gpt-6-luna and the two older models do not overlap, a difference of about 2.5 times. (Not a pre-registered hypothesis test; reported descriptively with intervals.)

### 2.3 Over-refusal

0/90 in English and 0/90 in Hebrew (95% upper bound: 4%). No legitimate request was refused, including benign controls designed to resemble attacks.

### 2.4 Decisions and stability

- Decided in code: 97 of 1,080 runs; the rest by the judge.
- Stability: in 286 of 300 attack cells (95%), all three repeats gave the same verdict.

### 2.5 Tokens, latency and cost

| Language | Agent input tokens | Agent output tokens | Latency | Cost per run (incl. judge) |
|---|---|---|---|---|
| English | 581 | 73 | 2.0 s | $0.0019 |
| Hebrew | 765 | 81 | 2.1 s | $0.0020 |

The same content costs the agent about **32% more input tokens in Hebrew**. The total cost per run differs by only about 5% because the judge, whose instructions are in English for both languages, dominates the cost. For a deployed agent without a judge, the token difference translates almost directly into cost.

## 3. Exploratory hypotheses (not confirmatory)

| Hypothesis (from `docs/OBSERVATIONS.md`) | In main-v1 |
|---|---|
| gpt-4o-mini fails more in Hebrew | Same direction, 6 vs 1, not significant (Holm p = 0.375) |
| Justified indirect injections succeed, bare commands fail | Not tested here; requires a planned experiment |
| Partial compliance recurs | Not measured automatically |

## 4. Limitations

- **Judge not yet calibrated.** Most verdicts come from an LLM judge; agreement with human labels will be reported after calibration.
- **Single provider.** Tested models and judge are all from OpenAI.
- **Small number of discordant pairs.** Limits the power to detect a language difference.
- **One synthetic agent, single-turn scenarios.** Findings may not generalize.
- **Model versions and date.** Results describe the listed model versions on 2026-11-15.
- **The agent's instructions include explicit defenses** (for example, treating order notes as data), so attack success rates reflect a reasonably defended baseline.

## 5. Not yet included

- Judge calibration (D-08).
- The 30 Hebrew-only scenarios, to be run and reported separately.
- Results by technique, tone and hiding method (descriptive).