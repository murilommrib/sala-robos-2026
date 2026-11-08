# Residual Edge Analysis

**Status:** RESIDUAL_FRAGILE
**Decision eligibility:** REVIEW_REQUIRED
**Period:** 2020-03-21 to 2026-11-07 (2423 observations)
**Primary model:** cesta

## Primary Model

| Metric | Value |
|---|---:|
| R² | 0.6199 |
| Adjusted R² | 0.6197 |
| Annualized alpha | 17.7769% |
| Alpha HAC t-stat | 1.545 |
| Annualized residual volatility | 31.0965% |
| Residual edge ratio | 0.572 |

## Baseline Loadings

| Baseline | Loading | HAC t-stat | VIF |
|---|---:|---:|---:|
| cesta_return | 0.5481 | 13.249 | 1.000 |

## Model Sensitivity

| Model | Role | R² | Annualized alpha | Residual edge ratio | Status |
|---|---|---:|---:|---:|---|
| cesta | primary | 0.6199 | 17.7769% | 0.572 | RESIDUAL_FRAGILE |
| btc | sensitivity | 0.3498 | 36.0172% | 0.886 | RESIDUAL_FRAGILE |
| cesta_mais_btc | sensitivity | 0.6293 | 17.6402% | 0.574 | RESIDUAL_FRAGILE |

## Evidence Warnings

- **HIGH — NOT_OUT_OF_SAMPLE:** Treat in-sample residual edge as exploratory until confirmed out of sample.

## Regime Breakdown

### volatility_regime

| Regime | N | Evidence | Annualized active return | Active Sharpe |
|---|---:|---|---:|---:|
| alta_vol | 986 | ADEQUATE | 23.1300% | 0.588 |
| baixa_vol | 1437 | ADEQUATE | 14.1038% | 0.590 |

## Interpretation

- Residual evidence does not clear all robustness thresholds.
- Rolling alpha is positive in too few windows.
- This report does not authorize a trade or an automatic exposure change.
- Confirm exploratory findings on untouched out-of-sample or live data.
