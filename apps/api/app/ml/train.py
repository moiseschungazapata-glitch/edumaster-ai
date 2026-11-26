"""Offline PyTorch multitask experiment, baseline, evaluation and local MLflow tracking."""
import argparse
import copy
import hashlib
import json
import random
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import mlflow
import numpy as np
import torch
from sklearn.metrics import (
    average_precision_score, balanced_accuracy_score, brier_score_loss,
    confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score,
)
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from app.ml.data import FEATURES, LABELS, SCHEMA, STEPS, _date, dataset_hash, demo_examples, load_labeled, load_oulad, validate_examples, validate_oulad_examples


class MultiTaskNetwork(nn.Module):
    def __init__(self):
        super().__init__()
        self.temporal = nn.GRU(len(FEATURES), 16, batch_first=True)
        self.fusion = nn.Sequential(nn.Linear(16 + len(FEATURES), 24), nn.LayerNorm(24),
                                    nn.ReLU(), nn.Dropout(.1))
        self.completion = nn.Linear(24, 1)
        self.mastery = nn.Linear(24, 3)
        self.risk = nn.Linear(24, 1)
        self.ranking = nn.Linear(24, 3)

    def forward(self, x):
        _, hidden = self.temporal(x)
        fused = self.fusion(torch.cat((hidden[-1], x[:, -1]), dim=1))
        return self.completion(fused).squeeze(-1), self.mastery(fused), self.risk(fused).squeeze(-1), self.ranking(fused)


def _ece(truth, scores, bins=5):
    truth, scores = np.asarray(truth), np.asarray(scores)
    result = 0.0
    for index in range(bins):
        mask = (scores >= index / bins) & (scores < (index + 1) / bins if index < bins - 1 else scores <= 1)
        if mask.any():
            result += mask.mean() * abs(float(truth[mask].mean()) - float(scores[mask].mean()))
    return float(result)


def _binary(truth, scores):
    actual = np.asarray(truth, dtype=int)
    probabilities = np.asarray(scores, dtype=float)
    predicted = (probabilities >= .5).astype(int)
    negatives = actual == 0
    return {
        "roc_auc": float(roc_auc_score(actual, probabilities)) if len(set(actual)) == 2 else None,
        "pr_auc": float(average_precision_score(actual, probabilities)) if actual.any() else None,
        "f1": float(f1_score(actual, predicted, zero_division=0)),
        "recall": float(recall_score(actual, predicted, zero_division=0)),
        "precision": float(precision_score(actual, predicted, zero_division=0)),
        "fpr": float(((predicted == 1) & negatives).sum() / negatives.sum()) if negatives.any() else None,
        "brier": float(brier_score_loss(actual, probabilities)),
        "ece_5_bins": _ece(actual, probabilities),
    }


def _multiclass(truth, scores):
    actual = np.asarray(truth, dtype=int)
    predicted = np.asarray(scores).argmax(axis=1)
    return {
        "macro_f1": float(f1_score(actual, predicted, labels=[0, 1, 2], average="macro", zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(actual, predicted)),
        "ordinal_mae": float(np.abs(actual - predicted).mean()),
        "confusion": confusion_matrix(actual, predicted, labels=[0, 1, 2]).tolist(),
    }


def _ranking(truth, scores):
    order = np.argsort(-np.asarray(scores), axis=1)
    actual = np.asarray(truth, dtype=int)
    positions = np.argmax(order == actual[:, None], axis=1)
    return {
        "ndcg_at_3": float(np.mean(1 / np.log2(positions + 2))),
        "recall_at_2": float(np.mean(positions < 2)),
        "coverage_at_2": float(len(set(order[:, :2].ravel())) / 3),
    }


def evaluate(rows, predictions):
    labels = {name: [row["labels"][name] for row in rows] for name in LABELS}
    result = {
        "completion": _binary(labels["completion"], predictions["completion"]),
        "mastery": _multiclass(labels["mastery"], predictions["mastery"]),
        "risk": _binary(labels["risk"], predictions["risk"]),
        "ranking": _ranking(labels["next_resource"], predictions["next_resource"]),
    }
    result["segments"] = {
        group: {
            "n": sum(row["segment"] == group for row in rows),
            "completion_brier": _binary(
                [labels["completion"][i] for i, row in enumerate(rows) if row["segment"] == group],
                [predictions["completion"][i] for i, row in enumerate(rows) if row["segment"] == group])["brier"],
            "risk_recall": _binary(
                [labels["risk"][i] for i, row in enumerate(rows) if row["segment"] == group],
                [predictions["risk"][i] for i, row in enumerate(rows) if row["segment"] == group])["recall"],
        } for group in sorted({row["segment"] for row in rows})
    }
    return result


def baseline(train, test):
    priors = {name: np.bincount([row["labels"][name] for row in train], minlength=classes) / len(train)
              for name, classes in (("completion", 2), ("mastery", 3), ("risk", 2), ("next_resource", 3))}
    return evaluate(test, {
        "completion": [float(priors["completion"][1])] * len(test),
        "mastery": np.tile(priors["mastery"], (len(test), 1)),
        "risk": [float(priors["risk"][1])] * len(test),
        "next_resource": np.tile(priors["next_resource"], (len(test), 1)),
    })


def train_model(train, validation, test, seed, epochs):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    values = np.asarray([row["sequence"] for row in train], dtype=np.float32)
    mean = values.mean(axis=(0, 1))
    std = np.maximum(values.std(axis=(0, 1)), 1e-6)

    def features(rows):
        return torch.tensor((np.asarray([row["sequence"] for row in rows], dtype=np.float32) - mean) / std)

    def labels(rows, name):
        return torch.tensor([row["labels"][name] for row in rows], dtype=torch.long)

    loader = DataLoader(TensorDataset(
        features(train), *(labels(train, name) for name in LABELS)),
        batch_size=32, shuffle=True, generator=torch.Generator().manual_seed(seed))
    model = MultiTaskNetwork()
    optimizer = torch.optim.AdamW(model.parameters(), lr=.003, weight_decay=.01)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=.5, patience=3)
    bce = nn.BCEWithLogitsLoss()
    ce = nn.CrossEntropyLoss()
    best, best_state, patience, history = float("inf"), None, 0, []
    val_x = features(validation)
    val_y = [labels(validation, name) for name in LABELS]

    def loss(outputs, targets):
        return bce(outputs[0], targets[0].float()) + ce(outputs[1], targets[1]) + (
            bce(outputs[2], targets[2].float()) + ce(outputs[3], targets[3]))

    for epoch in range(1, epochs + 1):
        model.train()
        total = 0.0
        for x, *y in loader:
            optimizer.zero_grad()
            objective = loss(model(x), y)
            objective.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total += float(objective.detach()) * len(x)
        model.eval()
        with torch.no_grad():
            val_loss = float(loss(model(val_x), val_y))
        scheduler.step(val_loss)
        history.append({"epoch": epoch, "train_loss": total / len(train), "val_loss": val_loss})
        if val_loss < best - 1e-4:
            best, best_state, patience = val_loss, copy.deepcopy(model.state_dict()), 0
        else:
            patience += 1
            if patience >= 8:
                break
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        outputs = model(features(test))
        predictions = {
            "completion": torch.sigmoid(outputs[0]).tolist(),
            "mastery": torch.softmax(outputs[1], dim=1).tolist(),
            "risk": torch.sigmoid(outputs[2]).tolist(),
            "next_resource": torch.softmax(outputs[3], dim=1).tolist(),
        }
    return model, {"mean": mean.tolist(), "std": std.tolist()}, history, evaluate(test, predictions)


def _flatten(prefix, value):
    for key, item in value.items():
        name = f"{prefix}.{key}"
        if isinstance(item, dict):
            yield from _flatten(name, item)
        elif isinstance(item, (int, float)) and item is not None:
            yield name, float(item)


def run(source, data_path, output, seed=27, epochs=40):
    if source == "demo":
        rows = demo_examples(seed=seed)
    elif source in {"labeled", "oulad"}:
        if data_path is None:
            raise ValueError("A labeled JSONL file is required")
        rows = load_oulad(Path(data_path)) if source == "oulad" else load_labeled(Path(data_path))
        if any(_date(row["label_observed_at"]) > datetime.now(timezone.utc) for row in rows):
            raise ValueError("Future outcome labels are not mature")
    else:
        raise ValueError("Unknown source")
    train, validation, test = (validate_oulad_examples(rows) if source == "oulad" else validate_examples(rows))
    baseline_metrics = baseline(train, test)
    model, scaler, history, metrics = train_model(train, validation, test, seed, epochs)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    data_version = dataset_hash(rows)
    digest = hashlib.sha256(b"".join(tensor.detach().numpy().tobytes()
                                     for _, tensor in sorted(model.state_dict().items()))).hexdigest()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip() or "unknown"
    checkpoint = {"state_dict": model.state_dict(), "normalization": scaler, "features": FEATURES,
                  "labels": LABELS, "schema": SCHEMA, "steps": STEPS,
                  "data_version": data_version, "model_version": digest}
    torch.save(checkpoint, output / "candidate.pt")
    comparison = {
        "completion_brier_improved": metrics["completion"]["brier"] < baseline_metrics["completion"]["brier"],
        "risk_pr_auc_improved": metrics["risk"]["pr_auc"] > baseline_metrics["risk"]["pr_auc"],
        "mastery_macro_f1_improved": metrics["mastery"]["macro_f1"] > baseline_metrics["mastery"]["macro_f1"],
        "ranking_ndcg_improved": metrics["ranking"]["ndcg_at_3"] > baseline_metrics["ranking"]["ndcg_at_3"],
    }
    source_name = {"demo": "synthetic-demo", "labeled": "authorized-labeled", "oulad": "public-oulad-benchmark"}[source]
    status = {"demo": "demo_only", "labeled": "candidate_pending_human_review", "oulad": "external_validation_only"}[source]
    result = {
        "source": source_name,
        "status": status,
        "schema": SCHEMA, "data_version": data_version, "model_version": digest,
        "git_commit": commit, "seed": seed, "epochs_trained": len(history),
        "split": {"train": len(train), "validation": len(validation), "test": len(test),
                  "purged": len(rows) - len(train) - len(validation) - len(test)},
        "baseline": baseline_metrics, "model": metrics, "comparison": comparison,
    }
    (output / "evaluation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "history.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    limitation = ("OULAD son datos anonimizados de otra institución. El objetivo next_resource representa la categoría de actividad futura observada, no el mejor recurso pedagógico; no se puede usar como recomendador. La evaluación no prueba transferencia a EduMaster."
                  if source == "oulad" else
                  "Las etiquetas sintéticas no demuestran utilidad real, causalidad ni calibración en estudiantes." if source == "demo" else
                  "La evaluación offline no sustituye la revisión técnica, docente, de privacidad ni la validación en EduMaster.")
    card = f"""# Model card: EduMaster multitarea\n\n- Estado: {result['status']}. Sin inferencia en producción.\n- Fuente: {result['source']}; versión dataset: {data_version}.\n- Atribución OULAD si aplica: Kuzilek, Hlosta y Zdrahal; DOI 10.24432/C5KK69; CC BY 4.0.\n- Esquema: {SCHEMA}; corte cronológico, separación con purga de etiquetas futuras.\n- Muestras: {result['split']}.\n- Arquitectura: GRU + capa densa/LayerNorm/Dropout; finalización, dominio ordinal, riesgo y ranking de tres opciones.\n- Baseline: prevalencias del entrenamiento, sin información del conjunto de prueba.\n- Evaluación: ver evaluation.json y history.json; métricas calculadas sobre el test temporal una sola vez.\n- Segmentos: {list(metrics['segments'])}. Los segmentos no son una auditoría de equidad completa.\n- Limitaciones: {limitation}\n- Uso prohibido: notas definitivas, sanciones, decisiones de acceso y recomendaciones personalizadas en producción.\n- Siguiente puerta: cohorte etiquetada, autorizada y suficiente de EduMaster; revisión técnica, docente, de privacidad y aprobación explícita antes de staging/shadow.\n- Rollback: no hay despliegue ni promoción automática; descartar candidate.pt y mantener las fases 1–4.\n"""
    (output / "model_card.md").write_text(card, encoding="utf-8")
    tracking_db = (output.parent / "mlruns" / "tracking.db").resolve()
    tracking_db.parent.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(f"sqlite:///{tracking_db.as_posix()}")
    client = mlflow.tracking.MlflowClient()
    if client.get_experiment_by_name("edumaster-phase5") is None:
        client.create_experiment("edumaster-phase5",
                                 artifact_location=(tracking_db.parent / "artifacts").as_uri())
    mlflow.set_experiment("edumaster-phase5")
    with mlflow.start_run(run_name=f"{source}-{digest[:12]}") as tracked_run:
        mlflow.log_params({"source": result["source"], "schema": SCHEMA, "data_version": data_version,
                           "model_version": digest, "seed": seed, "epochs": len(history), "git_commit": commit})
        for key, value in _flatten("model", metrics):
            mlflow.log_metric(key, value)
        for key, value in _flatten("baseline", baseline_metrics):
            mlflow.log_metric(key, value)
        for entry in history:
            mlflow.log_metrics({"train_loss": entry["train_loss"], "val_loss": entry["val_loss"]}, step=entry["epoch"])
        for name in ("evaluation.json", "history.json", "model_card.md", "candidate.pt"):
            mlflow.log_artifact(str(output / name))
    registry = {"model_version": digest, "data_version": data_version,
                "mlflow_run_id": tracked_run.info.run_id, "status": result["status"],
                "promoted": False, "rollback": "no production deployment"}
    (output / "registry.json").write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description="Train an offline candidate, never promote automatically.")
    parser.add_argument("--source", choices=("demo", "labeled", "oulad"), required=True)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=27)
    parser.add_argument("--epochs", type=int, default=40)
    args = parser.parse_args()
    if args.epochs < 1 or args.epochs > 200:
        parser.error("--epochs must be 1..200")
    result = run(args.source, args.data, args.out, args.seed, args.epochs)
    print(json.dumps({"source": result["source"], "status": result["status"],
                      "model_version": result["model_version"], "comparison": result["comparison"]}))


if __name__ == "__main__":
    main()
