from multifactor_platform.models.ml import ModelSpec, gradient_boosting_engine, make_gradient_boosting


def gradient_boosting_spec() -> ModelSpec:
    return ModelSpec(
        name="Gradient Boosting",
        factory=make_gradient_boosting,
        engine=gradient_boosting_engine(),
    )
