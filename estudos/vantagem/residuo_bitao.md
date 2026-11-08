# Residual Edge Analysis

**Status:** RESIDUAL_FRAGILE
**Decision eligibility:** REVIEW_REQUIRED
**Period:** 2020-03-21 to 2026-11-07 (2423 observations)
**Primary model:** cesta

## Primary Model

| Metric | Value |
|---|---:|
| R² | 0.0021 |
| Adjusted R² | 0.0016 |
| Annualized alpha | 54.2715% |
| Alpha HAC t-stat | 2.413 |
| Annualized residual volatility | 57.2435% |
| Residual edge ratio | 0.948 |

## Baseline Loadings

| Baseline | Loading | HAC t-stat | VIF |
|---|---:|---:|---:|
| cesta_return | -0.0358 | -0.629 | 1.000 |

## Model Sensitivity

| Model | Role | R² | Annualized alpha | Residual edge ratio | Status |
|---|---|---:|---:|---:|---|
| cesta | primary | 0.0021 | 54.2715% | 0.948 | RESIDUAL_EDGE |
| btc | sensitivity | 0.0005 | 50.0142% | 0.873 | RESIDUAL_FRAGILE |
| cesta_mais_btc | sensitivity | 0.0131 | 54.4395% | 0.956 | RESIDUAL_FRAGILE |

## Evidence Warnings

- **HIGH — NOT_OUT_OF_SAMPLE:** Treat in-sample residual edge as exploratory until confirmed out of sample.

## Regime Breakdown

### volatility_regime

| Regime | N | Evidence | Annualized active return | Active Sharpe |
|---|---:|---|---:|---:|
| alta_vol | 986 | ADEQUATE | 44.0084% | 0.688 |
| baixa_vol | 1437 | ADEQUATE | 61.3135% | 1.176 |

## Interpretation

- Alpha, residual edge ratio, and rolling stability clear the configured thresholds.
- Diagnostic status changes under alternate declared baselines.
- This report does not authorize a trade or an automatic exposure change.
- Confirm exploratory findings on untouched out-of-sample or live data.
