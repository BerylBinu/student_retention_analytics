# AI accuracy test (Role B)

Checks whether Gemini's risk scores match what a human would say, using the
**exact same prompt and clean-up code** as the cloud processor (`src/processor/app.py`).

| File | What it is |
|---|---|
| `answer_key.json` | Our hand-made labels for all 23 mock files + 5 tricky extra cases (28 total). Never uploaded to S3. |
| `extra_cases/` | 5 hard cases that keyword tools get wrong: sarcasm, angry-but-fine, Malay/English mix, a prompt-injection attempt, and a routine message full of money words. |
| `run_eval.py` | Runs every case through Gemini and prints the accuracy. |
| `results/latest.json` | Full output of the last run (created when you run it). |

## Run it

From the `backend` folder, with the same Gemini key used for `scripts/test_gemini_key.py`:

```powershell
# Windows PowerShell
$env:GEMINI_API_KEY="paste-your-key-here"
python eval/run_eval.py
```

```bash
# macOS / Linux
export GEMINI_API_KEY="paste-your-key-here"
python3 eval/run_eval.py
```

Takes about 3 minutes (5 s pause between calls for the free-tier rate limit).
Useful options: `--only x0` (just the tricky cases), `--runs 3` (check the AI gives the same answer every time).

## What the numbers mean

- **Risk level acceptable** – headline accuracy. Borderline cases accept two neighbouring levels.
- **Off by 2+ levels** – the serious mistakes (e.g. a CRITICAL student scored LOW). Target: 0.
- **Safety flag correct** – `priya_crisis.json` must always be flagged. Target: 100%.

The extra cases are only used for testing; they are not part of the demo data.
