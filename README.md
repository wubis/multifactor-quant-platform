# Multifactor Equity Ranking Platform

Production-style platform for ingesting equity data, computing stock factors, ranking stocks, backtesting portfolio rules, and serving results through an API/dashboard.

## MVP

- Universe: U.S. large-cap equities, starting with S&P 500-style tickers or top liquid names.
- Rebalance: monthly.
- Target: next-month relative return.
- First output: cross-sectional stock ranking from 1 to N.
- First strategy: buy top 50 equal-weight, hold one month, rebalance monthly.

## Architecture

```text
Data Sources
  -> ETL Pipeline
  -> Raw Database
  -> Feature Engineering Jobs
  -> Feature Store
  -> Ranking Models
  -> Backtester
  -> Portfolio Optimizer
  -> FastAPI Backend
  -> React Dashboard
```

## Build Plan

### Phase 1: Data Pipeline

- Ingest adjusted OHLCV prices.
- Ingest point-in-time fundamentals where possible.
- Build and version the investable universe.
- Store securities, prices, fundamentals, features, predictions, and backtest results.
- Add validation checks for duplicate rows, missing dates, invalid prices, stale fundamentals, and ticker changes.

### Phase 2: Feature Engineering

- Compute momentum, volatility, beta, value, quality, size, and liquidity factors.
- Winsorize and z-score cross-sectionally by date.
- Add sector-neutral normalization once sector coverage is reliable.

### Phase 3: Baseline Ranking

- Use a weighted score model:
  - value: 25%
  - quality: 25%
  - momentum: 25%
  - low volatility: 15%
  - liquidity: 10%
- Persist factor scores, composite score, rank, sector, and model version.

### Phase 4: Backtesting

- Monthly rebalance.
- Trade using signals known before the rebalance execution date.
- Track CAGR, Sharpe, volatility, drawdown, turnover, win rate, alpha vs SPY, sector exposure, and transaction costs.

### Phase 5: ML Models

- Add linear regression, Elastic Net, tree models, and ranking models after the baseline is working.
- Use walk-forward validation and compare information coefficient, rank IC, Sharpe, drawdown, and turnover.

### Phase 6: Optimization

- Add constrained allocation with max position, sector exposure, turnover, beta, and cash constraints.
- Start with scipy/cvxpy only after the naive top-N strategy is explainable.

### Phase 7: API

- Serve latest rankings, historical rankings, stock feature history, backtests, and latest portfolio.
- Keep training and backtest-running endpoints behind explicit jobs in production.

### Phase 8: Dashboard

- Show portfolio summary, rankings, stock detail, backtest analytics, model comparison, and risk views.

## Failure Modes And Controls

- Survivorship bias: store universe membership by effective date; do not rely on today's S&P 500 for old backtests.
- Lookahead leakage: separate signal dates from execution dates; fundamentals need publish/as-of dates, not fiscal period end alone.
- Corporate actions: use adjusted prices for returns; retain raw prices for auditability.
- Vendor drift: isolate vendor adapters behind ingestion interfaces and record source/version metadata.
- Missing fundamentals: impute only within training windows; expose missingness as model features when useful.
- Overfitting: require walk-forward validation and out-of-sample model comparison before claiming performance.
- Transaction-cost blindness: include slippage, commissions, and turnover from the first backtest.
- Liquidity traps: filter by minimum average dollar volume and cap position size relative to volume.
- Sector concentration: report sector exposure early; enforce constraints later.
- Operational fragility: add idempotent jobs, structured logs, and database uniqueness constraints.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn multifactor_platform.api.main:app --reload
```

API docs will be available at `http://127.0.0.1:8000/docs`.

## Current Scaffold

This scaffold includes:

- factor calculations for momentum, volatility, normalization, and liquidity
- weighted baseline ranker
- monthly top-N backtest engine
- FastAPI endpoints backed by deterministic sample data
- SQLAlchemy models for the planned database tables
- tests for factor timing, ranking, portfolio weights, and API health

## Limitations

The initial scaffold intentionally uses generated sample data and simplified fundamentals. Real investment research requires point-in-time datasets, delisting handling, robust corporate action treatment, and stronger cost/slippage models.
