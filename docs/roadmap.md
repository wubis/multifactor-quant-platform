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

## Daily accounting and reproducibility milestone

Implemented:

- Daily close-to-close NAV, holdings, signed trades, buy/sell costs, and cash interest. Every date reconciles opening NAV plus market P&L and interest less costs to closing NAV. Turnover consistently means half gross traded notional / pre-trade NAV, including the initial entry.
- Daily volatility, Sharpe, tracking error, information ratio, and drawdown; CAGR uses actual calendar time. Entry costs are included as the first daily observation with a zero benchmark return at entry. Cash accrual uses actual calendar days and a configured constant annual rate (default zero).
- Mark remaining positions through the requested final date. No new terminal-date position or forced liquidation is assumed.
- Monthly holding-period summaries remain available for turnover/return diagnostics; the equity chart uses daily NAV. A final holding period may be partial.
- Comparisons are rerun from cash on identical executable boundaries. Missing internal prediction periods reject the comparison. Incomplete/stale month-end predictions do not manufacture rebalance signals. The comparison ends at the last common rebalance boundary, while a standalone run can value its final holdings through the end of its price data.
- Date-aware factor-exposure joins use signal dates; beta is actual rolling beta, rather than its cross-sectional z-score. Missing exposure values are omitted rather than reported as zero.
- Content-addressed CSV input snapshots with schemas, availability restrictions, and round-trip float precision. CSV avoids an optional Parquet dependency for research archives.
- Both API strategy comparisons and CLI backtests write immutable run bundles under `data/processed/research`. Bundles contain input identifiers, exact parameters, source copies, numerical dependency versions, daily ledgers, trades, holdings, supplied predictions/rankings, and summaries.
- Replay verifies artifact checksums, matching source/dependencies, and exact equality of every regenerated output file and summary. It replays frozen predictions; it does not refit historical ML estimators.

Accounting scope: holdings use **adjusted total-return units**, not raw executable shares. Corporate actions are embedded in adjusted prices; there is no independent event ledger for dividends, splits, mergers, or delistings. Cash rates are configurable constants, not a historical rate feed. Daily observations use the supplied price calendar; complete vendor-wide missing sessions still require an independent exchange-calendar audit.

## Next research work

1. Obtain point-in-time fundamentals and historically eligible securities with corporate-action/delisting records. Keep historical yfinance multifactor research disabled until appropriate inputs exist.
2. Align forecast labels to actual execution and holding dates; current labels still use the next 21 available ticker observations. Address calendar gaps explicitly.
3. Reserve an untouched final evaluation period; account for overlapping outcomes in uncertainty estimates. Shared backtest windows do not fix research selection bias.
4. Archive fitted model artifacts and full training manifests to support retraining reproducibility, beyond frozen-prediction replay.
5. Add raw-share corporate-action accounting and a historical cash-rate feed; audit vendor calendars and execution assumptions.
6. Add explicit cache refresh/freshness rules. The new immutable research snapshots preserve exactly what was used but do not make the upstream yfinance cache fresh.

## Data and investment mandate

- Select a benchmark-relative long-only mandate first, including capital, liquidity, turnover, and risk budgets.
- Obtain and verify point-in-time fundamentals, historical security eligibility, delisted returns, and corporate action records. Preserve publication timestamps and revisions separately from fiscal dates.
- Replace the curated universe with historically reconstructed eligibility. Compare against passive holdings of the same eligible universe.
- Document each signal's economic hypothesis, coverage, sector behavior, predictive horizon, costs, and incremental contribution.
- Remove placeholder quality inputs; standardize accounting units and valuation treatment.
- Add covariance-aware portfolio construction and actual beta/sector constraints. The current allocator does not enforce its informational beta target and reports that limitation.
- Freeze a research configuration before paper trading; reconcile predictions, orders, positions, and realized costs. Paper trading is an operational validation step, not proof of alpha.
