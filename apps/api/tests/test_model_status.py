import pytest
from fastapi import HTTPException

from app.guidance import model_status, predict


def test_public_benchmark_status_does_not_enable_inference():
    status = model_status()
    benchmark = status["benchmark"]
    assert status["status"] == "external_validation_only"
    assert status["prediction_enabled"] is False
    assert benchmark["source"] == "public-oulad-benchmark"
    assert benchmark["examples"] == sum(benchmark["split"].values())
    assert benchmark["metrics"]["completion_brier"] > benchmark["metrics"]["completion_baseline_brier"]
    with pytest.raises(HTTPException) as blocked:
        predict()
    assert blocked.value.status_code == 503
