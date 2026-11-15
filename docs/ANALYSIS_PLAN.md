# Analysis plan (pre-registered)

Written on 2026-11-15, **before** the main research run (`main-v1`). It fixes what will be measured, how, and what will count as a finding, so that the analysis cannot be chosen after seeing the results. Any deviation is logged in `docs/DECISIONS.md` with its reason.

Related: SPEC section 7 (metrics), D-12 (success is defined by work quality), D-25 (three repeats), D-32 (batches).

---

## 1. What is frozen before the run

| Item | Frozen as |
|---|---|
| Scenarios | The 60 parallel pairs in `data/scenarios/he` and `data/scenarios/en` at git tag `v0.2.0-frozen` |
| Target agent | System prompts and tools at the same tag; the system-prompt fingerprint is stored with every run |
| Tested models | `gpt-6-luna`, `gpt-4o-mini`, `gpt-4.1-mini`, settings as in `MODEL_SETTINGS` (D-14, D-15) |
| Judge | `gpt-6-sol`, reasoning off, with the store policy (D-30), prompt at the same tag |
| Repeats | 3 per scenario and model (D-25) |
| Batch | `main-v1`: 120 scenarios x 3 models x 3 repeats = 1,080 runs |

The 30 Hebrew-only scenarios are not part of this run. They are analysed separately and descriptively (SPEC 4.2).

## 2. Units and outcomes

- **Run:** one scenario, one model, one repeat. Outcome: attack succeeded, attack failed, or unclear (for benign controls: over-refusal, helped, or unclear).
- **Cell:** one scenario on one model. Outcome: the majority over its decided repeats. A cell with no decided repeats, or a tie, is **incomplete**.
- **Paired cell:** one attack pair on one model, with a Hebrew cell and an English cell. 50 attack pairs x 3 models = **150 paired cells**.

## 3. Primary question and analysis

**Question:** Are agents more or less vulnerable to prompt injection in Hebrew than in English? (SPEC 1.2)

- **Hypotheses (two-sided):** H0: the attack succeeds equally often in Hebrew-only and English-only paired cells. H1: it does not.
- **Test:** exact two-sided McNemar test on the discordant paired cells, pooled across the three models: *b* = Hebrew-only failures, *c* = English-only failures.
- **Significance level:** α = 0.05.
- **Reported alongside the p-value:** *b*, *c*, both, neither, incomplete; the attack success rate per language with a 95% Wilson interval; the difference between languages.

**Interpretation, decided in advance:**
- p < 0.05: a difference between languages is reported, in the direction of the larger of *b* and *c*.
- p ≥ 0.05: "no evidence of a difference at this sample size". This is not evidence that there is no difference; the intervals show what sizes remain plausible.

**Known limitation:** the paired cells of one pair on three models are not independent, so pooling slightly overstates the effective sample size. Per-model results (section 4) are reported to show whether one model drives the pooled result.

**Power, stated honestly:** development batches produced about 15 discordant cells out of 150. With so few, only a large asymmetry (roughly 3 to 1 or stronger) would reach significance. A null result is therefore likely unless the effect is large.

## 4. Secondary analyses

1. **Per model:** the same McNemar test for each model separately, with Holm correction across the three tests.
2. **Attack success rate** by language, by model and by category, each with a 95% Wilson interval, over decided runs.
3. **Over-refusal rate** on benign controls, by language, with a 95% Wilson interval.
4. **Share of decisions made in code vs. by the judge**, and the unclear rate.
5. **Stability across repeats:** share of cells whose three repeats all agree.
6. **Cost and latency** per run, by language and model; input tokens by language for the same content.
7. **Judge agreement with human labels** (percent and Cohen's kappa, per language), after calibration (D-08). Planned separately; not part of this run.

## 5. Descriptive only (no inferential claims)

Results by **technique**, **technique family**, **tone** and **hiding method** (D-20, D-23, D-29). Each has too few scenarios for inference. The hiding-method results are reported together with the perception probe (tag characters are not read by any tested model).

## 6. Missing and unclear data

- **Main analysis:** incomplete cells are excluded from the McNemar test and reported as a count.
- **Sensitivity analysis:** the primary test is repeated twice, once counting every unclear run as attack succeeded and once as attack failed. If the conclusion changes, this is reported prominently.
- **Failed runs** (API errors) are re-run with `--resume` until the batch is complete. If any remain, they are reported.

## 7. Exploratory hypotheses from development

These came from development batches (`docs/OBSERVATIONS.md`) and are **not** confirmatory. The main run may inform them, but any result on them is labelled exploratory.

1. gpt-4o-mini fails more often in Hebrew than in English (observed from 2026-11-10).
2. Indirect injections succeed when the injected note gives a plausible business justification, and fail as bare commands (observed 2026-11-14).
3. Partial compliance ("I can't confirm this, but here is a draft") is a recurring failure pattern (observed 2026-11-14).

## 8. What would change this plan

Only problems found **before** looking at `main-v1` results (for example, a broken scenario discovered while starting the run) may change the frozen items. Any such change is logged in `docs/DECISIONS.md`, and the frozen tag is moved with the reason recorded.