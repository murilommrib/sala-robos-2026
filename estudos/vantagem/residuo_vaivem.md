# Residual Edge Analysis

**Status:** RESIDUAL_FRAGILE
**Decision eligibility:** REVIEW_REQUIRED
**Period:** 2020-03-21 to 2026-11-07 (2423 observations)
**Primary model:** cesta

## Primary Model

| Metric | Value |
|---|---:|
| R² | 0.0012 |
| Adjusted R² | 0.0008 |
| Annualized alpha | 45.5510% |
| Alpha HAC t-stat | 2.080 |
| Annualized residual volatility | 59.4150% |
| Residual edge ratio | 0.767 |

## Baseline Loadings

| Baseline | Loading | HAC t-stat | VIF |
|---|---:|---:|---:|
| cesta_return | 0.0282 | 0.330 | 1.000 |

## Model Sensitivity

| Model | Role | R² | Annualized alpha | Residual edge ratio | Status |
|---|---|---:|---:|---:|---|
| cesta | primary | 0.0012 | 45.5510% | 0.767 | RESIDUAL_FRAGILE |
| btc | sensitivity | 0.0027 | 50.8591% | 0.857 | RESIDUAL_FRAGILE |
| cesta_mais_btc | sensitivity | 0.0210 | 45.3173% | 0.770 | RESIDUAL_FRAGILE |

## Evidence Warnings

- **HIGH — NOT_OUT_OF_SAMPLE:** Treat in-sample residual edge as exploratory until confirmed out of sample.

## Regime Breakdown

### volatility_regime

| Regime | N | Evidence | Annualized active return | Active Sharpe |
|---|---:|---|---:|---:|
| alta_vol | 986 | ADEQUATE | 33.8518% | 0.465 |
| baixa_vol | 1437 | ADEQUATE | 53.5785% | 1.114 |

## Interpretation

- Residual evidence does not clear all robustness thresholds.
- Rolling alpha is positive in too few windows.
- This report does not authorize a trade or an automatic exposure change.
- Confirm exploratory findings on untouched out-of-sample or live data.
