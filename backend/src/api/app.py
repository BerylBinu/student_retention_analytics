"""
API Lambda - the backend the Next.js dashboard talks to.

Routes (all return JSON):
    GET  /health                  -> {"status": "ok"}
    GET  /insights                -> every analysed message, newest first
                                     optional filters: ?risk_level=HIGH&stressor=FINANCIAL&student_id=TP071234&limit=50
    GET  /students                -> one row per student with their current risk, sorted highest first
    GET  /students/{student_id}   -> one student's profile plus their full timeline
    GET  /stats                   -> totals and chart-ready numbers for the dashboard
    POST /ingest                  -> drop a new raw message into the pipeline (great for the live demo)

For a hackathon-sized dataset (hundreds or a few thousand rows) we simply read the whole
table and aggregate in Python. That keeps the code easy to follow.
"""

import base64
import json
import logging
import os
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("TABLE_NAME", "")
DATA_BUCKET = os.environ.get("DATA_BUCKET", "")
INGEST_PREFIX = os.environ.get("INGEST_PREFIX", "incoming/live/")
MAX_SCAN_ITEMS = 5000
MAX_INGEST_CHARS = 10_000

RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
URGENCY_ORDER = {"ROUTINE": 0, "FOLLOW_UP_THIS_WEEK": 1, "CONTACT_WITHIN_24H": 2, "IMMEDIATE": 3}

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")


# ---------------------------------------------------------------------------
# Entry point and routing
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    route = event.get("routeKey", "")
    params = event.get("queryStringParameters") or {}
    path_params = event.get("pathParameters") or {}
    logger.info("Request %s %s", route, params)

    try:
        if route == "GET /health":
            return respond(200, {"status": "ok", "time": now_iso()})
        if route == "GET /insights":
            return respond(200, list_insights(params))
        if route == "GET /students":
            return respond(200, list_students())
        if route == "GET /students/{student_id}":
            return get_student(path_params.get("student_id", ""))
        if route == "GET /stats":
            return respond(200, get_stats())
        if route == "POST /ingest":
            return ingest(event)
        return respond(404, {"error": f"Unknown route: {route}"})
    except Exception:  # noqa: BLE001
        logger.exception("Unhandled error for %s", route)
        return respond(500, {"error": "Internal server error. Check the ApiFunction logs in CloudWatch."})


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------
def list_insights(params):
    items = scan_all()
    if params.get("risk_level"):
        wanted = {v.strip().upper() for v in params["risk_level"].split(",")}
        items = [i for i in items if i.get("risk_level") in wanted]
    if params.get("stressor"):
        wanted = params["stressor"].strip().upper()
        items = [i for i in items if i.get("primary_stressor") == wanted or wanted in (i.get("secondary_stressors") or [])]
    if params.get("student_id"):
        wanted = params["student_id"].strip().upper()
        items = [i for i in items if i.get("student_id") == wanted]

    items.sort(key=lambda i: i.get("event_time", ""), reverse=True)
    limit = to_int(params.get("limit"), default=200, minimum=1, maximum=1000)
    return {"count": len(items), "items": items[:limit]}


def list_students():
    students = [summarise_student(sid, records) for sid, records in group_by_student(scan_all()).items()]
    students.sort(key=lambda s: (s["current_risk_score"], s["latest_event_time"]), reverse=True)
    return {"count": len(students), "items": students}


def get_student(student_id):
    student_id = student_id.strip().upper()
    records = [i for i in scan_all() if i.get("student_id") == student_id]
    if not records:
        return respond(404, {"error": f"No records for student {student_id}"})
    profile = summarise_student(student_id, records)
    profile["timeline"] = sorted(records, key=lambda r: r.get("event_time", ""))
    return respond(200, profile)


def get_stats():
    items = scan_all()
    students = [summarise_student(sid, recs) for sid, recs in group_by_student(items).items()]

    daily = defaultdict(lambda: {"signals": 0, "risk_total": 0, "high_or_critical": 0})
    for item in items:
        day = daily[item.get("event_date") or item.get("event_time", "")[:10] or "unknown"]
        day["signals"] += 1
        day["risk_total"] += item.get("risk_score", 0)
        if item.get("risk_level") in ("HIGH", "CRITICAL"):
            day["high_or_critical"] += 1

    timeline = [
        {
            "date": date,
            "signals": d["signals"],
            "avg_risk_score": round(d["risk_total"] / d["signals"], 1),
            "high_or_critical": d["high_or_critical"],
        }
        for date, d in sorted(daily.items())
    ]

    return {
        "total_signals": len(items),
        "total_students": len(students),
        "students_needing_attention": sum(1 for s in students if s["current_risk_level"] in ("HIGH", "CRITICAL")),
        "self_harm_alerts": sum(1 for s in students if s["self_harm_flag"]),
        "average_risk_score": round(sum(i.get("risk_score", 0) for i in items) / len(items), 1) if items else 0,
        "signals_by_risk_level": counts_in_order((i.get("risk_level") for i in items), RISK_ORDER),
        "students_by_risk_level": counts_in_order((s["current_risk_level"] for s in students), RISK_ORDER),
        "signals_by_stressor": counter_to_list(
            Counter(i.get("primary_stressor", "NONE") for i in items if i.get("primary_stressor") != "NONE"), "stressor"
        ),
        "signals_by_source": counter_to_list(Counter(i.get("source_system", "OTHER") for i in items), "source"),
        "timeline": timeline,
        "generated_at": now_iso(),
    }


def ingest(event):
    """Accept a raw message from the dashboard and drop it into S3 incoming/live/.

    The S3 -> SQS -> Processor pipeline then picks it up exactly like any other file,
    so the frontend can poll GET /insights a few seconds later to see the result.
    """
    if not DATA_BUCKET:
        return respond(500, {"error": "DATA_BUCKET environment variable is not set"})

    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8", errors="replace")
    try:
        body = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return respond(400, {"error": "Body must be JSON, e.g. {\"student_id\": \"TP012345\", \"text\": \"...\"}"})
    if not isinstance(body, dict):
        return respond(400, {"error": "Body must be a JSON object"})

    text = str(body.get("text") or "").strip()
    if not text:
        return respond(400, {"error": "Field 'text' is required"})
    if len(text) > MAX_INGEST_CHARS:
        return respond(400, {"error": f"Field 'text' must be at most {MAX_INGEST_CHARS} characters"})

    document = {
        "channel": str(body.get("source") or "dashboard_demo")[:50],
        "student_id": str(body.get("student_id") or "")[:20],
        "student_name": str(body.get("student_name") or "")[:100],
        "submitted_at": now_iso(),
        "message": text,
    }
    key = f"{INGEST_PREFIX}{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}.json"
    s3.put_object(
        Bucket=DATA_BUCKET,
        Key=key,
        Body=json.dumps(document, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    return respond(202, {"status": "queued", "s3_key": key, "hint": "Poll GET /insights in ~10 seconds"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def scan_all():
    """Read every row (following DynamoDB's 1 MB pages) and convert Decimals to numbers."""
    table = dynamodb.Table(TABLE_NAME)
    items, kwargs = [], {}
    while True:
        page = table.scan(**kwargs)
        items.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page or len(items) >= MAX_SCAN_ITEMS:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return [from_dynamodb(i) for i in items[:MAX_SCAN_ITEMS]]


def group_by_student(items):
    groups = defaultdict(list)
    for item in items:
        groups[item.get("student_id", "UNKNOWN")].append(item)
    return groups


def summarise_student(student_id, records):
    """Turn many signals into one profile.

    current_risk_score = the highest-risk signal from this student. This is easy to explain
    to judges and counselors: "one serious warning sign is enough to reach out".
    trend compares the most recent signal with the earliest one.
    """
    records = sorted(records, key=lambda r: r.get("event_time", ""))
    worst = max(records, key=lambda r: (r.get("risk_score", 0), URGENCY_ORDER.get(r.get("urgency"), 0)))
    latest = records[-1]
    first_score = records[0].get("risk_score", 0)
    latest_score = latest.get("risk_score", 0)

    if len(records) < 2:
        trend = "NEW"
    elif latest_score - first_score >= 10:
        trend = "RISING"
    elif first_score - latest_score >= 10:
        trend = "FALLING"
    else:
        trend = "STABLE"

    stressor_counts = Counter()
    for r in records:
        if r.get("primary_stressor") and r["primary_stressor"] != "NONE":
            stressor_counts[r["primary_stressor"]] += 2  # primary counts double
        for s in r.get("secondary_stressors") or []:
            stressor_counts[s] += 1

    names = [r.get("student_name") for r in records if r.get("student_name") and r["student_name"] != "Unknown student"]

    return {
        "student_id": student_id,
        "student_name": names[-1] if names else "Unknown student",
        "signal_count": len(records),
        "current_risk_score": worst.get("risk_score", 0),
        "current_risk_level": worst.get("risk_level", "LOW"),
        "latest_risk_score": latest_score,
        "average_risk_score": round(sum(r.get("risk_score", 0) for r in records) / len(records), 1),
        "trend": trend,
        "top_stressors": [s for s, _ in stressor_counts.most_common(3)],
        "self_harm_flag": any(r.get("self_harm_indicator") for r in records),
        "highest_urgency": max((r.get("urgency", "ROUTINE") for r in records), key=lambda u: URGENCY_ORDER.get(u, 0)),
        "recommended_action": worst.get("recommended_action", ""),
        "latest_summary": latest.get("summary", ""),
        "first_event_time": records[0].get("event_time", ""),
        "latest_event_time": latest.get("event_time", ""),
        "sources": sorted({r.get("source_system", "OTHER") for r in records}),
    }


def counts_in_order(values, order):
    counts = Counter(values)
    return [{"level": level, "count": counts.get(level, 0)} for level in order]


def counter_to_list(counter, label):
    return [{label: key, "count": count} for key, count in counter.most_common()]


def from_dynamodb(value):
    """DynamoDB returns numbers as Decimal, which json.dumps cannot handle."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_dynamodb(v) for k, v in value.items()}
    if isinstance(value, (list, set, tuple)):
        return [from_dynamodb(v) for v in value]
    return value


def to_int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def respond(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
