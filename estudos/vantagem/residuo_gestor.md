# Residual Edge Analysis

**Status:** RESIDUAL_FRAGILE
**Decision eligibility:** REVIEW_REQUIRED
**Period:** 2020-03-21 to 2026-11-07 (2423 observations)
**Primary model:** cesta

## Primary Model

| Metric | Value |
|---|---:|
| R² | 0.6809 |
| Adjusted R² | 0.6807 |
| Annualized alpha | 10.7887% |
| Alpha HAC t-stat | 1.607 |
| Annualized residual volatility | 18.6906% |
| Residual edge ratio | 0.577 |

## Baseline Loadings

| Baseline | Loading | HAC t-stat | VIF |
|---|---:|---:|---:|
| cesta_return | 0.3768 | 17.588 | 1.000 |

## Model Sensitivity

| Model | Role | R² | Annualized alpha | Residual edge ratio | Status |
|---|---|---:|---:|---:|---|
| cesta | primary | 0.6809 | 10.7887% | 0.577 | RESIDUAL_FRAGILE |
| btc | sensitivity | 0.4254 | 22.3183% | 0.890 | RESIDUAL_FRAGILE |
| cesta_mais_btc | sensitivity | 0.6829 | 10.7471% | 0.577 | RESIDUAL_FRAGILE |

## Evidence Warnings

- **HIGH — NOT_OUT_OF_SAMPLE:** Treat in-sample residual edge as exploratory until confirmed out of sample.

## Regime Breakdown

### volatility_regime

| Regime | N | Evidence | Annualized active return | Active Sharpe |
|---|---:|---|---:|---:|
| alta_vol | 986 | ADEQUATE | 9.4702% | 0.408 |
| baixa_vol | 1437 | ADEQUATE | 11.6933% | 0.790 |

## Interpretation

- Residual evidence does not clear all robustness thresholds.
- Rolling alpha is positive in too few windows.
- This report does not authorize a trade or an automatic exposure change.
- Confirm exploratory findings on untouched out-of-sample or live data.
