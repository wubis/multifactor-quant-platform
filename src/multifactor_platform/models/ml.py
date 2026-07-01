from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.base import RegressorMixin
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


MODEL_FEATURE_COLUMNS = [
    "momentum_1m_z",
    "momentum_3m_z",
    "momentum_6m_z",
    "momentum_12m_ex_1m_z",
    "volatility_20d_z",
    "volatility_60d_z",
    "beta_252d_z",
    "pe_ratio_z",
    "pb_ratio_z",
    "fcf_yield_z",
    "roe_z",
    "gross_margin_z",
    "debt_to_equity_z",
    "earnings_stability_z",
    "market_cap_z",
    "dollar_volume_z",
]
TARGET_COLUMN = "next_21d_relative_return"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    factory: Callable[[], RegressorMixin]
    engine: str


def add_forward_return_target(
    features: pd.DataFrame,
    horizon_days: int = 21,
    target_column: str = TARGET_COLUMN,
) -> pd.DataFrame:
    output = features.sort_values(["ticker", "date"]).copy()
    output["next_21d_return"] = output.groupby("ticker")["adj_close"].pct_change(horizon_days).shift(
        -horizon_days
    )
    output[target_column] = output["next_21d_return"] - output.groupby("date")[
        "next_21d_return"
    ].transform("mean")
    return output


def prepare_model_frame(features: pd.DataFrame) -> pd.DataFrame:
    available_features = [column for column in MODEL_FEATURE_COLUMNS if column in features.columns]
    model_frame = add_forward_return_target(features)
    required = ["date", "ticker", TARGET_COLUMN, *available_features]
    model_frame = model_frame.dropna(subset=required).copy()
    return model_frame[required]


def make_linear_regression() -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("model", LinearRegression())])


def make_elastic_net() -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            ("model", ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=10_000, random_state=7)),
        ]
    )


def make_random_forest() -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=80,
        max_depth=6,
        min_samples_leaf=20,
        random_state=7,
        n_jobs=1,
    )


def make_gradient_boosting() -> RegressorMixin:
    try:
        from xgboost import XGBRegressor

        return XGBRegressor(
            n_estimators=120,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="reg:squarederror",
            random_state=7,
            n_jobs=1,
            nthread=1,
        )
    except ImportError:
        pass

    try:
        from lightgbm import LGBMRegressor

        return LGBMRegressor(
            n_estimators=120,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=7,
            verbose=-1,
        )
    except ImportError:
        pass

    return HistGradientBoostingRegressor(
        max_iter=120,
        max_leaf_nodes=15,
        learning_rate=0.05,
        l2_regularization=0.01,
        random_state=7,
    )


def gradient_boosting_engine() -> str:
    try:
        import xgboost  # noqa: F401

        return "xgboost"
    except ImportError:
        pass

    try:
        import lightgbm  # noqa: F401

        return "lightgbm"
    except ImportError:
        return "sklearn_hist_gradient_boosting"


def default_model_specs() -> list[ModelSpec]:
    return [
        ModelSpec("Linear Regression", make_linear_regression, "sklearn_linear_regression"),
        ModelSpec("Elastic Net", make_elastic_net, "sklearn_elastic_net"),
        ModelSpec("Random Forest", make_random_forest, "sklearn_random_forest"),
        ModelSpec("Gradient Boosting", make_gradient_boosting, gradient_boosting_engine()),
    ]


def build_walk_forward_splits(
    model_frame: pd.DataFrame,
    min_train_days: int = 252,
    validation_days: int = 63,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    dates = pd.DatetimeIndex(pd.to_datetime(model_frame["date"].drop_duplicates()).sort_values())
    if len(dates) < min_train_days + validation_days:
        min_train_days = max(21, int(len(dates) * 0.55))
        validation_days = max(10, int(len(dates) * 0.15))

    splits = []
    start = min_train_days
    while start + validation_days <= len(dates):
        train_end = dates[start - 1]
        validation_start = dates[start]
        validation_end = dates[start + validation_days - 1]
        splits.append((train_end, validation_start, validation_end))
        start += validation_days
    return splits


def rank_ic_by_date(predictions: pd.DataFrame) -> pd.Series:
    values = {}
    for date, frame in predictions.groupby("date"):
        if frame["prediction"].nunique() < 2 or frame[TARGET_COLUMN].nunique() < 2:
            continue
        statistic = spearmanr(frame["prediction"], frame[TARGET_COLUMN], nan_policy="omit").statistic
        if not np.isnan(statistic):
            values[pd.Timestamp(date)] = float(statistic)
    return pd.Series(values, dtype=float).sort_index()


def evaluate_predictions(predictions: pd.DataFrame) -> dict[str, float]:
    if predictions.empty:
        return {
            "rank_ic": 0.0,
            "rank_ic_std": 0.0,
            "hit_rate": 0.0,
            "rmse": 0.0,
            "mae": 0.0,
            "r2": 0.0,
        }

    rank_ic = rank_ic_by_date(predictions)
    actual = predictions[TARGET_COLUMN]
    predicted = predictions["prediction"]
    return {
        "rank_ic": float(rank_ic.mean()) if not rank_ic.empty else 0.0,
        "rank_ic_std": float(rank_ic.std(ddof=0)) if len(rank_ic) > 1 else 0.0,
        "hit_rate": float((np.sign(predicted) == np.sign(actual)).mean()),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "mae": float(mean_absolute_error(actual, predicted)),
        "r2": float(r2_score(actual, predicted)) if len(predictions) > 1 else 0.0,
    }


def walk_forward_validate_model(
    model_frame: pd.DataFrame,
    model_spec: ModelSpec,
    feature_columns: list[str] | None = None,
) -> dict:
    feature_columns = feature_columns or [
        column for column in MODEL_FEATURE_COLUMNS if column in model_frame.columns
    ]
    splits = build_walk_forward_splits(model_frame)
    predictions = []
    fold_rows = []

    for fold_number, (train_end, validation_start, validation_end) in enumerate(splits, start=1):
        train = model_frame.loc[model_frame["date"] <= train_end]
        validation = model_frame.loc[
            (model_frame["date"] >= validation_start) & (model_frame["date"] <= validation_end)
        ]
        if train.empty or validation.empty:
            continue

        estimator = model_spec.factory()
        estimator.fit(train[feature_columns], train[TARGET_COLUMN])
        validation_predictions = validation[["date", "ticker", TARGET_COLUMN]].copy()
        validation_predictions["prediction"] = estimator.predict(validation[feature_columns])
        validation_predictions["fold"] = fold_number
        predictions.append(validation_predictions)

        metrics = evaluate_predictions(validation_predictions)
        fold_rows.append(
            {
                "fold": fold_number,
                "train_end": train_end,
                "validation_start": validation_start,
                "validation_end": validation_end,
                "train_rows": len(train),
                "validation_rows": len(validation),
                **metrics,
            }
        )

    prediction_frame = (
        pd.concat(predictions, ignore_index=True)
        if predictions
        else pd.DataFrame(columns=["date", "ticker", TARGET_COLUMN, "prediction", "fold"])
    )
    return {
        "name": model_spec.name,
        "engine": model_spec.engine,
        "status": "Active" if not prediction_frame.empty else "Insufficient data",
        "feature_count": len(feature_columns),
        "folds": pd.DataFrame(fold_rows),
        "predictions": prediction_frame,
        "metrics": evaluate_predictions(prediction_frame),
    }


def evaluate_weighted_score(features: pd.DataFrame) -> dict:
    from multifactor_platform.models.weighted_score import score_weighted_model

    model_frame = prepare_model_frame(features)
    scored = score_weighted_model(features)
    scored = scored[["date", "ticker", "composite_score"]].rename(
        columns={"composite_score": "prediction"}
    )
    predictions = model_frame[["date", "ticker", TARGET_COLUMN]].merge(
        scored,
        on=["date", "ticker"],
        how="inner",
    )
    return {
        "name": "Weighted Score",
        "engine": "manual_factor_weights",
        "status": "Baseline",
        "feature_count": 5,
        "folds": pd.DataFrame(),
        "predictions": predictions,
        "metrics": evaluate_predictions(predictions),
    }


def evaluate_models(features: pd.DataFrame) -> list[dict]:
    model_frame = prepare_model_frame(features)
    results = [evaluate_weighted_score(features)]
    results.extend(
        walk_forward_validate_model(model_frame, model_spec)
        for model_spec in default_model_specs()
    )
    return results


def model_results_by_name(features: pd.DataFrame) -> dict[str, dict]:
    return {result["name"]: result for result in evaluate_models(features)}


def build_ml_rankings(
    features: pd.DataFrame,
    model_name: str,
    results: dict[str, dict] | None = None,
) -> pd.DataFrame:
    results = results or model_results_by_name(features)
    if model_name not in results:
        available = ", ".join(sorted(results))
        raise ValueError(f"Unknown model '{model_name}'. Available models: {available}")

    predictions = results[model_name]["predictions"].copy()
    if predictions.empty:
        return pd.DataFrame(columns=["date", "ticker", "sector", "rank", "composite_score"])

    metadata_columns = ["date", "ticker", "sector"]
    metadata = features[[column for column in metadata_columns if column in features.columns]].drop_duplicates(
        ["date", "ticker"]
    )
    ranked = predictions.merge(metadata, on=["date", "ticker"], how="left")
    ranked["composite_score"] = ranked["prediction"]
    ranked["rank"] = ranked.groupby("date")["prediction"].rank(method="first", ascending=False)
    return ranked.sort_values(["date", "rank"]).reset_index(drop=True)
