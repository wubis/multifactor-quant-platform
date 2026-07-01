from multifactor_platform.models.ml import ModelSpec, make_elastic_net


def elastic_net_spec() -> ModelSpec:
    return ModelSpec(
        name="Elastic Net",
        factory=make_elastic_net,
        engine="sklearn_elastic_net",
    )
