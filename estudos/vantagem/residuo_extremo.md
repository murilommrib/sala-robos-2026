# Residual Edge Analysis

**Status:** RESIDUAL_FRAGILE
**Decision eligibility:** REVIEW_REQUIRED
**Period:** 2020-03-21 to 2026-11-07 (2423 observations)
**Primary model:** cesta

## Primary Model

| Metric | Value |
|---|---:|
| R² | 0.0006 |
| Adjusted R² | 0.0002 |
| Annualized alpha | 14.4837% |
| Alpha HAC t-stat | 1.306 |
| Annualized residual volatility | 32.5299% |
| Residual edge ratio | 0.445 |

## Baseline Loadings

| Baseline | Loading | HAC t-stat | VIF |
|---|---:|---:|---:|
| cesta_return | -0.0110 | -0.586 | 1.000 |

## Model Sensitivity

| Model | Role | R² | Annualized alpha | Residual edge ratio | Status |
|---|---|---:|---:|---:|---|
| cesta | primary | 0.0006 | 14.4837% | 0.445 | RESIDUAL_FRAGILE |
| btc | sensitivity | 0.0000 | 13.7551% | 0.423 | RESIDUAL_FRAGILE |
| cesta_mais_btc | sensitivity | 0.0012 | 14.5053% | 0.446 | RESIDUAL_FRAGILE |

## Evidence Warnings

- **HIGH — NOT_OUT_OF_SAMPLE:** Treat in-sample residual edge as exploratory until confirmed out of sample.

## Regime Breakdown

### volatility_regime

| Regime | N | Evidence | Annualized active return | Active Sharpe |
|---|---:|---|---:|---:|
| alta_vol | 986 | ADEQUATE | 24.5605% | 0.597 |
| baixa_vol | 1437 | ADEQUATE | 7.5695% | 0.303 |

## Interpretation

- Residual evidence does not clear all robustness thresholds.
- Rolling alpha is positive in too few windows.
- This report does not authorize a trade or an automatic exposure change.
- Confirm exploratory findings on untouched out-of-sample or live data.
