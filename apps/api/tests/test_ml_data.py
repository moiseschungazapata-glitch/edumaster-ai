from datetime import datetime

import pytest

from app.ml.data import FEATURES, dataset_hash, demo_examples, validate_examples


def test_synthetic_dataset_is_reproducible_and_purges_future_labels():
    rows = demo_examples()
    assert rows == demo_examples()
    assert dataset_hash(rows) == dataset_hash(list(rows))
    train, validation, test = validate_examples(rows)
    assert len(train) >= 50 and len(validation) >= 20 and len(test) >= 20
    assert len(train) + len(validation) + len(test) < len(rows)
    assert datetime.fromisoformat(train[-1]["label_observed_at"]) < datetime.fromisoformat(validation[0]["as_of"])
    assert datetime.fromisoformat(validation[-1]["label_observed_at"]) < datetime.fromisoformat(test[0]["as_of"])
    assert len(rows[0]["sequence"][0]) == len(FEATURES)


def test_supervised_data_contract_blocks_missing_outcomes_and_leakage():
    rows = demo_examples()
    rows[0]["feature_window_end"] = rows[0]["label_observed_at"]
    with pytest.raises(ValueError, match="Feature window"):
        validate_examples(rows)
    rows = demo_examples()
    rows[0]["label_observed_at"] = rows[0]["as_of"]
    with pytest.raises(ValueError, match="strictly after"):
        validate_examples(rows)
    rows = demo_examples()
    rows[1]["student_key"] = rows[0]["student_key"]
    with pytest.raises(ValueError, match="unique"):
        validate_examples(rows)
    rows = demo_examples()
    rows[1]["sequence"][0][0] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        validate_examples(rows)
    with pytest.raises(ValueError, match="At least 100"):
        validate_examples(rows[:1])


def test_model_heads_and_baseline_when_ml_dependencies_are_installed():
    torch = pytest.importorskip("torch")
    pytest.importorskip("mlflow")
    from app.ml.train import MultiTaskNetwork, baseline

    outputs = MultiTaskNetwork()(torch.zeros(2, 6, 4))
    assert [tuple(item.shape) for item in outputs] == [(2,), (2, 3), (2,), (2, 3)]
    train, _, test = validate_examples(demo_examples())
    result = baseline(train, test)
    assert 0 <= result["completion"]["brier"] <= 1
    assert 0 <= result["ranking"]["ndcg_at_3"] <= 1
