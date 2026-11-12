"""
API function - the backend the Next.js dashboard talks to (Google Cloud version).

Routes (all return JSON):
    GET  /health                  -> {"status": "ok"}
    GET  /insights                -> every analysed message, newest first
                                     optional filters: ?risk_level=HIGH&stressor=FINANCIAL&student_id=TP071234&limit=50
    GET  /students                -> one row per student with their current risk, sorted highest first
    GET  /students/{student_id}   -> one student's profile plus their full timeline
    GET  /stats                   -> totals and chart-ready numbers for the dashboard
    POST /ingest                  -> drop a new raw message into the pipeline (great for the live demo)
    POST /students/{id}/case      -> counsellor follow-up: {"status": "CONTACTED", "note": "Called, meeting Fri"}
    POST /admin/reset-demo        -> delete live-demo messages and follow-up records (needs the X-Admin-Token header)

Runs as a Cloud Run function (see main.py). Data is read from Firestore; /ingest writes to the
raw Cloud Storage bucket, which triggers the processor function. For a hackathon-sized dataset
(hundreds or a few thousand documents) we simply read the whole collection and aggregate in Python.
"""

import hmac
import json
import logging
import os
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

FIRESTORE_COLLECTION = os.environ.get("FIRESTORE_COLLECTION", "insights")
CASES_COLLECTION = os.environ.get("CASES_COLLECTION", "cases")
RAW_BUCKET = os.environ.get("RAW_BUCKET", "")
INGEST_PREFIX = "incoming/live/"
MAX_SCAN_ITEMS = 5000
MAX_INGEST_CHARS = 10_000
CASE_STATUSES = ("OPEN", "CONTACTED", "RESOLVED")
MAX_NOTE_CHARS = 500
MAX_CASE_HISTORY = 20

RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
URGENCY_ORDER = {"ROUTINE": 0, "FOLLOW_UP_THIS_WEEK": 1, "CONTACT_WITHIN_24H": 2, "IMMEDIATE": 3}

_storage_client = None
_firestore_client = None


def storage_client():
    global _storage_client
    if _storage_client is None:
        from google.cloud import storage

        _storage_client = storage.Client()
    return _storage_client


def firestore_client():
    global _firestore_client
    if _firestore_client is None:
        from google.cloud import firestore

        _firestore_client = firestore.Client()
    return _firestore_client


# ---------------------------------------------------------------------------
# Routing (called from main.py with the parts of the HTTP request)
# ---------------------------------------------------------------------------
def handle_request(method, path, params=None, body_text="", headers=None):
    """Returns (status_code, body_dict)."""
    params = params or {}
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    path = "/" + path.strip("/")
    logger.info("Request %s %s %s", method, path, params)

    try:
        if method == "GET" and path == "/health":
            return 200, {"status": "ok", "time": now_iso()}
        if method == "GET" and path == "/insights":
            return 200, list_insights(params)
        if method == "GET" and path == "/students":
            return 200, list_students()
        if method == "GET" and path.startswith("/students/") and path.count("/") == 2:
            return get_student(path.split("/")[2])
        if method == "POST" and path.startswith("/students/") and path.endswith("/case") and path.count("/") == 3:
            return update_case(path.split("/")[2], body_text)
        if method == "GET" and path == "/stats":
            return 200, get_stats()
        if method == "POST" and path == "/ingest":
            return ingest(body_text)
        if method == "POST" and path == "/admin/reset-demo":
            return reset_demo(headers.get("x-admin-token", ""))
        return 404, {"error": f"Unknown route: {method} {path}"}
    except Exception:  # noqa: BLE001
        logger.exception("Unhandled error for %s %s", method, path)
        return 500, {"error": "Internal server error. Check the retention-api logs in Google Cloud."}


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
    cases = load_cases()
    students = [
        attach_case(summarise_student(sid, records), records, cases.get(sid))
        for sid, records in group_by_student(scan_all()).items()
    ]
    students.sort(key=lambda s: (s["current_risk_score"], s["latest_event_time"]), reverse=True)
    return {"count": len(students), "items": students}




def get_student(student_id):
    student_id = student_id.strip().upper()
    records = [i for i in scan_all() if i.get("student_id") == student_id]
    if not records:
        return 404, {"error": f"No records for student {student_id}"}
    case = load_cases().get(student_id)
    profile = attach_case(summarise_student(student_id, records), records, case)
    profile["case_history"] = list(reversed((case or {}).get("history") or []))  # newest first
    profile["timeline"] = sorted(records, key=lambda r: r.get("event_time", ""))
    return 200, profile


def get_stats():
    items = scan_all()
    cases = load_cases()
    with_records = [(sid, recs, summarise_student(sid, recs)) for sid, recs in group_by_student(items).items()]
    students = [s for _, _, s in with_records]

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
        # High / critical students nobody has contacted yet (or who wrote again after being contacted).
        "awaiting_follow_up": sum(
            1
            for s in (attach_case(s, recs, cases.get(sid)) for sid, recs, s in with_records)
            if s["current_risk_level"] in ("HIGH", "CRITICAL") and s["needs_follow_up"]
        ),
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




def ingest(body_text):
    """Accept a raw message from the dashboard and drop it into the raw bucket under incoming/live/.

    The Cloud Storage -> Eventarc -> processor pipeline then picks it up exactly like any other file,
    so the frontend can poll GET /insights a few seconds later to see the result.
    """
    if not RAW_BUCKET:
        return 500, {"error": "RAW_BUCKET environment variable is not set"}
    try:
        body = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        return 400, {"error": "Body must be JSON, e.g. {\"student_id\": \"TP012345\", \"text\": \"...\"}"}
    if not isinstance(body, dict):
        return 400, {"error": "Body must be a JSON object"}

    text = str(body.get("text") or "").strip()
    if not text:
        return 400, {"error": "Field 'text' is required"}
    if len(text) > MAX_INGEST_CHARS:
        return 400, {"error": f"Field 'text' must be at most {MAX_INGEST_CHARS} characters"}

    document = {
        "channel": str(body.get("source") or "dashboard_demo")[:50],
        "student_id": str(body.get("student_id") or "")[:20],
        "student_name": str(body.get("student_name") or "")[:100],
        "submitted_at": now_iso(),
        "message": text,
    }
    key = f"{INGEST_PREFIX}{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}.json"
    storage_client().bucket(RAW_BUCKET).blob(key).upload_from_string(
        json.dumps(document, ensure_ascii=False), content_type="application/json"
    )
    # "s3_key" repeats "object_key" under the name the dashboard already uses.
    return 202, {"status": "queued", "object_key": key, "s3_key": key, "hint": "Poll GET /insights in ~10 seconds"}


def update_case(student_id, body_text):
    """Record a counsellor's follow-up for one student: status (OPEN / CONTACTED / RESOLVED) and a short note.

    Stored in its own Firestore collection (one document per student), so the AI results are never
    changed by a counsellor and the risk score always stays the AI's own assessment.
    """
    student_id = student_id.strip().upper()
    try:
        body = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        return 400, {"error": "Body must be JSON, e.g. {\"status\": \"CONTACTED\", \"note\": \"Called, meeting Friday\"}"}
    if not isinstance(body, dict):
        return 400, {"error": "Body must be a JSON object"}

    status = str(body.get("status") or "").strip().upper()
    if status not in CASE_STATUSES:
        return 400, {"error": f"Field 'status' must be one of {', '.join(CASE_STATUSES)}"}
    note = str(body.get("note") or "").strip()
    if len(note) > MAX_NOTE_CHARS:
        return 400, {"error": f"Field 'note' must be at most {MAX_NOTE_CHARS} characters"}
    if not any(i.get("student_id") == student_id for i in scan_all()):
        return 404, {"error": f"No records for student {student_id}"}

    previous = load_cases().get(student_id) or {}
    stamp = now_iso()
    history = (previous.get("history") or []) + [{"status": status, "note": note, "at": stamp}]
    case = {
        "student_id": student_id,
        "status": status,
        "note": note,
        "updated_at": stamp,
        "history": history[-MAX_CASE_HISTORY:],
    }
    firestore_client().collection(CASES_COLLECTION).document(student_id).set(case)
    logger.info("Case %s -> %s", student_id, status)
    return 200, case


def reset_demo(token):
    """Delete messages sent through the Live demo page and all follow-up records, keeping the original data.

    Protected by a secret token (stored in Secret Manager as admin-token), because the API is public.
    """
    expected = os.environ.get("ADMIN_TOKEN", "").strip()
    if not expected or not hmac.compare_digest(token.strip().encode(), expected.encode()):
        return 403, {"error": "Missing or wrong X-Admin-Token header"}
    collection = firestore_client().collection(FIRESTORE_COLLECTION)
    deleted = 0
    for snapshot in collection.stream():
        item = snapshot.to_dict() or {}
        if item.get("is_live") or INGEST_PREFIX in str(item.get("source_uri") or item.get("s3_uri") or ""):
            collection.document(snapshot.id).delete()
            deleted += 1
    remaining = sum(1 for _ in collection.stream())

    cases = firestore_client().collection(CASES_COLLECTION)
    cases_cleared = 0
    for snapshot in cases.stream():
        cases.document(snapshot.id).delete()
        cases_cleared += 1
    logger.info("Demo reset: deleted %d live message(s), %d remain, %d case(s) cleared", deleted, remaining, cases_cleared)
    return 200, {"deleted": deleted, "remaining": remaining, "cases_cleared": cases_cleared}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def scan_all():
    """Read every analysed message from Firestore."""
    items = []
    for snapshot in firestore_client().collection(FIRESTORE_COLLECTION).stream():
        items.append(snapshot.to_dict() or {})
        if len(items) >= MAX_SCAN_ITEMS:
            break
    return items


def load_cases():
    """Every counsellor follow-up record, keyed by student ID (one small document per student)."""
    return {snap.id: (snap.to_dict() or {}) for snap in firestore_client().collection(CASES_COLLECTION).stream()}


def attach_case(profile, records, case):
    """Add the follow-up fields to a student profile.

    needs_follow_up is True when nobody has acted yet, or when the student sent a new message after
    the last update (so a "Resolved" student who writes in again goes back on the counsellor's list).
    Messages are compared by when they were analysed, so this works the same for live and historical data.
    """
    case = case or {}
    status = case.get("status") or "OPEN"
    updated_at = case.get("updated_at") or ""
    newest = max((r.get("processed_at") or r.get("event_time") or "") for r in records) if records else ""
    new_message = bool(updated_at) and newest > updated_at
    profile.update(
        {
            "case_status": status,
            "case_note": case.get("note") or "",
            "case_updated_at": updated_at,
            "case_new_message": new_message,
            "needs_follow_up": status == "OPEN" or new_message,
        }
    )
    return profile


def group_by_student(items):
    groups = defaultdict(list)
    for item in items:
        groups[item.get("student_id", "UNKNOWN")].append(item)
    return groups


def summarise_student(student_id, records):
    """Turn many signals into one profile.

    current_risk_* = the student's MOST RECENT signal, so the dashboard reflects where they are
    now: a student who reached out and got help drops down the list.
    Safety rule: a self-harm signal never fades on its own. If any message was flagged, the student
    stays CRITICAL / IMMEDIATE until a counsellor follows up.
    peak_risk_* = the highest-risk signal ever, kept for context.
    trend compares the latest signal with the one before it.
    """
    records = sorted(records, key=lambda r: r.get("event_time", ""))
    peak = max(records, key=lambda r: (r.get("risk_score", 0), URGENCY_ORDER.get(r.get("urgency"), 0)))
    latest = records[-1]
    latest_score = latest.get("risk_score", 0)
    flagged = [r for r in records if r.get("self_harm_indicator")]

    if flagged:
        driver = max(flagged + [latest], key=lambda r: r.get("risk_score", 0))
        current_score = max(driver.get("risk_score", 0), 90)
        current_level = "CRITICAL"
        current_urgency = "IMMEDIATE"
    else:
        driver = latest
        current_score = latest_score
        current_level = latest.get("risk_level", "LOW")
        current_urgency = latest.get("urgency", "ROUTINE")

    if len(records) < 2:
        trend = "NEW"
    else:
        previous_score = records[-2].get("risk_score", 0)
        if latest_score - previous_score >= 10:
            trend = "RISING"
        elif previous_score - latest_score >= 10:
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
        "current_risk_score": current_score,
        "current_risk_level": current_level,
        "latest_risk_score": latest_score,
        "peak_risk_score": peak.get("risk_score", 0),
        "peak_risk_level": peak.get("risk_level", "LOW"),
        "average_risk_score": round(sum(r.get("risk_score", 0) for r in records) / len(records), 1),
        "trend": trend,
        "top_stressors": [s for s, _ in stressor_counts.most_common(3)],
        "self_harm_flag": bool(flagged),
        # Field name kept so the dashboard doesn't need changes; it now holds the CURRENT urgency.
        "highest_urgency": current_urgency,
        "recommended_action": driver.get("recommended_action", ""),
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




def to_int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))




def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
