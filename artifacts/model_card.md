# FloatWise Model Card — fw-34e31047

Generated 2026-10-03T08:17:45 by `make evaluate`. All numbers come from code (R-ML-5).

## Model
- Global LightGBM quantile regression, one model per target (cash-out, cash-in) and quantile [0.1, 0.5, 0.9].
- Direct multi-horizon (h = 1..7 as a feature); target = served amount / agent's trailing 28-day mean.
- 39 features: target-day calendar (Eid distance, salary window, Ramadan, …), lags and rolling
  stats known at the origin, previous-Eid multipliers, archetype/district, recent stockouts.
- Censoring: `inflate` — on a stockout day the observed volume understates true demand. The mode was
  chosen on a held-out Eid (2025) by `scripts/censoring_experiment.py`; `inflate` lifts censored labels to the
  P75 ratio of uncensored peers (same archetype, same day).
- Trained on 2024-01-01 → 2025-06-30; early stopping on validation
  2025-07-01 → 2025-12-31. Test 2026-01-01 → 2026-06-30 untouched.

## Test results (vs synthetic ground-truth demand, all horizons)
| Slice | WAPE model | WAPE seasonal-naive | WAPE trailing-7 | Δ vs naive | P10–P90 coverage |
|---|---|---|---|---|---|
| Cash-out — overall | 0.186 | 0.396 | 0.327 | +53.1 % | 74% |
| Cash-out — event_days | 0.206 | 0.589 | 0.538 | +65.1 % | 55% |
| Cash-out — salary_window | 0.186 | 0.369 | 0.311 | +49.6 % | 74% |
| Cash-out — normal_days | 0.180 | 0.364 | 0.280 | +50.5 % | 78% |
| Cash-out — rural | 0.208 | 0.384 | 0.311 | +46.0 % | 76% |
| Cash-out — urban | 0.182 | 0.398 | 0.329 | +54.3 % | 74% |
| Cash-out — urban_residential | 0.181 | 0.321 | 0.257 | +43.5 % | 75% |
| Cash-out — garment_belt | 0.188 | 0.490 | 0.420 | +61.6 % | 69% |
| Cash-out — rural_remittance | 0.208 | 0.384 | 0.311 | +46.0 % | 76% |
| Cash-out — market_hub | 0.170 | 0.338 | 0.264 | +49.7 % | 75% |
| Cash-out — university_area | 0.212 | 0.410 | 0.357 | +48.1 % | 74% |
| Cash-in — overall | 0.180 | 0.353 | 0.283 | +49.1 % | 78% |
| Cash-in — event_days | 0.189 | 0.593 | 0.544 | +68.2 % | 71% |

## Acceptance (SRS §6.4)
- ✅ overall_improvement_vs_seasonal_naive_ge_20pct
- ✅ event_improvement_vs_seasonal_naive_ge_35pct
- ✅ coverage_p10_p90_between_72_and_88pct
- ✅ no_archetype_worse_than_baseline

## Intended use & limits
- Operational liquidity planning for agents; recommendations always need human approval.
- Trained on synthetic data only; must be re-validated on governed real data before any pilot.
- Not for credit, lending or penalty decisions about agents.
