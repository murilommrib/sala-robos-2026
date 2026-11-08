# Residual Edge Analysis

**Status:** RESIDUAL_FRAGILE
**Decision eligibility:** REVIEW_REQUIRED
**Period:** 2020-03-21 to 2026-11-07 (2423 observations)
**Primary model:** cesta

## Primary Model

| Metric | Value |
|---|---:|
| R² | 0.6094 |
| Adjusted R² | 0.6092 |
| Annualized alpha | 17.5175% |
| Alpha HAC t-stat | 1.598 |
| Annualized residual volatility | 29.7524% |
| Residual edge ratio | 0.589 |

## Baseline Loadings

| Baseline | Loading | HAC t-stat | VIF |
|---|---:|---:|---:|
| cesta_return | 0.5130 | 11.983 | 1.000 |

## Model Sensitivity

| Model | Role | R² | Annualized alpha | Residual edge ratio | Status |
|---|---|---:|---:|---:|---|
| cesta | primary | 0.6094 | 17.5175% | 0.589 | RESIDUAL_FRAGILE |
| btc | sensitivity | 0.3509 | 34.3193% | 0.895 | RESIDUAL_FRAGILE |
| cesta_mais_btc | sensitivity | 0.6167 | 17.4035% | 0.591 | RESIDUAL_FRAGILE |

## Evidence Warnings

- **HIGH — NOT_OUT_OF_SAMPLE:** Treat in-sample residual edge as exploratory until confirmed out of sample.

## Regime Breakdown

### volatility_regime

| Regime | N | Evidence | Annualized active return | Active Sharpe |
|---|---:|---|---:|---:|
| alta_vol | 986 | ADEQUATE | 11.4549% | 0.314 |
| baixa_vol | 1437 | ADEQUATE | 21.6773% | 0.900 |

## Interpretation

- Residual evidence does not clear all robustness thresholds.
- Rolling alpha is positive in too few windows.
- This report does not authorize a trade or an automatic exposure change.
- Confirm exploratory findings on untouched out-of-sample or live data.
