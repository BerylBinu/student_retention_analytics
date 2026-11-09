"""
Offline tests: no AWS account, no Gemini key, no internet needed.

AWS and Gemini are replaced with small fakes so we can check the pipeline logic:
S3 event handling, message splitting, safety rules, DynamoDB saving and the API aggregation.

Run from the backend folder:
    python -m unittest discover -s tests -v
"""

import importlib.util
import json
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Fakes for boto3
# ---------------------------------------------------------------------------
class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        for value in Item.values():
            assert not isinstance(value, float), "floats must be converted to Decimal"
        self.items[Item["record_id"]] = Item

    def scan(self, **kwargs):
        return {"Items": list(self.items.values())}


class FakeDynamo:
    def __init__(self):
        self.table = FakeTable()

    def Table(self, name):
        return self.table


class FakeBody:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


class FakeS3:
    def __init__(self):
        self.objects = {}

    def get_object(self, Bucket, Key):
        return {"Body": FakeBody(self.objects[(Bucket, Key)])}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.objects[(Bucket, Key)] = Body if isinstance(Body, bytes) else Body.encode()


FAKE_S3 = FakeS3()
FAKE_DYNAMO = FakeDynamo()

boto3_stub = types.ModuleType("boto3")
boto3_stub.client = lambda service, *a, **k: FAKE_S3 if service == "s3" else None
boto3_stub.resource = lambda service, *a, **k: FAKE_DYNAMO
sys.modules["boto3"] = boto3_stub


def load(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, BACKEND_DIR / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


processor = load("processor_app", "src/processor/app.py")
processor.MIN_SECONDS_PER_CALL = 0  # no rate-limit pacing in tests
api = load("api_app", "src/api/app.py")
api.DATA_BUCKET = "test-bucket"


def fake_gemini_answer(student_id, score, stressor, self_harm=False, timestamp="2026-10-13T15:41:00Z"):
    return {
        "student_id": student_id,
        "student_name": "Test Student",
        "source_system": "EMAIL",
        "message_timestamp": timestamp,
        "risk_score": score,
        "risk_level": "LOW",  # deliberately wrong: the code must fix it from the score
        "primary_stressor": stressor,
        "secondary_stressors": ["ACADEMIC_PRESSURE", stressor, "NOT_A_REAL_STRESSOR"],
        "sentiment": "NEGATIVE",
        "summary": "Student is worried.",
        "evidence": ["a", "b", "c", "d"],
        "recommended_action": "Reach out.",
        "urgency": "ROUTINE",
        "self_harm_indicator": self_harm,
    }


def s3_event_message(bucket, key, size=100):
    body = {"Records": [{"eventTime": "2026-10-13T16:00:00.000Z",
                         "s3": {"bucket": {"name": bucket}, "object": {"key": key, "size": size}}}]}
    return {"messageId": f"msg-{key}", "body": json.dumps(body)}


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        FAKE_DYNAMO.table.items.clear()
        FAKE_S3.objects.clear()

    def test_split_formats(self):
        self.assertEqual(processor.split_into_messages("From: x\n\nhello"), ["From: x\n\nhello"])
        self.assertEqual(len(processor.split_into_messages('[{"a":1},{"b":2}]')), 2)
        self.assertEqual(len(processor.split_into_messages('{"a":1}')), 1)
        self.assertEqual(processor.split_into_messages("   "), [])

    def test_normalise_fixes_level_and_filters(self):
        clean = processor.normalise_analysis(fake_gemini_answer("tp071234", 72, "FINANCIAL"))
        self.assertEqual(clean["student_id"], "TP071234")
        self.assertEqual(clean["risk_level"], "HIGH")
        self.assertEqual(clean["secondary_stressors"], ["ACADEMIC_PRESSURE"])
        self.assertEqual(len(clean["evidence"]), 3)

    def test_self_harm_always_escalates(self):
        clean = processor.normalise_analysis(fake_gemini_answer("TP070455", 40, "BURNOUT_MENTAL_HEALTH", self_harm=True))
        self.assertEqual(clean["risk_score"], 90)
        self.assertEqual(clean["risk_level"], "CRITICAL")
        self.assertEqual(clean["urgency"], "IMMEDIATE")

    def test_bad_values_are_safe(self):
        clean = processor.normalise_analysis({"risk_score": "abc", "primary_stressor": "???"})
        self.assertEqual(clean["risk_score"], 0)
        self.assertEqual(clean["primary_stressor"], "NONE")
        self.assertEqual(clean["student_id"], "UNKNOWN")

    def test_timestamps(self):
        self.assertEqual(processor.normalise_timestamp("1760000000"), "2025-10-09T08:53:20Z")
        self.assertEqual(processor.normalise_timestamp("2026-10-13T23:41:00+08:00"), "2026-10-13T15:41:00Z")
        self.assertEqual(processor.normalise_timestamp("not a date"), "")

    def test_rate_limit_parsing(self):
        detail = '{"error": {"code": 429, "message": "Please retry in 58.491880011s.", "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "58s"}]}}'
        self.assertEqual(processor.retry_delay_seconds(detail), 58.0)
        self.assertAlmostEqual(processor.retry_delay_seconds("Please retry in 12.5s."), 12.5)
        self.assertEqual(processor.retry_delay_seconds("no hint"), 30.0)
        self.assertFalse(processor.is_daily_quota("requests per minute limit exceeded"))
        self.assertTrue(processor.is_daily_quota('"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"'))

    def test_parse_gemini_response(self):
        body = {"candidates": [{"content": {"parts": [{"text": '{"risk_score": 5}'}]}}]}
        self.assertEqual(processor.parse_gemini_response(body), {"risk_score": 5})
        fenced = {"candidates": [{"content": {"parts": [{"text": '```json\n{"risk_score": 7}\n```'}]}}]}
        self.assertEqual(processor.parse_gemini_response(fenced), {"risk_score": 7})
        with self.assertRaises(RuntimeError):
            processor.parse_gemini_response({"promptFeedback": {"blockReason": "SAFETY"}})

    def test_full_pipeline_with_fake_gemini(self):
        FAKE_S3.objects[("test-bucket", "incoming/my file.txt")] = b"From: a\n\nI cannot pay my fees"
        processor.call_gemini = lambda text: fake_gemini_answer("TP071234", 65, "FINANCIAL")

        event = {"Records": [
            s3_event_message("test-bucket", "incoming/my+file.txt"),        # URL-encoded key
            s3_event_message("test-bucket", "incoming/", size=0),           # folder placeholder
            {"messageId": "test", "body": json.dumps({"Event": "s3:TestEvent"})},
        ]}
        result = processor.lambda_handler(event, None)
        self.assertEqual(result, {"batchItemFailures": []})
        self.assertEqual(len(FAKE_DYNAMO.table.items), 1)
        item = next(iter(FAKE_DYNAMO.table.items.values()))
        self.assertEqual(item["risk_level"], "HIGH")
        self.assertEqual(item["event_date"], "2026-10-13")
        self.assertTrue(any(k.startswith("curated/2026-10-13/") for (_, k) in FAKE_S3.objects))

        # Re-processing the same file must not create a duplicate row
        processor.lambda_handler({"Records": [s3_event_message("test-bucket", "incoming/my+file.txt")]}, None)
        self.assertEqual(len(FAKE_DYNAMO.table.items), 1)

    def test_failure_is_reported_for_retry(self):
        FAKE_S3.objects[("test-bucket", "incoming/x.json")] = b'{"a": 1}'

        def broken(text):
            raise RuntimeError("Gemini HTTP 429")

        processor.call_gemini = broken
        result = processor.lambda_handler({"Records": [s3_event_message("test-bucket", "incoming/x.json")]}, None)
        self.assertEqual(result["batchItemFailures"], [{"itemIdentifier": "msg-incoming/x.json"}])


class ApiTests(unittest.TestCase):
    def setUp(self):
        FAKE_DYNAMO.table.items.clear()
        rows = [
            ("r1", "TP071234", "Aisyah", 35, "MEDIUM", "FINANCIAL", "2026-10-02T02:15:00Z", False),
            ("r2", "TP071234", "Aisyah", 70, "HIGH", "FINANCIAL", "2026-10-13T15:41:00Z", False),
            ("r3", "TP070455", "Priya", 90, "CRITICAL", "BURNOUT_MENTAL_HEALTH", "2026-10-19T19:20:00Z", True),
            ("r4", "TP071877", "Arjun", 5, "LOW", "NONE", "2026-10-08T01:00:00Z", False),
        ]
        for rid, sid, name, score, level, stressor, ts, harm in rows:
            FAKE_DYNAMO.table.items[rid] = {
                "record_id": rid, "student_id": sid, "student_name": name, "risk_score": Decimal(score),
                "risk_level": level, "primary_stressor": stressor, "secondary_stressors": [],
                "event_time": ts, "event_date": ts[:10], "self_harm_indicator": harm,
                "urgency": "IMMEDIATE" if harm else "ROUTINE", "source_system": "EMAIL",
                "recommended_action": "Reach out", "summary": "s",
            }

    def call(self, route, **extra):
        response = api.lambda_handler({"routeKey": route, **extra}, None)
        return response["statusCode"], json.loads(response["body"])

    def test_students_sorted_and_trend(self):
        status, body = self.call("GET /students")
        self.assertEqual(status, 200)
        self.assertEqual([s["student_id"] for s in body["items"]], ["TP070455", "TP071234", "TP071877"])
        aisyah = body["items"][1]
        self.assertEqual(aisyah["trend"], "RISING")
        self.assertEqual(aisyah["current_risk_level"], "HIGH")
        self.assertIsInstance(aisyah["current_risk_score"], int)

    def add_row(self, rid, sid, score, level, ts, harm=False):
        FAKE_DYNAMO.table.items[rid] = {
            "record_id": rid, "student_id": sid, "student_name": sid, "risk_score": Decimal(score),
            "risk_level": level, "primary_stressor": "NONE", "secondary_stressors": [], "event_time": ts,
            "event_date": ts[:10], "self_harm_indicator": harm, "urgency": "IMMEDIATE" if harm else "ROUTINE",
            "source_system": "EMAIL", "recommended_action": f"action-{rid}", "summary": "s",
        }

    def test_recovery_lowers_current_risk(self):
        self.add_row("c1", "TP072210", 82, "CRITICAL", "2026-10-21T13:30:00Z")
        self.add_row("c2", "TP072210", 2, "LOW", "2026-11-05T10:00:00Z")
        status, body = self.call("GET /students/{student_id}", pathParameters={"student_id": "TP072210"})
        self.assertEqual(body["current_risk_level"], "LOW")
        self.assertEqual(body["current_risk_score"], 2)
        self.assertEqual(body["peak_risk_score"], 82)
        self.assertEqual(body["trend"], "FALLING")
        self.assertEqual(body["recommended_action"], "action-c2")

    def test_self_harm_never_fades(self):
        self.add_row("p1", "TP070999", 95, "CRITICAL", "2026-11-01T00:00:00Z", harm=True)
        self.add_row("p2", "TP070999", 5, "LOW", "2026-11-02T00:00:00Z")
        status, body = self.call("GET /students/{student_id}", pathParameters={"student_id": "TP070999"})
        self.assertEqual(body["current_risk_level"], "CRITICAL")
        self.assertEqual(body["current_risk_score"], 95)
        self.assertEqual(body["highest_urgency"], "IMMEDIATE")
        self.assertEqual(body["recommended_action"], "action-p1")
        self.assertTrue(body["self_harm_flag"])

    def test_insights_filter(self):
        status, body = self.call("GET /insights", queryStringParameters={"risk_level": "high,critical"})
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["items"][0]["record_id"], "r3")  # newest first

    def test_stats(self):
        status, body = self.call("GET /stats")
        self.assertEqual(body["total_students"], 3)
        self.assertEqual(body["students_needing_attention"], 2)
        self.assertEqual(body["self_harm_alerts"], 1)
        self.assertEqual([x["level"] for x in body["signals_by_risk_level"]], ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
        self.assertNotIn("NONE", [x["stressor"] for x in body["signals_by_stressor"]])

    def test_student_detail_and_404(self):
        status, body = self.call("GET /students/{student_id}", pathParameters={"student_id": "tp071234"})
        self.assertEqual(status, 200)
        self.assertEqual(len(body["timeline"]), 2)
        status, _ = self.call("GET /students/{student_id}", pathParameters={"student_id": "TP000000"})
        self.assertEqual(status, 404)

    def test_ingest(self):
        status, body = self.call("POST /ingest", body=json.dumps({"student_id": "TP1", "text": "help"}))
        self.assertEqual(status, 202)
        self.assertTrue(body["s3_key"].startswith("incoming/live/"))
        status, _ = self.call("POST /ingest", body=json.dumps({"text": ""}))
        self.assertEqual(status, 400)
        status, _ = self.call("POST /ingest", body="not json")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
