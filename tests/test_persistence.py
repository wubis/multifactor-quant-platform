from multifactor_platform.db.persistence import database_status, persist_pipeline_snapshot


def test_persist_sample_pipeline_snapshot_to_sqlite(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'multifactor.db'}"

    result = persist_pipeline_snapshot("sample", database_url=database_url)
    status = database_status(database_url=database_url)

    assert result["source"] == "sample"
    assert status["securities"] > 0
    assert status["prices"] > 0
    assert status["features"] > 0
    assert status["model_predictions"] > 0
    assert status["backtest_results"] == 1
