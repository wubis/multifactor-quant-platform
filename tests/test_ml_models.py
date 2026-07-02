from multifactor_platform.features.pipeline import build_feature_frame
from multifactor_platform.ingestion.sample_data import make_sample_fundamentals, make_sample_prices
from multifactor_platform.models.ml import (
    build_ml_rankings,
    evaluate_models,
    prepare_model_frame,
    walk_forward_validate_model,
)
from multifactor_platform.models.linear_model import linear_regression_spec


def test_prepare_model_frame_adds_relative_forward_return_target():
    features = build_feature_frame(make_sample_prices(days=360), make_sample_fundamentals()).dropna()

    model_frame = prepare_model_frame(features)

    assert not model_frame.empty
    assert "next_21d_relative_return" in model_frame.columns
    assert model_frame["next_21d_relative_return"].notna().all()


def test_linear_model_walk_forward_validation_runs():
    features = build_feature_frame(make_sample_prices(days=420), make_sample_fundamentals()).dropna()
    model_frame = prepare_model_frame(features)

    result = walk_forward_validate_model(model_frame, linear_regression_spec())

    assert result["status"] == "Active"
    assert not result["folds"].empty
    assert not result["predictions"].empty
    assert result["train_metrics"]["rank_ic"] is not None
    assert result["placebo_metrics"]["rank_ic"] is not None
    assert "yearly_rank_ic" in result
    assert "diagnostic_warnings" in result
    assert "rank_ic" in result["metrics"]


def test_evaluate_models_includes_baseline_and_ml_models():
    features = build_feature_frame(make_sample_prices(days=420), make_sample_fundamentals()).dropna()

    results = evaluate_models(features)
    names = {result["name"] for result in results}

    assert "Weighted Score" in names
    assert "Linear Regression" in names
    assert "Elastic Net" in names
    assert "Random Forest" in names
    assert "Gradient Boosting" in names


def test_build_ml_rankings_creates_ranked_prediction_frame():
    features = build_feature_frame(make_sample_prices(days=420), make_sample_fundamentals()).dropna()

    rankings = build_ml_rankings(features, "Random Forest")

    assert not rankings.empty
    assert {"date", "ticker", "sector", "rank", "composite_score"}.issubset(rankings.columns)
    assert rankings.groupby("date")["rank"].min().eq(1).all()
