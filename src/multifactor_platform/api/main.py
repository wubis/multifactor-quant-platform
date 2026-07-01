from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

from multifactor_platform.backtesting.engine import run_top_n_backtest
from multifactor_platform.config import get_settings
from multifactor_platform.utils.platform_data import DataSource, load_platform_data

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_data_or_503(source: DataSource):
    try:
        return load_platform_data(source)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _json_records(frame: pd.DataFrame, columns: list[str] | None = None) -> list[dict]:
    output = frame.copy()
    if columns is not None:
        output = output[columns]
    output = output.replace({pd.NA: None})
    output = output.where(pd.notna(output), None)
    records = output.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, pd.Timestamp):
                record[key] = value.date().isoformat()
    return records


@app.get("/")
def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
        "endpoints": [
            "/rankings/latest?source=yfinance",
            "/portfolio/latest?source=yfinance",
            "/backtests?source=yfinance",
            "/stocks/{ticker}/features?source=yfinance",
        ],
        "data_sources": ["yfinance", "sample"],
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/rankings/latest")
def latest_rankings(limit: int = 50, source: DataSource = "sample"):
    _, _, rankings = _load_data_or_503(source)
    latest_date = rankings["date"].max()
    rows = rankings.loc[rankings["date"] == latest_date].head(limit)
    return {
        "source": source,
        "date": latest_date.date().isoformat(),
        "rankings": _json_records(
            rows,
            [
                "ticker",
                "sector",
                "rank",
                "composite_score",
                "value_score",
                "quality_score",
                "momentum_score",
                "low_vol_score",
                "liquidity_score",
            ],
        ),
    }


@app.get("/rankings/{ranking_date}")
def rankings_by_date(ranking_date: date, limit: int = 50, source: DataSource = "sample"):
    _, _, rankings = _load_data_or_503(source)
    requested = rankings.loc[rankings["date"] == str(ranking_date)].head(limit)
    if requested.empty:
        raise HTTPException(status_code=404, detail="No rankings found for date")
    return {
        "source": source,
        "date": ranking_date.isoformat(),
        "rankings": _json_records(requested),
    }


@app.get("/stocks/{ticker}/features")
def stock_features(ticker: str, source: DataSource = "sample"):
    _, features, _ = _load_data_or_503(source)
    rows = features.loc[features["ticker"] == ticker.upper()].sort_values("date")
    if rows.empty:
        raise HTTPException(status_code=404, detail="Ticker not found")
    columns = [
        "date",
        "ticker",
        "momentum_1m",
        "momentum_3m",
        "volatility_20d",
        "pe_ratio",
        "roe",
        "market_cap",
        "dollar_volume",
    ]
    return {
        "source": source,
        "ticker": ticker.upper(),
        "features": _json_records(rows.tail(120), columns),
    }


@app.get("/backtests")
def list_backtests(source: DataSource = "sample"):
    prices, _, rankings = _load_data_or_503(source)
    result = run_top_n_backtest(rankings, prices, n=10)
    return [
        {
            "id": f"{source}-top-10",
            "name": f"{source.title()} Top 10 Monthly",
            "source": source,
            "metrics": result["metrics"],
        }
    ]


@app.get("/backtests/{backtest_id}")
def get_backtest(backtest_id: str, source: DataSource = "sample"):
    valid_ids = {"sample-top-10", "yfinance-top-10"}
    if backtest_id not in valid_ids:
        raise HTTPException(status_code=404, detail="Backtest not found")
    prices, _, rankings = _load_data_or_503(source)
    result = run_top_n_backtest(rankings, prices, n=10)
    return {
        "id": f"{source}-top-10",
        "source": source,
        "metrics": result["metrics"],
        "returns": [
            {"date": index.date().isoformat(), "return": value}
            for index, value in result["returns"].items()
        ],
    }


@app.get("/portfolio/latest")
def latest_portfolio(limit: int = 10, source: DataSource = "sample"):
    _, _, rankings = _load_data_or_503(source)
    latest_date = rankings["date"].max()
    rows = rankings.loc[rankings["date"] == latest_date].head(limit).copy()
    rows["weight"] = 1 / len(rows)
    sector_exposure = (
        rows.groupby("sector")["weight"].sum().sort_values(ascending=False).reset_index()
    )
    return {
        "source": source,
        "date": latest_date.date().isoformat(),
        "positions": _json_records(rows, ["ticker", "sector", "rank", "weight", "composite_score"]),
        "sector_exposure": _json_records(sector_exposure),
    }


@app.get("/models")
def models(source: DataSource = "sample"):
    return {
        "source": source,
        "models": [
            {"name": "Weighted Score", "rank_ic": None, "sharpe": None, "status": "Active"},
            {"name": "Elastic Net", "rank_ic": None, "sharpe": None, "status": "Planned"},
            {"name": "XGBoost", "rank_ic": None, "sharpe": None, "status": "Planned"},
        ],
    }
