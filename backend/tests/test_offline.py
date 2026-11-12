"""
Offline tests: no Google Cloud project, no Gemini key, no internet needed.

Cloud Storage, Firestore and Gemini are replaced with small fakes so we can check the pipeline
logic: storage event handling, message splitting, safety rules, retry decisions, saving, the API
aggregation, the demo reset, and the HTTP/CORS layer.

Run from the backend folder:
    python -m unittest discover -s tests -v
"""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Fakes for Cloud Storage and Firestore
# ---------------------------------------------------------------------------
class FakeBlob:
    def __init__(self, store, bucket, name):
        self.store, self.bucket, self.name = store, bucket, name

    def download_as_bytes(self):
        return self.store.objects[(self.bucket, self.name)]

    def upload_from_string(self, data, content_type=None):
        self.store.objects[(self.bucket, self.name)] = data.encode() if isinstance(data, str) else data


class FakeBucket:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def blob(self, name):
        return FakeBlob(self.store, self.name, name)


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def bucket(self, name):
        return FakeBucket(self, name)


class FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id, self._data = doc_id, data

    def to_dict(self):
        return dict(self._data)


class FakeDocRef:
    def __init__(self, docs, doc_id):
        self.docs, self.doc_id = docs, doc_id

    def set(self, data):
        json.dumps(data)  # Firestore only stores plain JSON-like values
        self.docs[self.doc_id] = dict(data)

    def delete(self):
        self.docs.pop(self.doc_id, None)


class FakeCollection:
    def __init__(self):
        self.docs = {}

    def document(self, doc_id):
        return FakeDocRef(self.docs, doc_id)

    def stream(self):
        return [FakeSnapshot(k, v) for k, v in list(self.docs.items())]


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection())


FAKE_STORAGE = FakeStorage()
FAKE_DB = FakeFirestore()


def docs():
    return FAKE_DB.collection("insights").docs


def load(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, BACKEND_DIR / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


processor = load("processor_app", "src/processor/app.py")
processor.MIN_SECONDS_PER_CALL = 0  # no rate-limit pacing in tests
processor.CURATED_BUCKET = "curated-bucket"
processor._storage_client = FAKE_STORAGE
processor._firestore_client = FAKE_DB
REAL_CALL_GEMINI = processor.call_gemini

api = load("api_app", "src/api/app.py")
api.RAW_BUCKET = "raw-bucket"
api._storage_client = FAKE_STORAGE
api._firestore_client = FAKE_DB


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


def storage_event(name, size=100, bucket="raw-bucket"):
    return {"bucket": bucket, "name": name, "size": str(size), "timeCreated": "2026-10-13T16:00:00.000Z"}


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        docs().clear()
        FAKE_STORAGE.objects.clear()
        processor.call_gemini = REAL_CALL_GEMINI

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
        FAKE_STORAGE.objects[("raw-bucket", "incoming/my file.txt")] = b"From: a\n\nI cannot pay my fees"
        processor.call_gemini = lambda text: fake_gemini_answer("TP071234", 65, "FINANCIAL")

        self.assertEqual(processor.handle_storage_event(storage_event("incoming/my file.txt")), "processed")
        self.assertEqual(len(docs()), 1)
        item = next(iter(docs().values()))
        self.assertEqual(item["risk_level"], "HIGH")
        self.assertEqual(item["event_date"], "2026-10-13")
        self.assertEqual(item["source_uri"], "gs://raw-bucket/incoming/my file.txt")
        self.assertEqual(item["s3_uri"], item["source_uri"])  # dashboard compatibility
        self.assertFalse(item["is_live"])
        self.assertTrue(any(b == "curated-bucket" and k.startswith("curated/2026-10-13/") for (b, k) in FAKE_STORAGE.objects))

        # Re-processing the same file (Google Cloud may deliver an event twice) must not duplicate it
        processor.handle_storage_event(storage_event("incoming/my file.txt"))
        self.assertEqual(len(docs()), 1)

    def test_skips_files_outside_incoming_and_placeholders(self):
        processor.call_gemini = lambda text: self.fail("Gemini must not be called")
        self.assertEqual(processor.handle_storage_event(storage_event("curated/x.json")), "skipped")
        self.assertEqual(processor.handle_storage_event(storage_event("incoming/", size=0)), "skipped")
        self.assertEqual(processor.handle_storage_event(storage_event("incoming/big.json", size=5_000_000)), "skipped")

    def test_live_messages_are_marked(self):
        FAKE_STORAGE.objects[("raw-bucket", "incoming/live/a.json")] = b'{"message": "help"}'
        processor.call_gemini = lambda text: fake_gemini_answer("TP1", 20, "NONE")
        processor.handle_storage_event(storage_event("incoming/live/a.json"))
        self.assertTrue(next(iter(docs().values()))["is_live"])

    def test_transient_failure_is_raised_for_retry(self):
        FAKE_STORAGE.objects[("raw-bucket", "incoming/x.json")] = b'{"a": 1}'

        def busy(text):
            raise processor.TransientError("Gemini HTTP 503")

        processor.call_gemini = busy
        with self.assertRaises(processor.TransientError):
            processor.handle_storage_event(storage_event("incoming/x.json"))

    def test_google_service_errors_are_retried(self):
        class ServiceUnavailable(Exception):
            pass

        FAKE_STORAGE.objects[("raw-bucket", "incoming/x.json")] = b'{"a": 1}'

        def db_down(text):
            raise ServiceUnavailable("firestore busy")

        processor.call_gemini = db_down
        with self.assertRaises(processor.TransientError):
            processor.handle_storage_event(storage_event("incoming/x.json"))

    def test_permanent_failure_is_not_retried(self):
        FAKE_STORAGE.objects[("raw-bucket", "incoming/x.json")] = b'{"a": 1}'

        def bad_key(text):
            raise RuntimeError("Gemini HTTP 400: API key not valid")

        processor.call_gemini = bad_key
        self.assertEqual(processor.handle_storage_event(storage_event("incoming/x.json")), "failed")
        self.assertEqual(len(docs()), 0)


class ApiTests(unittest.TestCase):
    def setUp(self):
        docs().clear()
        FAKE_DB.collection(api.CASES_COLLECTION).docs.clear()
        FAKE_STORAGE.objects.clear()
        api.os.environ["ADMIN_TOKEN"] = "secret-token"
        rows = [
            ("r1", "TP071234", "Aisyah", 35, "MEDIUM", "FINANCIAL", "2026-10-02T02:15:00Z", False),
            ("r2", "TP071234", "Aisyah", 70, "HIGH", "FINANCIAL", "2026-10-13T15:41:00Z", False),
            ("r3", "TP070455", "Priya", 90, "CRITICAL", "BURNOUT_MENTAL_HEALTH", "2026-10-19T19:20:00Z", True),
            ("r4", "TP071877", "Arjun", 5, "LOW", "NONE", "2026-10-08T01:00:00Z", False),
        ]
        for rid, sid, name, score, level, stressor, ts, harm in rows:
            docs()[rid] = {
                "record_id": rid, "student_id": sid, "student_name": name, "risk_score": score,
                "risk_level": level, "primary_stressor": stressor, "secondary_stressors": [],
                "event_time": ts, "event_date": ts[:10], "self_harm_indicator": harm,
                "urgency": "IMMEDIATE" if harm else "ROUTINE", "source_system": "EMAIL",
                "recommended_action": "Reach out", "summary": "s",
                "source_uri": f"gs://raw-bucket/incoming/historical/{rid}.json", "is_live": False,
            }

    def call(self, method, path, params=None, body="", headers=None):
        return api.handle_request(method, path, params or {}, body, headers or {})

    def add_row(self, rid, sid, score, level, ts, harm=False, live=False):
        docs()[rid] = {
            "record_id": rid, "student_id": sid, "student_name": sid, "risk_score": score,
            "risk_level": level, "primary_stressor": "NONE", "secondary_stressors": [], "event_time": ts,
            "event_date": ts[:10], "self_harm_indicator": harm, "urgency": "IMMEDIATE" if harm else "ROUTINE",
            "source_system": "EMAIL", "recommended_action": f"action-{rid}", "summary": "s",
            "source_uri": f"gs://raw-bucket/incoming/{'live' if live else 'historical'}/{rid}.json", "is_live": live,
        }

    def test_students_sorted_and_trend(self):
        status, body = self.call("GET", "/students")
        self.assertEqual(status, 200)
        self.assertEqual([s["student_id"] for s in body["items"]], ["TP070455", "TP071234", "TP071877"])
        aisyah = body["items"][1]
        self.assertEqual(aisyah["trend"], "RISING")
        self.assertEqual(aisyah["current_risk_level"], "HIGH")
        self.assertIsInstance(aisyah["current_risk_score"], int)

    def test_recovery_lowers_current_risk(self):
        self.add_row("c1", "TP072210", 82, "CRITICAL", "2026-10-21T13:30:00Z")
        self.add_row("c2", "TP072210", 2, "LOW", "2026-11-05T10:00:00Z")
        status, body = self.call("GET", "/students/TP072210")
        self.assertEqual(body["current_risk_level"], "LOW")
        self.assertEqual(body["current_risk_score"], 2)
        self.assertEqual(body["peak_risk_score"], 82)
        self.assertEqual(body["trend"], "FALLING")
        self.assertEqual(body["recommended_action"], "action-c2")

    def test_self_harm_never_fades(self):
        self.add_row("p1", "TP070999", 95, "CRITICAL", "2026-11-01T00:00:00Z", harm=True)
        self.add_row("p2", "TP070999", 5, "LOW", "2026-11-02T00:00:00Z")
        status, body = self.call("GET", "/students/TP070999")
        self.assertEqual(body["current_risk_level"], "CRITICAL")
        self.assertEqual(body["current_risk_score"], 95)
        self.assertEqual(body["highest_urgency"], "IMMEDIATE")
        self.assertEqual(body["recommended_action"], "action-p1")
        self.assertTrue(body["self_harm_flag"])

    def test_insights_filter(self):
        status, body = self.call("GET", "/insights", {"risk_level": "high,critical"})
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["items"][0]["record_id"], "r3")  # newest first

    def test_stats(self):
        status, body = self.call("GET", "/stats")
        self.assertEqual(body["total_students"], 3)
        self.assertEqual(body["students_needing_attention"], 2)
        self.assertEqual(body["self_harm_alerts"], 1)
        self.assertEqual([x["level"] for x in body["signals_by_risk_level"]], ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
        self.assertNotIn("NONE", [x["stressor"] for x in body["signals_by_stressor"]])

    def test_student_detail_404_and_paths(self):
        status, body = self.call("GET", "/students/tp071234")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["timeline"]), 2)
        self.assertEqual(self.call("GET", "/students/TP000000")[0], 404)
        self.assertEqual(self.call("GET", "/students/")[0], 200)  # trailing slash = list
        self.assertEqual(self.call("GET", "/nope")[0], 404)
        self.assertEqual(self.call("DELETE", "/students")[0], 404)

    def test_ingest(self):
        status, body = self.call("POST", "/ingest", body=json.dumps({"student_id": "TP1", "text": "help"}))
        self.assertEqual(status, 202)
        self.assertTrue(body["object_key"].startswith("incoming/live/"))
        self.assertEqual(body["s3_key"], body["object_key"])  # dashboard compatibility
        self.assertIn(("raw-bucket", body["object_key"]), FAKE_STORAGE.objects)
        self.assertEqual(self.call("POST", "/ingest", body=json.dumps({"text": ""}))[0], 400)
        self.assertEqual(self.call("POST", "/ingest", body="not json")[0], 400)

    def test_reset_demo_needs_token_and_keeps_original_data(self):
        self.add_row("live1", "TP071234", 85, "CRITICAL", "2026-11-09T10:00:00Z", live=True)
        self.assertEqual(self.call("POST", "/admin/reset-demo")[0], 403)
        self.assertEqual(self.call("POST", "/admin/reset-demo", headers={"X-Admin-Token": "wrong"})[0], 403)
        status, body = self.call("POST", "/admin/reset-demo", headers={"X-Admin-Token": "secret-token"})
        self.assertEqual(status, 200)
        self.assertEqual(body, {"deleted": 1, "remaining": 4, "cases_cleared": 0})
        self.assertNotIn("live1", docs())

    def cases(self):
        return FAKE_DB.collection(api.CASES_COLLECTION).docs

    def test_case_defaults_to_open(self):
        self.cases().clear()
        status, body = self.call("GET", "/students")
        priya = body["items"][0]
        self.assertEqual(priya["case_status"], "OPEN")
        self.assertTrue(priya["needs_follow_up"])
        self.assertEqual(self.call("GET", "/stats")[1]["awaiting_follow_up"], 2)  # Priya (critical) + Aisyah (high)

    def test_update_case_and_history(self):
        self.cases().clear()
        status, body = self.call("POST", "/students/tp070455/case", body=json.dumps({"status": "contacted", "note": "Called, meeting Friday"}))
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "CONTACTED")
        self.call("POST", "/students/TP070455/case", body=json.dumps({"status": "RESOLVED", "note": "Referred to counselling"}))
        detail = self.call("GET", "/students/TP070455")[1]
        self.assertEqual(detail["case_status"], "RESOLVED")
        self.assertEqual(detail["case_note"], "Referred to counselling")
        self.assertFalse(detail["needs_follow_up"])
        self.assertEqual([h["status"] for h in detail["case_history"]], ["RESOLVED", "CONTACTED"])  # newest first
        self.assertEqual(detail["current_risk_level"], "CRITICAL")  # the AI's score is never changed by a counsellor
        self.assertEqual(self.call("GET", "/stats")[1]["awaiting_follow_up"], 1)

    def test_update_case_validation(self):
        self.cases().clear()
        self.assertEqual(self.call("POST", "/students/TP070455/case", body=json.dumps({"status": "DONE"}))[0], 400)
        self.assertEqual(self.call("POST", "/students/TP070455/case", body="not json")[0], 400)
        self.assertEqual(self.call("POST", "/students/TP070455/case", body=json.dumps({"status": "OPEN", "note": "x" * 501}))[0], 400)
        self.assertEqual(self.call("POST", "/students/TP000000/case", body=json.dumps({"status": "OPEN"}))[0], 404)
        self.assertEqual(self.cases(), {})

    def test_new_message_after_follow_up_reopens(self):
        self.cases().clear()
        self.call("POST", "/students/TP071234/case", body=json.dumps({"status": "RESOLVED"}))
        self.assertFalse(self.call("GET", "/students/TP071234")[1]["needs_follow_up"])
        self.add_row("live2", "TP071234", 80, "CRITICAL", "2026-11-12T10:00:00Z", live=True)
        docs()["live2"]["processed_at"] = "2999-01-01T00:00:00Z"  # analysed after the counsellor's update
        detail = self.call("GET", "/students/TP071234")[1]
        self.assertTrue(detail["case_new_message"])
        self.assertTrue(detail["needs_follow_up"])
        self.assertEqual(detail["case_status"], "RESOLVED")

    def test_reset_demo_clears_cases(self):
        self.cases().clear()
        self.call("POST", "/students/TP071234/case", body=json.dumps({"status": "CONTACTED"}))
        status, body = self.call("POST", "/admin/reset-demo", headers={"X-Admin-Token": "secret-token"})
        self.assertEqual(body["cases_cleared"], 1)
        self.assertEqual(self.cases(), {})

    def test_reset_demo_disabled_without_configured_token(self):
        api.os.environ.pop("ADMIN_TOKEN", None)
        self.assertEqual(self.call("POST", "/admin/reset-demo", headers={"X-Admin-Token": ""})[0], 403)


class EntryPointTests(unittest.TestCase):
    """main.py files: the thin layer Google Cloud calls. functions_framework is replaced by a stand-in."""

    @classmethod
    def setUpClass(cls):
        ff = types.ModuleType("functions_framework")
        ff.http = lambda fn: fn
        ff.cloud_event = lambda fn: fn
        sys.modules["functions_framework"] = ff
        sys.modules["app"] = api
        cls.api_main = load("api_main", "src/api/main.py")
        sys.modules["app"] = processor
        cls.processor_main = load("processor_main", "src/processor/main.py")
        del sys.modules["app"]

    def setUp(self):
        docs().clear()

    class Request:
        def __init__(self, method, path, args=None, body=""):
            self.method, self.path, self.body = method, path, body
            self.args = types.SimpleNamespace(to_dict=lambda: dict(args or {}))
            self.headers = {"Content-Type": "application/json"}

        def get_data(self, as_text=False):
            return self.body

    def test_cors_preflight(self):
        body, status, headers = self.api_main.handle_http(self.Request("OPTIONS", "/ingest"))
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertIn("POST", headers["Access-Control-Allow-Methods"])

    def test_health_has_cors_and_json(self):
        body, status, headers = self.api_main.handle_http(self.Request("GET", "/health"))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "ok")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_processor_entry_point(self):
        calls = []
        original = self.processor_main.handle_storage_event
        self.processor_main.handle_storage_event = calls.append
        try:
            self.processor_main.handle_upload(types.SimpleNamespace(data={"name": "incoming/a.json"}))
        finally:
            self.processor_main.handle_storage_event = original
        self.assertEqual(calls, [{"name": "incoming/a.json"}])


if __name__ == "__main__":
    unittest.main()
