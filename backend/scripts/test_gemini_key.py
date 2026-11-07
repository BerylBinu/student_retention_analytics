"""
Check your Gemini API key BEFORE deploying, and preview what the AI returns.

It runs the exact same Gemini call the cloud processor uses, on one of the mock files,
and prints the structured result. No AWS account or boto3 needed.

Usage (from the backend folder):

    Windows PowerShell:
        $env:GEMINI_API_KEY="paste-your-key-here"
        python scripts/test_gemini_key.py

    macOS / Linux:
        export GEMINI_API_KEY="paste-your-key-here"
        python3 scripts/test_gemini_key.py

    Optional: test a different file or model
        python scripts/test_gemini_key.py mock_data/samples/live_demo/priya_crisis.json
        (set GEMINI_MODEL=gemini-3.8-flash the same way as the key to try another model)
"""

import json
import os
import sys
import types
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FILE = BACKEND_DIR / "mock_data" / "samples" / "historical" / "02_email.txt"


def load_processor():
    # The processor imports boto3 (AWS SDK). It's not needed for this test, so if it
    # isn't installed we put in a harmless stand-in.
    try:
        import boto3  # noqa: F401
    except ImportError:
        stub = types.ModuleType("boto3")
        stub.client = lambda *args, **kwargs: None
        stub.resource = lambda *args, **kwargs: None
        sys.modules["boto3"] = stub
    sys.path.insert(0, str(BACKEND_DIR / "src" / "processor"))
    import app  # noqa: E402

    return app


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. See the instructions at the top of this file.")
        sys.exit(1)

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE
    if not path.exists():
        print(f"File not found: {path}")
        print("Did you run:  python mock_data/generate_mock_data.py  first?")
        sys.exit(1)

    processor = load_processor()
    text = path.read_text(encoding="utf-8")
    messages = processor.split_into_messages(text)
    print(f"Model: {processor.GEMINI_MODEL}")
    print(f"File:  {path}  ({len(messages)} message(s))\n")

    for message in messages:
        raw = processor.call_gemini(message[: processor.MAX_TEXT_CHARS])
        clean = processor.normalise_analysis(raw)
        print(json.dumps(clean, indent=2, ensure_ascii=False))

    print("\nSuccess! Your key works. Next: store it in AWS with the 'aws ssm put-parameter' command in the README.")


if __name__ == "__main__":
    main()
