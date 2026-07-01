from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from multifactor_platform.backtesting.engine import run_top_n_backtest
from multifactor_platform.config import get_settings
from multifactor_platform.db.models import (
    BacktestResult,
    Base,
    Feature,
    Fundamental,
    ModelPrediction,
    Price,
    Security,
    utc_now,
)
from multifactor_platform.db.session import build_engine, build_session_factory
from multifactor_platform.ingestion.universe import load_default_universe
from multifactor_platform.utils.platform_data import DataSource, load_platform_data


FEATURE_COLUMNS = [
    "momentum_1m",
    "momentum_3m",
    "momentum_6m",
    "momentum_12m_ex_1m",
    "volatility_20d",
    "volatility_60d",
    "beta_252d",
    "pe_ratio",
    "pb_ratio",
    "ev_to_ebitda",
    "fcf_yield",
    "roe",
    "gross_margin",
    "debt_to_equity",
    "earnings_stability",
    "market_cap",
    "dollar_volume",
]


def _coerce_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _coerce_date(value: Any):
    return pd.Timestamp(value).date()


def initialize_database(database_url: str | None = None) -> None:
    url = database_url or get_settings().database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = build_engine(url)
    Base.metadata.create_all(engine)


def _security_id_map(session: Session) -> dict[str, int]:
    rows = session.execute(select(Security.ticker, Security.id)).all()
    return {ticker: security_id for ticker, security_id in rows}


def persist_securities(session: Session) -> dict[str, int]:
    existing = _security_id_map(session)
    for security in load_default_universe():
        if security.ticker in existing:
            row = session.get(Security, existing[security.ticker])
            if row is not None:
                row.name = security.name
                row.sector = security.sector
            continue

        session.add(
            Security(
                ticker=security.ticker,
                name=security.name,
                sector=security.sector,
                exchange=None,
                active_from=None,
                active_to=None,
            )
        )
    session.flush()
    return _security_id_map(session)


def persist_prices(session: Session, prices: pd.DataFrame, source: DataSource, ids: dict[str, int]) -> int:
    source_security_ids = [ids[ticker] for ticker in prices["ticker"].drop_duplicates() if ticker in ids]
    if source_security_ids:
        session.execute(delete(Price).where(Price.security_id.in_(source_security_ids)))

    rows = []
    for record in prices.to_dict(orient="records"):
        security_id = ids.get(record["ticker"])
        if security_id is None:
            continue
        rows.append(
            Price(
                security_id=security_id,
                date=_coerce_date(record["date"]),
                open=_coerce_float(record["open"]) or 0.0,
                high=_coerce_float(record["high"]) or 0.0,
                low=_coerce_float(record["low"]) or 0.0,
                close=_coerce_float(record["close"]) or 0.0,
                adj_close=_coerce_float(record["adj_close"]) or 0.0,
                volume=_coerce_float(record["volume"]) or 0.0,
                source=source,
            )
        )
    session.add_all(rows)
    return len(rows)


def persist_fundamentals(
    session: Session,
    features: pd.DataFrame,
    source: DataSource,
    ids: dict[str, int],
) -> int:
    metric_columns = [
        "pe_ratio",
        "pb_ratio",
        "ev_to_ebitda",
        "fcf_yield",
        "roe",
        "gross_margin",
        "debt_to_equity",
        "earnings_stability",
        "market_cap",
    ]
    latest = features.sort_values("date").groupby("ticker", as_index=False).tail(1)
    source_security_ids = [ids[ticker] for ticker in latest["ticker"].drop_duplicates() if ticker in ids]
    if source_security_ids:
        session.execute(delete(Fundamental).where(Fundamental.security_id.in_(source_security_ids)))

    rows = []
    for record in latest.to_dict(orient="records"):
        security_id = ids.get(record["ticker"])
        if security_id is None:
            continue
        for metric in metric_columns:
            rows.append(
                Fundamental(
                    security_id=security_id,
                    as_of_date=_coerce_date(record["date"]),
                    fiscal_period_end=None,
                    metric=metric,
                    value=_coerce_float(record.get(metric)) or 0.0,
                    source=source,
                )
            )
    session.add_all(rows)
    return len(rows)


def persist_features(session: Session, features: pd.DataFrame, ids: dict[str, int]) -> int:
    source_security_ids = [ids[ticker] for ticker in features["ticker"].drop_duplicates() if ticker in ids]
    if source_security_ids:
        session.execute(delete(Feature).where(Feature.security_id.in_(source_security_ids)))

    rows = []
    for record in features.to_dict(orient="records"):
        security_id = ids.get(record["ticker"])
        if security_id is None:
            continue
        payload = {column: _coerce_float(record.get(column)) for column in FEATURE_COLUMNS}
        rows.append(Feature(security_id=security_id, date=_coerce_date(record["date"]), **payload))
    session.add_all(rows)
    return len(rows)


def persist_predictions(session: Session, rankings: pd.DataFrame, ids: dict[str, int]) -> int:
    model_name = "weighted_score"
    source_security_ids = [ids[ticker] for ticker in rankings["ticker"].drop_duplicates() if ticker in ids]
    if source_security_ids:
        session.execute(
            delete(ModelPrediction).where(
                ModelPrediction.security_id.in_(source_security_ids),
                ModelPrediction.model_name == model_name,
            )
        )

    rows = []
    for record in rankings.to_dict(orient="records"):
        security_id = ids.get(record["ticker"])
        if security_id is None:
            continue
        rows.append(
            ModelPrediction(
                security_id=security_id,
                date=_coerce_date(record["date"]),
                model_name=model_name,
                score=_coerce_float(record["composite_score"]) or 0.0,
                rank=int(record["rank"]),
            )
        )
    session.add_all(rows)
    return len(rows)


def persist_backtest(session: Session, source: DataSource, result: dict) -> int:
    metrics = result["metrics"]
    session.add(
        BacktestResult(
            name=f"{source}-top-10",
            started_at=utc_now(),
            cagr=_coerce_float(metrics.get("cagr")),
            sharpe=_coerce_float(metrics.get("sharpe")),
            max_drawdown=_coerce_float(metrics.get("max_drawdown")),
            turnover=_coerce_float(metrics.get("average_turnover")),
        )
    )
    return 1


def persist_pipeline_snapshot(source: DataSource = "sample", database_url: str | None = None) -> dict[str, int | str]:
    initialize_database(database_url)
    prices, features, rankings = load_platform_data(source)
    backtest = run_top_n_backtest(rankings, prices, n=10)
    session_factory = build_session_factory(database_url or get_settings().database_url)

    with session_factory() as session:
        ids = persist_securities(session)
        counts = {
            "prices": persist_prices(session, prices, source, ids),
            "fundamentals": persist_fundamentals(session, features, source, ids),
            "features": persist_features(session, features, ids),
            "model_predictions": persist_predictions(session, rankings, ids),
            "backtest_results": persist_backtest(session, source, backtest),
        }
        session.commit()

    return {"source": source, **counts}


def database_status(database_url: str | None = None) -> dict[str, int | str]:
    initialize_database(database_url)
    session_factory = build_session_factory(database_url or get_settings().database_url)
    with session_factory() as session:
        return {
            "database_url": database_url or get_settings().database_url,
            "securities": session.scalar(select(func.count()).select_from(Security)) or 0,
            "prices": session.scalar(select(func.count()).select_from(Price)) or 0,
            "fundamentals": session.scalar(select(func.count()).select_from(Fundamental)) or 0,
            "features": session.scalar(select(func.count()).select_from(Feature)) or 0,
            "model_predictions": session.scalar(select(func.count()).select_from(ModelPrediction)) or 0,
            "backtest_results": session.scalar(select(func.count()).select_from(BacktestResult)) or 0,
        }
