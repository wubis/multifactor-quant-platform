from multifactor_platform.models.ml import ModelSpec, make_linear_regression


def linear_regression_spec() -> ModelSpec:
    return ModelSpec(
        name="Linear Regression",
        factory=make_linear_regression,
        engine="sklearn_linear_regression",
    )
