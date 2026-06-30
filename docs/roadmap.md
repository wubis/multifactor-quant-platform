# Roadmap

## Immediate Next Milestones

1. Replace generated sample data with a real price ingestion adapter.
2. Add migrations and create the PostgreSQL schema from SQLAlchemy models.
3. Persist feature snapshots and model rankings by date.
4. Expand tests around no-lookahead fundamentals joins and rebalance execution delays.
5. Add the first real dashboard API integration.

## Data Vendor Notes

- `yfinance` is acceptable for local demos and scaffolding, but not for institutional-grade research.
- Polygon, Financial Modeling Prep, Nasdaq Data Link, Intrinio, or Sharadar-style datasets are better candidates.
- A point-in-time fundamentals dataset is the single biggest quality upgrade for the backtester.

## Resume Story

The polished story should emphasize an end-to-end platform, not a single model:

- ETL and data quality checks
- point-in-time feature engineering
- baseline and ML ranking models
- walk-forward evaluation
- transaction-cost-aware backtesting
- FastAPI service layer
- interactive dashboard
- Dockerized local deployment
