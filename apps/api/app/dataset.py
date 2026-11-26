"""Deterministic, institution-scoped academic event dataset (schema v1).

Only aggregated features are written to disk. Raw actors never appear in exports.
"""
import argparse
import csv
import hashlib
import io
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import engine
from app.core.models import AcademicEvent

SCHEMA = "academic-daily-v1"
KINDS = {
    "course_created", "course_published", "enrolled", "lesson_completed",
    "assessment_passed", "assessment_failed", "path_created",
    "course_updated", "course_unpublished", "teacher_assigned", "courses_imported", "courses_exported",
    "lesson_created", "lesson_updated", "lesson_restored", "unit_created", "resource_created", "resource_downloaded", "resource_deleted",
    "activity_created", "assessment_copied", "assessment_submitted", "submission_downloaded",
    "path_published", "path_assigned", "cohort_created", "cohort_student_added", "cohort_enrolled",
    "certificate_issued", "certificate_downloaded", "certificate_revoked", "certificate_reissued",
}
FEATURE_KINDS = {
    "enrolled": "enrollments",
    "lesson_completed": "lesson_completions",
    "assessment_passed": "assessment_passes",
    "assessment_failed": "assessment_failures",
}
FIELDS = ["date", "course_id", "enrollments", "lesson_completions",
          "assessment_passes", "assessment_failures", "active_actors"]


def _stamp(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp without timezone")
    return parsed.astimezone(timezone.utc)


def database_stamp(value):
    # PostgreSQL returns an aware TIMESTAMPTZ; SQLite test databases omit tzinfo.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _validate(row):
    event_id = int(row["id"])
    if event_id <= 0 or row["kind"] not in KINDS:
        raise ValueError("invalid id or event kind")
    actor = str(uuid.UUID(str(row["actor_id"])))
    course = str(uuid.UUID(str(row["course_id"]))) if row.get("course_id") else None
    if row["kind"] in FEATURE_KINDS and course is None:
        raise ValueError("academic action without course")
    return event_id, row["kind"], actor, course, _stamp(row["occurred_at"])


def build_dataset(records):
    """Validate, deduplicate and aggregate an iterable of event dictionaries."""
    seen = set()
    groups = defaultdict(lambda: {"enrollments": 0, "lesson_completions": 0,
                                  "assessment_passes": 0, "assessment_failures": 0, "actors": set()})
    rejected = 0
    duplicate = 0
    accepted = 0
    latest = None
    for record in records:
        try:
            event_id, kind, actor, course, occurred = _validate(record)
        except (ValueError, TypeError, KeyError, OverflowError):
            rejected += 1
            continue
        if event_id in seen:
            duplicate += 1
            continue
        seen.add(event_id)
        accepted += 1
        latest = max(latest, occurred) if latest else occurred
        if kind in FEATURE_KINDS:
            group = groups[(occurred.date().isoformat(), course)]
            group[FEATURE_KINDS[kind]] += 1
            group["actors"].add(actor)
    rows = [
        {"date": day, "course_id": course,
         **{name: item[name] for name in FEATURE_KINDS.values()},
         "active_actors": len(item["actors"])}
        for (day, course), item in sorted(groups.items())
    ]
    quality = {"accepted": accepted, "rejected": rejected, "duplicate_ids": duplicate,
               "feature_rows": len(rows)}
    return rows, quality, latest


def csv_bytes(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def manifest(rows, quality, latest, source):
    digest = hashlib.sha256(csv_bytes(rows)).hexdigest()
    return {"schema": SCHEMA, "source": source, "version": digest,
            "as_of": latest.isoformat() if latest else None, "quality": quality,
            "columns": FIELDS, "timezone": "UTC"}


def write_dataset(records, output, source):
    rows, quality, latest = build_dataset(records)
    if quality["rejected"] or quality["duplicate_ids"]:
        raise ValueError(f"Quality gate failed: {quality}. No dataset was written.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "daily_course_features.csv").write_bytes(csv_bytes(rows))
    metadata = manifest(rows, quality, latest, source)
    (output / "manifest.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description="Build a versioned academic dataset; never exports raw actor IDs.")
    parser.add_argument("--source", choices=("demo", "database"), required=True)
    parser.add_argument("--institution", type=uuid.UUID, help="Required for authorized database extraction")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.source == "demo":
        if args.institution:
            parser.error("--institution is only valid with --source database")
        sample = Path(__file__).resolve().parents[1] / "data" / "demo_events.jsonl"
        with sample.open(encoding="utf-8") as source:
            records = [json.loads(line) for line in source if line.strip()]
        label = "synthetic-demo"
    else:
        if not args.institution:
            parser.error("--institution is required with --source database")
        with Session(engine()) as db:
            events = db.scalars(select(AcademicEvent).where(
                AcademicEvent.institution_id == args.institution).order_by(AcademicEvent.id))
            records = [{"id": event.id, "kind": event.kind, "actor_id": event.actor_id,
                        "course_id": event.course_id, "occurred_at": database_stamp(event.occurred_at)}
                       for event in events]
        label = "institution-database"
    result = write_dataset(records, args.out, label)
    print(json.dumps({"version": result["version"], "quality": result["quality"]}))


if __name__ == "__main__":
    main()
