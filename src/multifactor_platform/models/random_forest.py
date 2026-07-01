from multifactor_platform.models.ml import ModelSpec, make_random_forest


def random_forest_spec() -> ModelSpec:
    return ModelSpec(
        name="Random Forest",
        factory=make_random_forest,
        engine="sklearn_random_forest",
    )
