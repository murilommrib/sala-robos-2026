# Residual Edge Analysis

**Status:** RESIDUAL_FRAGILE
**Decision eligibility:** REVIEW_REQUIRED
**Period:** 2020-03-21 to 2026-11-07 (2423 observations)
**Primary model:** cesta

## Primary Model

| Metric | Value |
|---|---:|
| R² | 0.8866 |
| Adjusted R² | 0.8866 |
| Annualized alpha | -10.7719% |
| Alpha HAC t-stat | -1.196 |
| Annualized residual volatility | 26.4990% |
| Residual edge ratio | -0.407 |

## Baseline Loadings

| Baseline | Loading | HAC t-stat | VIF |
|---|---:|---:|---:|
| cesta_return | 1.0228 | 53.685 | 1.000 |

## Model Sensitivity

| Model | Role | R² | Annualized alpha | Residual edge ratio | Status |
|---|---|---:|---:|---:|---|
| cesta | primary | 0.8866 | -10.7719% | -0.407 | BASELINE_EXPLAINED |
| btc | sensitivity | 0.5919 | 18.6567% | 0.371 | RESIDUAL_FRAGILE |
| cesta_mais_btc | sensitivity | 0.8867 | -10.7879% | -0.407 | BASELINE_EXPLAINED |

## Evidence Warnings

- **HIGH — NOT_OUT_OF_SAMPLE:** Treat in-sample residual edge as exploratory until confirmed out of sample.

## Regime Breakdown

### volatility_regime

| Regime | N | Evidence | Annualized active return | Active Sharpe |
|---|---:|---|---:|---:|
| alta_vol | 986 | ADEQUATE | -12.0129% | -0.331 |
| baixa_vol | 1437 | ADEQUATE | -9.9204% | -0.594 |

## Interpretation

- Declared baselines explain most variation and residual edge is weak.
- Diagnostic status changes under alternate declared baselines.
- This report does not authorize a trade or an automatic exposure change.
- Confirm exploratory findings on untouched out-of-sample or live data.
