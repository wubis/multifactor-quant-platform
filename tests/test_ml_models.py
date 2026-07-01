from multifactor_platform.features.pipeline import build_feature_frame
from multifactor_platform.ingestion.sample_data import make_sample_fundamentals, make_sample_prices
from multifactor_platform.models.ml import (
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
