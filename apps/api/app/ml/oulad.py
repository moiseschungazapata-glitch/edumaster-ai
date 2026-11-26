"""Convert the public OULAD CSV archive into leakage-controlled offline examples.

Source: Kuzilek, Hlosta and Zdrahal, OULAD, DOI 10.24432/C5KK69 (CC BY 4.0).
This benchmark cannot authorize predictions about EduMaster learners.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.ml.data import SCHEMA, dataset_hash, validate_oulad_examples

COHORTS = ("2013B", "2013J", "2014J")
DISCUSSION = {"forumng", "oucollaborate", "ouwiki", "ouelluminate"}
PRACTICE = {"quiz", "externalquiz", "questionnaire"}


def _csv(archive, name):
    return csv.DictReader(io.TextIOWrapper(archive.open(name), encoding="utf-8-sig"))


def _day(value):
    return None if value in ("", "?") else int(value)


def _start(cohort):
    return datetime(int(cohort[:4]), 2 if cohort.endswith("B") else 10, 1, tzinfo=timezone.utc)


def build_examples(archive_path):
    """Stream OULAD without extracting the 453 MB click table to disk."""
    with zipfile.ZipFile(archive_path) as archive:
        lengths = {(r["code_module"], r["code_presentation"]): int(r["module_presentation_length"])
                   for r in _csv(archive, "courses.csv")}
        assessments = {r["id_assessment"]: (r["code_module"], r["code_presentation"])
                       for r in _csv(archive, "assessments.csv")}
        totals = defaultdict(int)
        for module, cohort in assessments.values():
            totals[(module, cohort)] += 1
        registration = {(r["code_module"], r["code_presentation"], r["id_student"]):
                        (_day(r["date_registration"]), _day(r["date_unregistration"]))
                        for r in _csv(archive, "studentRegistration.csv")}
        # One presentation per student avoids the same learner in two partitions.
        selected = {}
        for row in _csv(archive, "studentInfo.csv"):
            cohort = row["code_presentation"]
            if cohort not in COHORTS:
                continue
            key = (row["code_module"], cohort, row["id_student"])
            dates = registration.get(key)
            if dates is None or dates[0] is None or dates[0] > 42 or (dates[1] is not None and dates[1] <= 42):
                continue
            previous = selected.get(row["id_student"])
            if previous is None or (cohort, row["code_module"]) < (previous["code_presentation"], previous["code_module"]):
                selected[row["id_student"]] = row
        learners = {(r["code_module"], r["code_presentation"], r["id_student"]): r
                    for r in selected.values()}
        submissions = defaultdict(list)
        for row in _csv(archive, "studentAssessment.csv"):
            module, cohort = assessments[row["id_assessment"]]
            key = (module, cohort, row["id_student"])
            day = _day(row["date_submitted"])
            score = _day(row["score"])
            if key in learners and day is not None and day <= 42 and row["is_banked"] == "0" and score is not None:
                submissions[key].append((day, max(0, min(100, score))))
        sites = {r["id_site"]: (r["code_module"], r["code_presentation"], r["activity_type"])
                 for r in _csv(archive, "vle.csv")}
        weekly = defaultdict(lambda: [0] * 6)
        click_days = defaultdict(set)
        future = defaultdict(lambda: [0, 0, 0])
        for row in _csv(archive, "studentVle.csv"):
            module, cohort, kind = sites[row["id_site"]]
            key = (module, cohort, row["id_student"])
            if key not in learners:
                continue
            day = int(row["date"])
            clicks = int(row["sum_click"])
            if 0 <= day <= 42:
                weekly[key][min((max(day, 1) - 1) // 7, 5)] += clicks
                click_days[key].add(day)
            elif 42 < day <= 70:
                category = 1 if kind in DISCUSSION else 2 if kind in PRACTICE else 0
                future[key][category] += clicks
        rows = []
        for key, info in sorted(learners.items()):
            module, cohort, student = key
            # The fourth target is the next observed engagement category. It is
            # not a ground-truth label for the best resource to recommend.
            upcoming = future.get(key, [0, 0, 0])
            if not any(upcoming):
                continue
            sequence = []
            assessments_so_far = sorted(submissions[key])
            active_days = sorted(click_days[key] | {day for day, _ in assessments_so_far})
            # A zero click week is not filled using future activity.
            for step in range(6):
                end = (step + 1) * 7
                available = [score for day, score in assessments_so_far if day <= end]
                progress = min(1.0, len(available) / max(1, totals[(module, cohort)]))
                assessment = sum(available) / (100 * len(available)) if available else 0.0
                visits = min(1.0, math.log1p(weekly[key][step]) / math.log1p(200))
                observed = max([day for day in active_days if day <= end] + [-28])
                inactive = min(1.0, max(0, end - observed) / 28)
                sequence.append([round(value, 4) for value in (progress, assessment, visits, inactive)])
            result = info["final_result"]
            if result not in {"Pass", "Distinction", "Fail", "Withdrawn"}:
                continue
            start = _start(cohort)
            rows.append({
                "student_key": hashlib.sha256(f"{module}:{cohort}:{student}".encode()).hexdigest()[:20],
                "segment": "continuo" if int(info["num_of_prev_attempts"]) else "nuevo",
                "cohort": cohort,
                "as_of": (start + timedelta(days=42)).isoformat(),
                "feature_window_end": (start + timedelta(days=42)).isoformat(),
                "label_observed_at": (start + timedelta(days=lengths[(module, cohort)])).isoformat(),
                "sequence": sequence,
                "labels": {"completion": int(result in {"Pass", "Distinction"}),
                           "mastery": 2 if result == "Distinction" else 1 if result == "Pass" else 0,
                           "risk": int(result == "Withdrawn"),
                           "next_resource": max(range(3), key=lambda index: (upcoming[index], -index))},
            })
    validate_oulad_examples(rows)
    return rows


def write_examples(archive_path, output):
    rows = build_examples(archive_path)
    digest = hashlib.sha256()
    with Path(archive_path).open("rb") as archive:
        for chunk in iter(lambda: archive.read(1024 * 1024), b""):
            digest.update(chunk)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    summary = {"schema": SCHEMA, "source": "OULAD/UCI", "license": "CC BY 4.0",
               "citation": "Kuzilek, Hlosta and Zdrahal (2015), DOI 10.24432/C5KK69",
               "archive_sha256": digest.hexdigest(), "dataset_version": dataset_hash(rows), "rows": len(rows),
               "cohorts": {cohort: sum(r["cohort"] == cohort for r in rows) for cohort in COHORTS},
               "limitation": "External benchmark; next_resource is observed future engagement, not an optimal recommendation."}
    output.with_suffix(".manifest.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Build a public OULAD offline benchmark dataset")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(write_examples(args.archive, args.out), ensure_ascii=False))


if __name__ == "__main__":
    main()
