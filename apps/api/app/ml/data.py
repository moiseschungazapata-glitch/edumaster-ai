"""Versioned supervised examples with a strict chronological observation boundary."""
import hashlib
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

FEATURES = ("progress", "assessment", "visits", "inactive_days")
LABELS = ("completion", "mastery", "risk", "next_resource")
SCHEMA = "student-sequence-supervised-v1"
STEPS = 6


def demo_examples(size=360, seed=27):
    rng = random.Random(seed)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(size):
        sequence = []
        progress = rng.random() * .35
        visits = rng.random()
        for _ in range(STEPS):
            progress = min(1.0, max(0.0, progress + rng.uniform(-.04, .16)))
            visits = max(0.0, min(1.0, visits + rng.uniform(-.25, .25)))
            score = max(0.0, min(1.0, progress + rng.uniform(-.2, .2)))
            inactive = rng.random() if visits < .4 else rng.random() * .5
            sequence.append([round(v, 4) for v in (progress, score, visits, inactive)])
        end = sequence[-1]
        completion = int(end[0] + .3 * end[2] + rng.uniform(-.2, .2) > .53)
        mastery = 0 if end[1] < .35 else 1 if end[1] < .65 else 2
        risk = int(end[3] - .4 * end[2] + rng.uniform(-.2, .2) > .30)
        resource = 0 if mastery == 0 else 1 if risk else 2
        observed = start + timedelta(days=i)
        rows.append({
            "student_key": f"SYNTH-{i:04d}", "segment": "nuevo" if i % 2 else "continuo",
            "as_of": observed.isoformat(), "feature_window_end": observed.isoformat(),
            "label_observed_at": (observed + timedelta(days=30)).isoformat(),
            "sequence": sequence,
            "labels": {"completion": completion, "mastery": mastery, "risk": risk, "next_resource": resource},
        })
    return rows


def _date(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_examples(rows):
    _validate_rows(rows)
    ordered = sorted(rows, key=lambda r: (_date(r["as_of"]), r["student_key"]))
    cut1, cut2 = int(len(rows) * .6), int(len(rows) * .8)
    train, validation, test = ordered[:cut1], ordered[cut1:cut2], ordered[cut2:]
    train = [row for row in train if _date(row["label_observed_at"]) < _date(validation[0]["as_of"])]
    validation = [row for row in validation if _date(row["label_observed_at"]) < _date(test[0]["as_of"])]
    _validate_partitions(train, validation, test)
    return train, validation, test


def _validate_rows(rows):
    if len(rows) < 100:
        raise ValueError("At least 100 labeled independent examples are required")
    keys = set()
    for row in rows:
        if not row.get("student_key") or row["student_key"] in keys:
            raise ValueError("Each learner needs a unique pseudonymous key and one snapshot")
        keys.add(row["student_key"])
        if _date(row["feature_window_end"]) > _date(row["as_of"]):
            raise ValueError("Feature window must end at or before the prediction cutoff")
        if _date(row["label_observed_at"]) <= _date(row["as_of"]):
            raise ValueError("Labels must be observed strictly after the feature cutoff")
        sequence = row["sequence"]
        if len(sequence) != STEPS or any(len(step) != len(FEATURES) for step in sequence):
            raise ValueError("Feature sequence does not match the fixed schema")
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > 1
               for step in sequence for value in step):
            raise ValueError("Features must be finite numbers normalized to [0,1]")
        labels = row["labels"]
        if any(labels.get(name) not in range(classes) for name, classes in
               (("completion", 2), ("mastery", 3), ("risk", 2), ("next_resource", 3))):
            raise ValueError("Invalid labels")
        if not row.get("segment"):
            raise ValueError("Segment missing")


def _validate_partitions(train, validation, test):
    if len(train) < 50 or len(validation) < 20 or len(test) < 20:
        raise ValueError("Insufficient matured examples after purging label overlap")
    for partition in (train, validation, test):
        for label, classes in (("completion", 2), ("mastery", 3), ("risk", 2), ("next_resource", 3)):
            if set(row["labels"][label] for row in partition) != set(range(classes)):
                raise ValueError(f"Insufficient label diversity for {label} in temporal split")


def validate_oulad_examples(rows):
    """Reserve entire presentations for validation and test, without learner overlap."""
    _validate_rows(rows)
    cohorts = ("2013B", "2013J", "2014J")
    if {row.get("cohort") for row in rows} != set(cohorts):
        raise ValueError("OULAD requires 2013B, 2013J and 2014J presentations")
    partitions = [[row for row in rows if row["cohort"] == cohort] for cohort in cohorts]
    train, validation, test = partitions
    if max(_date(row["label_observed_at"]) for row in train) >= min(_date(row["as_of"]) for row in validation):
        raise ValueError("Training labels overlap validation features")
    if max(_date(row["label_observed_at"]) for row in validation) >= min(_date(row["as_of"]) for row in test):
        raise ValueError("Validation labels overlap test features")
    _validate_partitions(train, validation, test)
    return train, validation, test


def dataset_hash(rows):
    encoded = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_labeled(path: Path):
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def load_oulad(path: Path):
    rows = load_labeled(path)
    manifest = json.loads(path.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    if manifest.get("source") != "OULAD/UCI" or manifest.get("dataset_version") != dataset_hash(rows):
        raise ValueError("OULAD manifest does not match the labeled dataset")
    return rows
