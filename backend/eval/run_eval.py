"""
Accuracy test for the AI step (Role B).

Runs every file listed in eval/answer_key.json through the SAME Gemini prompt,
schema and clean-up code the cloud processor uses (src/processor/app.py), then
compares the AI's answers with our hand-made labels.

No AWS account or boto3 needed - only a Gemini API key.

Usage (from the backend folder):

    Windows PowerShell:
        $env:GEMINI_API_KEY="paste-your-key-here"
        python eval/run_eval.py

    macOS / Linux:
        export GEMINI_API_KEY="paste-your-key-here"
        python3 eval/run_eval.py

Options:
    --delay 5        seconds to wait between Gemini calls (free tier has a per-minute limit)
    --only x0        only run cases whose file path contains this text
    --runs 3         run every case several times to check the AI is consistent
    --prompt FILE    test a different copy of the processor (e.g. a proposed new prompt)

Results are printed and also saved to eval/results/latest.json for the pitch deck.
"""

import argparse
import json
import os
import sys
import time
import types
from collections import Counter
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ANSWER_KEY = BACKEND_DIR / "eval" / "answer_key.json"
RESULTS_DIR = BACKEND_DIR / "eval" / "results"
LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
PROCESSOR_FILE = BACKEND_DIR / "src" / "processor" / "app.py"


def load_processor():
    """Import the real processor code. boto3 is replaced by a stand-in if it isn't installed."""
    try:
        import boto3  # noqa: F401
    except ImportError:
        stub = types.ModuleType("boto3")
        stub.client = lambda *args, **kwargs: None
        stub.resource = lambda *args, **kwargs: None
        sys.modules["boto3"] = stub
    import importlib.util

    path = Path(PROCESSOR_FILE)
    spec = importlib.util.spec_from_file_location("processor_app", path)
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    return app


def check_case(case, result):
    """Compare one AI result with the answer key. Returns a dict of pass/fail checks."""
    checks = {
        "level_ok": result["risk_level"] in case["acceptable_levels"],
        "level_exact": result["risk_level"] == case["expected_level"],
        "stressor_ok": result["primary_stressor"] in case["acceptable_stressors"],
        "id_ok": result["student_id"] == (case["student_id"] or "UNKNOWN"),
    }
    if case.get("self_harm") is None:
        checks["safety_ok"] = True
    else:
        checks["safety_ok"] = result["self_harm_indicator"] == case["self_harm"]
    return checks


def pct(part, whole):
    return f"{(100 * part / whole):.0f}%" if whole else "n/a"


def main():
    parser = argparse.ArgumentParser(description="Accuracy test for the Gemini risk analysis")
    parser.add_argument("--delay", type=float, default=5.0, help="seconds between Gemini calls (default 5)")
    parser.add_argument("--only", default="", help="only run cases whose file path contains this text")
    parser.add_argument("--runs", type=int, default=1, help="how many times to run each case (default 1)")
    parser.add_argument("--prompt", default="", help="path to a different processor app.py to test")
    parser.add_argument("--save-as", default="latest", help="name for the results file (default latest)")
    args = parser.parse_args()

    global PROCESSOR_FILE
    if args.prompt:
        PROCESSOR_FILE = Path(args.prompt).resolve()

    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. See the instructions at the top of this file.")
        sys.exit(1)

    processor = load_processor()
    cases = [c for c in json.loads(ANSWER_KEY.read_text(encoding="utf-8"))["cases"] if args.only in c["file"]]
    if not cases:
        print("No cases matched.")
        sys.exit(1)

    print(f"Model: {processor.GEMINI_MODEL}")
    print(f"Prompt from: {PROCESSOR_FILE}")
    print(f"Cases: {len(cases)} x {args.runs} run(s)\n")
    print(f"{'file':38} {'expected':9} {'got':9} {'score':>5}  {'stressor':22} checks")
    print("-" * 100)

    rows = []
    for run in range(args.runs):
        for case in cases:
            path = BACKEND_DIR / case["file"]
            if not path.exists():
                print(f"MISSING FILE: {case['file']} (run: python mock_data/generate_mock_data.py)")
                continue
            message = processor.split_into_messages(path.read_text(encoding="utf-8"))[0]
            try:
                raw = processor.call_gemini(message[: processor.MAX_TEXT_CHARS])
                result = processor.normalise_analysis(raw)
            except Exception as error:  # noqa: BLE001 - keep going, report at the end
                if any(f"HTTP {code}" in str(error) for code in (400, 401, 403)) and "key" in str(error).lower():
                    print("\nSTOPPED: Gemini rejected the API key, so every case would fail.")
                    print("Check the key: in PowerShell run  $env:GEMINI_API_KEY.Substring(0,4)  (should print AIza)")
                    print("and  $env:GEMINI_API_KEY.Length  (should print 39). Then set it again and re-run.")
                    sys.exit(1)
                print(f"{Path(case['file']).name:38} ERROR: {error}")
                rows.append({"file": case["file"], "run": run + 1, "error": str(error)})
                time.sleep(args.delay)
                continue

            checks = check_case(case, result)
            flags = []
            if not checks["level_ok"]:
                flags.append("LEVEL")
            if not checks["stressor_ok"]:
                flags.append("STRESSOR")
            if not checks["id_ok"]:
                flags.append("ID")
            if not checks["safety_ok"]:
                flags.append("SAFETY")
            status = "ok" if not flags else "WRONG: " + ",".join(flags)
            print(
                f"{Path(case['file']).name:38} {case['expected_level']:9} {result['risk_level']:9} "
                f"{result['risk_score']:>5}  {result['primary_stressor']:22} {status}"
            )
            rows.append({"file": case["file"], "run": run + 1, "note": case["note"],
                         "expected_level": case["expected_level"], "result": result, "checks": checks})
            time.sleep(args.delay)

    scored = [r for r in rows if "checks" in r]
    errors = [r for r in rows if "error" in r]
    n = len(scored)

    def count(key):
        return sum(1 for r in scored if r["checks"][key])

    print("\n" + "=" * 100)
    print(f"Risk level acceptable : {count('level_ok')}/{n}  ({pct(count('level_ok'), n)})")
    print(f"Risk level exact match: {count('level_exact')}/{n}  ({pct(count('level_exact'), n)})")
    print(f"Main stressor correct : {count('stressor_ok')}/{n}  ({pct(count('stressor_ok'), n)})")
    print(f"Student ID extracted  : {count('id_ok')}/{n}  ({pct(count('id_ok'), n)})")
    print(f"Safety flag correct   : {count('safety_ok')}/{n}  ({pct(count('safety_ok'), n)})")
    if errors:
        print(f"Errors (not scored)   : {len(errors)}")

    # Off by more than one level is the serious kind of mistake (e.g. CRITICAL called LOW)
    big_misses = [r for r in scored
                  if abs(LEVELS.index(r["expected_level"]) - LEVELS.index(r["result"]["risk_level"])) >= 2]
    print(f"Off by 2+ levels      : {len(big_misses)}")
    for r in big_misses:
        print(f"    {r['file']}: expected {r['expected_level']}, got {r['result']['risk_level']}")

    # Confusion table: rows = our label, columns = AI's answer
    table = Counter((r["expected_level"], r["result"]["risk_level"]) for r in scored)
    print("\nExpected (rows) vs AI (columns):")
    print(" " * 10 + "".join(f"{lvl:>10}" for lvl in LEVELS))
    for exp in LEVELS:
        print(f"{exp:10}" + "".join(f"{table[(exp, got)]:>10}" for got in LEVELS))

    # Ranking check: the dashboard shows each student's WORST score, so students in different
    # situations should get clearly different numbers. We compare every pair of students whose
    # expected worst level differs and check the AI put them in the right order.
    by_student = {}
    for r in scored:
        case = next(c for c in cases if c["file"] == r["file"])
        sid = case["student_id"] or r["file"]
        entry = by_student.setdefault(sid, {"expected": "LOW", "worst_by_run": {}})
        if LEVELS.index(case["expected_level"]) > LEVELS.index(entry["expected"]):
            entry["expected"] = case["expected_level"]
        run_worst = entry["worst_by_run"]
        run_worst[r["run"]] = max(run_worst.get(r["run"], 0), r["result"]["risk_score"])
    students = []
    for sid, entry in by_student.items():
        worst = list(entry["worst_by_run"].values())
        students.append((sid, entry["expected"], sum(worst) / len(worst)))
    students.sort(key=lambda s: s[2], reverse=True)

    print("\nStudent ranking (worst score per student, as on the dashboard):")
    for sid, expected, score in students:
        print(f"    {sid:44} expected {expected:9} score {score:5.1f}")
    right = tied = wrong = 0
    for i, a in enumerate(students):
        for b in students[i + 1:]:
            la, lb = LEVELS.index(a[1]), LEVELS.index(b[1])
            if la == lb:
                continue
            high, low = (a, b) if la > lb else (b, a)
            if abs(high[2] - low[2]) < 1:
                tied += 1
            elif high[2] > low[2]:
                right += 1
            else:
                wrong += 1
    pairs = right + tied + wrong
    distinct = len({round(s[2]) for s in students})
    print(f"Pairs in the right order: {right}/{pairs} ({pct(right, pairs)})   tied: {tied}   wrong way round: {wrong}")
    print(f"Different scores among {len(students)} students: {distinct}")

    if args.runs > 1:
        unstable = []
        for case in cases:
            levels = {r["result"]["risk_level"] for r in scored if r["file"] == case["file"]}
            if len(levels) > 1:
                unstable.append(f"{case['file']}: {sorted(levels)}")
        print(f"\nCases that changed level between runs: {len(unstable)}")
        for line in unstable:
            print("    " + line)

    RESULTS_DIR.mkdir(exist_ok=True)
    summary = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "model": processor.GEMINI_MODEL,
        "prompt_file": str(PROCESSOR_FILE),
        "cases": len(cases),
        "runs": args.runs,
        "scored": n,
        "errors": len(errors),
        "level_acceptable": count("level_ok"),
        "level_exact": count("level_exact"),
        "stressor_correct": count("stressor_ok"),
        "student_id_correct": count("id_ok"),
        "safety_correct": count("safety_ok"),
        "off_by_two_or_more": len(big_misses),
        "ranking_pairs_right": right,
        "ranking_pairs_tied": tied,
        "ranking_pairs_wrong": wrong,
        "distinct_student_scores": distinct,
    }
    out = RESULTS_DIR / f"{args.save_as}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved full results to {out}")


if __name__ == "__main__":
    main()
