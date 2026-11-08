# Residual Edge Analysis

**Status:** RESIDUAL_FRAGILE
**Decision eligibility:** REVIEW_REQUIRED
**Period:** 2020-03-21 to 2026-11-07 (2423 observations)
**Primary model:** cesta

## Primary Model

| Metric | Value |
|---|---:|
| R² | 0.8406 |
| Adjusted R² | 0.8405 |
| Annualized alpha | -6.6233% |
| Alpha HAC t-stat | -1.077 |
| Annualized residual volatility | 14.4237% |
| Residual edge ratio | -0.459 |

## Baseline Loadings

| Baseline | Loading | HAC t-stat | VIF |
|---|---:|---:|---:|
| cesta_return | 0.4572 | 19.692 | 1.000 |

## Model Sensitivity

| Model | Role | R² | Annualized alpha | Residual edge ratio | Status |
|---|---|---:|---:|---:|---|
| cesta | primary | 0.8406 | -6.6233% | -0.459 | BASELINE_EXPLAINED |
| btc | sensitivity | 0.6221 | 5.1817% | 0.233 | RESIDUAL_FRAGILE |
| cesta_mais_btc | sensitivity | 0.8445 | -6.5604% | -0.460 | BASELINE_EXPLAINED |

## Evidence Warnings

- **HIGH — NOT_OUT_OF_SAMPLE:** Treat in-sample residual edge as exploratory until confirmed out of sample.

## Regime Breakdown

### volatility_regime

| Regime | N | Evidence | Annualized active return | Active Sharpe |
|---|---:|---|---:|---:|
| alta_vol | 986 | ADEQUATE | -21.2645% | -1.400 |
| baixa_vol | 1437 | ADEQUATE | 3.4227% | 0.247 |

## Interpretation

- Declared baselines explain most variation and residual edge is weak.
- Diagnostic status changes under alternate declared baselines.
- This report does not authorize a trade or an automatic exposure change.
- Confirm exploratory findings on untouched out-of-sample or live data.
