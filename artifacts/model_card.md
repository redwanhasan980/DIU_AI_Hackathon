# FloatWise Model Card — fw-c078f4bb

Generated 2026-10-03T13:55:45 by `make evaluate`. All numbers come from code (R-ML-5).

## Model
- Global LightGBM quantile regression, one model per target (cash-out, cash-in) and quantile [0.1, 0.5, 0.9].
- Direct multi-horizon (h = 1..7 as a feature); target = served amount / agent's trailing 28-day mean.
- 40 features: target-day calendar (Eid distance, salary window, Ramadan, …), lags and rolling
  stats known at the origin, previous-Eid multipliers, archetype/district, recent stockouts.
- Censoring: `keep` — on a stockout day the observed volume understates true demand. The mode was
  chosen on a held-out Eid (2025) by `scripts/censoring_experiment.py`; `inflate` lifts censored labels to the
  P75 ratio of uncensored peers (same archetype, same day).
- Trained on 2024-01-01 → 2025-06-30; early stopping on validation
  2025-07-01 → 2025-12-31. Test 2026-01-01 → 2026-06-30 untouched.

## Test results (vs synthetic ground-truth demand, all horizons)
| Slice | WAPE model | WAPE seasonal-naive | WAPE trailing-7 | Δ vs naive | P10–P90 coverage |
|---|---|---|---|---|---|
| Cash-out — overall | 0.187 | 0.398 | 0.327 | +53.0 % | 75% |
| Cash-out — event_days | 0.212 | 0.589 | 0.538 | +64.0 % | 60% |
| Cash-out — salary_window | 0.186 | 0.369 | 0.310 | +49.6 % | 74% |
| Cash-out — normal_days | 0.181 | 0.368 | 0.283 | +50.7 % | 78% |
| Cash-out — rural | 0.208 | 0.397 | 0.319 | +47.5 % | 75% |
| Cash-out — urban | 0.183 | 0.398 | 0.329 | +54.0 % | 74% |
| Cash-out — urban_residential | 0.185 | 0.321 | 0.257 | +42.4 % | 77% |
| Cash-out — garment_belt | 0.188 | 0.490 | 0.419 | +61.6 % | 69% |
| Cash-out — rural_remittance | 0.208 | 0.397 | 0.319 | +47.5 % | 75% |
| Cash-out — market_hub | 0.172 | 0.339 | 0.264 | +49.1 % | 76% |
| Cash-out — university_area | 0.214 | 0.410 | 0.357 | +47.7 % | 75% |
| Cash-in — overall | 0.180 | 0.353 | 0.283 | +49.0 % | 78% |
| Cash-in — event_days | 0.191 | 0.593 | 0.544 | +67.9 % | 70% |

## Acceptance (SRS §6.4)
- ✅ overall_improvement_vs_seasonal_naive_ge_20pct
- ✅ event_improvement_vs_seasonal_naive_ge_35pct
- ✅ coverage_p10_p90_between_72_and_88pct
- ✅ no_archetype_worse_than_baseline

## Model selection (never on the test period)
- Censoring mode on 2025-03-01 → 2025-06-30 (Eid-ul-Fitr and Eid-ul-Adha 2025): keep: 57% above P90, exclude: 57% above P90, inflate: 60% above P90 → selected **keep**.
- Quantile architecture on 2025-03-01 → 2025-06-30 (Eid-ul-Fitr and Eid-ul-Adha 2025), trained on data before it: event pinball independent 45,624 vs spread 42,041; event P10–P90 coverage 46% vs 41%. Rule: adopt spread only if cash-out event pinball improves AND event P10-P90 coverage does not drop → selected **independent**.
- Policy (service level 0.99, risk threshold 0.1) chosen on 2025-07-01 → 2025-12-31 (validation) by: max stockout reduction s.t. trips <= +15.0% and cash held <= +5.0%.
- Raw quantile models can cross around Eid peaks; predictions are re-ordered (rearrangement) so P10 ≤ P50 ≤ P90. SHAP drivers explain the raw median model.

## Intended use & limits
- Operational liquidity planning for agents; recommendations always need human approval.
- Trained on synthetic data only; must be re-validated on governed real data before any pilot.
- Not for credit, lending or penalty decisions about agents.
