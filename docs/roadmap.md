# Research rebuild

## First correctness milestone

Implemented:

- Preserve fundamental snapshot dates. Current yfinance fundamentals cannot support historical multifactor research; the backtest and model evaluation now reject that dataset explicitly (HTTP 422 through the API).
- Limit fundamental median imputation to the same availability date; leave unavailable values missing.
- Build forward returns within each ticker and carry label realization dates. Walk-forward training uses only labels realized strictly before validation starts.
- Shuffle placebo predictions within their original dates, regardless of row ordering.
- Include initial capital in drawdown; use annualized arithmetic returns for Sharpe and information ratios. Sharpe defaults to a zero cash rate, with a per-period cash-rate argument available in the metric function.
- Reject missing/invalid execution prices instead of assigning zero returns.
- Carry drifted holdings into the next rebalance. Charge per-dollar buy/sell costs against actual traded notional and fund costs before earning holding-period returns.
- Preserve old positions when constraining turnover. Reject a transition when retained holdings violate the other constraints or lack metadata. This is a conservative allocator, not a general feasibility solver.
- Label CAGR spread and sector-balanced portfolios accurately in the interface. The legacy `alpha` metric key remains a compatibility alias for CAGR spread, not risk-adjusted alpha. Existing sector-neutral URL identifiers remain supported.

Existing stored results predate these corrections. They were not rewritten and should not be compared with corrected runs.

## Next: daily accounting and reproducible research

1. Build a daily holdings/cash/trades ledger with corporate actions, end-of-test valuation, and explicit cash-rate accrual. Current metrics still use monthly holding-period observations and miss intramonth drawdown. Cost-adjusted period NAV is reconciled, but a daily execution ledger is not implemented.
2. Align forecast labels to the execution and holding schedule. Current labels still use the next 21 available ticker observations; handle calendar gaps explicitly before treating these as a tradable target.
3. Use common evaluation dates for strategy comparisons; retain an untouched final evaluation period and account for overlapping outcomes in uncertainty estimates.
4. Persist run manifests containing code/configuration versions, input hashes, model artifacts, predictions, holdings, and trades.
5. Refresh/version caches explicitly, and make Parquet support an installed dependency. Fix historical risk-exposure joins and distinguish standardized characteristics from actual portfolio beta.

## Data and investment mandate

- Select a benchmark-relative long-only mandate first, including capital, liquidity, turnover, and risk budgets.
- Obtain and verify point-in-time fundamentals, historical security eligibility, delisted returns, and corporate action records. Preserve publication timestamps and revisions separately from fiscal dates.
- Replace the curated universe with historically reconstructed eligibility. Compare against passive holdings of the same eligible universe.
- Document each signal's economic hypothesis, coverage, sector behavior, predictive horizon, costs, and incremental contribution.
- Remove placeholder quality inputs; standardize accounting units and valuation treatment.
- Add covariance-aware portfolio construction and actual beta/sector constraints. The current allocator does not enforce its informational beta target and reports that limitation.
- Freeze a research configuration before paper trading; reconcile predictions, orders, positions, and realized costs. Paper trading is an operational validation step, not proof of alpha.
