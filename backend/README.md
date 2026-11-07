# Backend: Student Retention Analytics Engine (cloud + data pipeline)

This folder is the whole AWS side of the project. One command deploys it.
The Next.js dashboard only needs the **API URL** this produces.

```
                    ┌──────────────────────── AWS (ap-southeast-1) ─────────────────────────┐
 Mock Zendesk /     │                                                                        │
 Moodle / email ──► │  S3 data lake          SQS queue          Processor Lambda             │
 files (upload)     │  incoming/  ───────►  (buffer +   ───────► reads file ──► Gemini API ──┼──► Google
                    │                        retries)            cleans answer               │
 Dashboard "add  ──►│  HTTP API ──► API Lambda ──► writes to incoming/live/                  │
 message" button    │                                            │                           │
                    │                                            ▼                           │
 Next.js dashboard ◄┼── HTTP API ◄── API Lambda ◄──── DynamoDB (insights)   S3 curated/      │
                    └────────────────────────────────────────────────────────────────────────┘
```

## What each piece does (plain English)

| Piece | What it is | Why we use it |
|---|---|---|
| **S3 bucket** | Cloud folder storage. `incoming/` holds raw files; `curated/` holds cleaned results. | This is our "data lake": raw data is kept as-is, so we can re-process it later. |
| **SQS queue** | A waiting line for work. S3 adds a message every time a file lands. | If you upload 20 files at once, the queue feeds them to Lambda 2 at a time so we don't hit Gemini's rate limit. Failed files retry automatically. |
| **Dead-letter queue (DLQ)** | Where a message goes after failing 3 times. | Nothing is silently lost; you can see what broke. |
| **Processor Lambda** | Python code that runs only when there is work. | Sends each message to Gemini, checks the answer, saves it. You pay per run, no server to manage. |
| **Gemini API** | Google's AI model. | Turns messy text into structured JSON: risk score, stressor, evidence, recommended action. |
| **SSM Parameter Store** | Encrypted storage for settings. | Keeps the Gemini key out of the code and out of GitHub. |
| **DynamoDB** | A fast NoSQL database. | Stores one row per analysed message for the dashboard. |
| **HTTP API + API Lambda** | Public web addresses (`/students`, `/stats`, …). | How the React dashboard reads data, and how the demo adds a live message. |
| **AWS SAM (`template.yaml`)** | "Infrastructure as code": one file describing all of the above. | One command creates everything, including permissions (IAM roles) and CORS, which are the two things beginners most often get wrong when clicking in the console. |

## Folder map

```
backend/
├── template.yaml                 # all AWS resources (read the comments!)
├── src/
│   ├── processor/app.py          # S3 -> Gemini -> DynamoDB
│   └── api/app.py                # dashboard API
├── mock_data/
│   └── generate_mock_data.py     # creates fictional student messages in 4 formats
├── scripts/
│   └── test_gemini_key.py        # checks your Gemini key and previews AI output locally
└── tests/
    └── test_offline.py           # 13 tests, no AWS or internet needed
```

---

# Step-by-step setup

Total time: about 60-90 minutes the first time. **Only one person on the team needs to do Parts 0-4.**
Everyone else just uses the API URL.

> **Windows users:** use **PowerShell**. Every command below is a single line and works in PowerShell,
> macOS Terminal and Linux, unless it says otherwise.

## Part 0 — One-time setup

### 0.1 Pick a region and set a budget alarm (5 min)

We use **Asia Pacific (Singapore) `ap-southeast-1`** for everything. Using one region matters: resources
in different regions can't see each other, and that's the #1 cause of "it works on my side but not in AWS".

Set a budget alarm so a mistake can't cost you money silently:

1. Sign in to the [AWS Console](https://console.aws.amazon.com/).
2. In the search bar at the top, type **Budgets** and open **Billing and Cost Management → Budgets**.
3. Click **Create budget** → choose **Use a template (simplified)** → pick **Monthly cost budget**.
4. Budget amount: **5** (USD). Email recipients: your email. Click **Create budget**.

### 0.2 Create command-line access keys (10 min)

The AWS CLI and SAM need keys to act on your account.

1. Console search bar → **IAM** → left menu **Users** → **Create user**.
2. User name: `hackathon-cli` → **Next**.
3. Choose **Attach policies directly** → tick **AdministratorAccess** → **Next** → **Create user**.
4. Click the new user → **Security credentials** tab → **Create access key**.
5. Use case: **Command Line Interface (CLI)** → tick the confirmation box → **Next** → **Create access key**.
6. Click **Download .csv file**. Keep it private. **Never paste these keys into code, Discord or GitHub.**

> Admin access is fine for a short hackathon. Delete this access key after the event (see "Clean up").

> **Using an AWS Academy "Learner Lab" or a university-provided account?** Those usually block creating
> IAM roles, and the deploy will fail with `iam:CreateRole ... AccessDenied`. Tell us and we'll switch the
> template to use the lab's existing `LabRole`.

### 0.3 Install the AWS CLI (5 min)

- **Windows:** download and run https://awscli.amazonaws.com/AWSCLIV2.msi
- **macOS:** download and run https://awscli.amazonaws.com/AWSCLIV2.pkg
- **Linux:** follow https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

**Close and reopen your terminal**, then:

```
aws --version
```

You should see something like `aws-cli/2.x.x`. Now connect it to your account:

```
aws configure
```

Answer the four prompts:

```
AWS Access Key ID [None]:      <Access key ID from the .csv>
AWS Secret Access Key [None]:  <Secret access key from the .csv>
Default region name [None]:    ap-southeast-1
Default output format [None]:  json
```

Check it works (it should print your account number, not an error):

```
aws sts get-caller-identity
```

### 0.4 Install the AWS SAM CLI (5 min)

- **Windows:** download and run https://github.com/aws/aws-sam-cli/releases/latest/download/AWS_SAM_CLI_64_PY3.msi
- **macOS (Homebrew):** `brew install aws-sam-cli`
- **Other:** https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html

Close and reopen the terminal, then:

```
sam --version
```

### 0.5 Python for the local scripts (5 min)

You need Python 3.10 or newer **only to run the helper scripts on your laptop**. (The cloud uses its own
Python 3.13; your local version does not need to match.)

```
python --version
```

On macOS/Linux use `python3` instead of `python` in every command below.
On Windows, if typing `python` opens the Microsoft Store, install Python from https://www.python.org/downloads/
and **tick "Add python.exe to PATH"** on the first installer screen.

### 0.6 Get a Gemini API key (3 min)

1. Go to https://aistudio.google.com/ and sign in with a Google account.
2. Click **Get API key** → **Create API key** (create or pick a Google Cloud project when asked).
3. Copy the key (it starts with `AIza`). Treat it like a password.

---

## Part 1 — Test everything on your laptop first (10 min)

Open a terminal **inside the `backend` folder** (all commands from here on assume this).

**1. Create the mock data**

```
python mock_data/generate_mock_data.py
```

Expected: `Wrote 20 historical files ...` and `Wrote 3 live demo files ...`.
Open a few files in `mock_data/samples/` to see the four messy formats.

**2. Run the offline tests** (checks the logic without AWS or internet)

```
python -m unittest discover -s tests -v
```

Expected last line: `OK` (13 tests).

**3. Test your Gemini key and preview the AI output**

Windows PowerShell:
```
$env:GEMINI_API_KEY="paste-your-key-here"
python scripts/test_gemini_key.py
```

macOS / Linux:
```
export GEMINI_API_KEY="paste-your-key-here"
python3 scripts/test_gemini_key.py
```

Expected: a JSON block with `risk_score`, `primary_stressor: "FINANCIAL"`, evidence phrases, and
`Success! Your key works.` Try the crisis example too:

```
python scripts/test_gemini_key.py mock_data/samples/live_demo/priya_crisis.json
```

It should come back `CRITICAL`, `IMMEDIATE`, `self_harm_indicator: true`.

If this step fails, fix it now (see Troubleshooting); deploying won't fix a bad key.

---

## Part 2 — Store the Gemini key in AWS (2 min)

**Why:** the Lambda needs the key, but keys must never be in code or GitHub. SSM Parameter Store keeps it
encrypted (`SecureString`) and only our Lambda is allowed to read it. Standard parameters are free.

```
aws ssm put-parameter --name "/retention/gemini-api-key" --type SecureString --value "paste-your-key-here" --region ap-southeast-1
```

Expected: `{"Version": 1, "Tier": "Standard"}`.
To replace the key later, run the same command with `--overwrite` at the end.

---

## Part 3 — Deploy the whole backend (5-10 min)

**Why `sam deploy` and no `sam build`:** our code only uses libraries that already exist inside Lambda,
so there is nothing to build. Skipping `sam build` avoids the common
`Binary validation failed for python` error when your laptop's Python version differs from 3.13.

```
sam deploy --guided
```

Answer the prompts exactly like this (press Enter to accept a value in brackets):

| Prompt | Answer |
|---|---|
| Stack Name | `student-retention` |
| AWS Region | `ap-southeast-1` |
| Parameter GeminiModel | Enter (keeps `gemini-3.1-flash-lite`) |
| Parameter GeminiApiKeyParameterName | Enter |
| Parameter AllowedOrigin | Enter (keeps `*`) |
| Confirm changes before deploy | `y` |
| Allow SAM CLI IAM role creation | `Y` |
| Disable rollback | `N` |
| **ApiFunction has no authentication. Is this okay?** (may be asked several times) | `y` every time |
| Save arguments to configuration file | `Y` |
| SAM configuration file | Enter |
| SAM configuration environment | Enter |
| Deploy this changeset? | `y` |

Wait for `Successfully created/updated stack - student-retention`. At the end SAM prints **Outputs**.
Copy these somewhere (or print them again any time):

```
aws cloudformation describe-stacks --stack-name student-retention --query "Stacks[0].Outputs" --output table
```

You'll see `ApiBaseUrl` (for the frontend), `DataLakeBucketName`, `InsightsTableName`, and more.

> `samconfig.toml` was just created. It contains no secrets (the key lives in SSM), so it is safe to
> commit. Later deploys after code changes are just: `sam deploy`

**Quick check:** open `<ApiBaseUrl>/health` in your browser. You should see `{"status": "ok", ...}`.

---

## Part 4 — Feed the pipeline and watch it work (5 min)

**1. Upload the historical files** (replace `BUCKET` with your `DataLakeBucketName`):

```
aws s3 cp mock_data/samples/historical s3://BUCKET/incoming/historical/ --recursive
```

**Important:** files must go under `incoming/`. Anything elsewhere in the bucket is ignored on purpose.

**2. Watch the processor live** (open a second terminal in the `backend` folder):

```
sam logs --stack-name student-retention --name ProcessorFunction --tail
```

You'll see lines like `Saved 3f9a... student=TP071234 risk=72/HIGH stressor=FINANCIAL`.
20 files take about 1-2 minutes (2 at a time). Press `Ctrl+C` to stop watching.

**3. Check the results**

- Count rows: `aws dynamodb scan --table-name TABLENAME --select COUNT` → `"Count": 20`
- In the browser open `<ApiBaseUrl>/students` and `<ApiBaseUrl>/stats`
- Console view: search **DynamoDB** → **Tables** → your table → **Explore table items**

---

## Part 5 — The live demo moment (for the video)

Show judges a brand-new message flowing through the system in seconds.

**Option A: upload a file**

```
aws s3 cp mock_data/samples/live_demo/priya_crisis.json s3://BUCKET/incoming/live/
```

**Option B: send a message through the API** (this is what a dashboard "Add message" button would call)

Windows PowerShell:
```
Invoke-RestMethod -Method Post -Uri "https://YOUR-API-ID.execute-api.ap-southeast-1.amazonaws.com/ingest" -ContentType "application/json" -Body '{"student_id":"TP071234","student_name":"Aisyah Rahman","source":"zendesk","text":"I have to stop my studies, I cannot pay the fees and my family needs me to work full time."}'
```

macOS / Linux:
```
curl -X POST "https://YOUR-API-ID.execute-api.ap-southeast-1.amazonaws.com/ingest" -H "Content-Type: application/json" -d '{"student_id":"TP071234","student_name":"Aisyah Rahman","source":"zendesk","text":"I have to stop my studies, I cannot pay the fees and my family needs me to work full time."}'
```

About 5-15 seconds later the new row shows up in `GET /insights` and the student's risk rises in `/students`.

---

## Part 6 — API reference for the frontend team

Base URL = `ApiBaseUrl` from the stack outputs. In Next.js, put it in `.env.local`:

```
NEXT_PUBLIC_API_BASE_URL=https://YOUR-API-ID.execute-api.ap-southeast-1.amazonaws.com
```

(No trailing slash. Restart `npm run dev` after editing `.env.local`.)

| Method | Path | Use it for |
|---|---|---|
| GET | `/health` | "Is the backend up?" |
| GET | `/stats` | KPI cards and charts (risk distribution, stressors, daily trend) |
| GET | `/students` | The at-risk student table, highest risk first |
| GET | `/students/{student_id}` | Student detail page with full timeline |
| GET | `/insights?risk_level=HIGH,CRITICAL&stressor=FINANCIAL&student_id=TP071234&limit=50` | Raw signal feed (all filters optional) |
| POST | `/ingest` | Body: `{"student_id","student_name","source","text"}` → `202 {"status":"queued"}` |

**Allowed values**

- `risk_level`: `LOW` (0-29), `MEDIUM` (30-59), `HIGH` (60-79), `CRITICAL` (80-100)
- `primary_stressor`: `FINANCIAL`, `ACADEMIC_PRESSURE`, `BURNOUT_MENTAL_HEALTH`, `SOCIAL_ISOLATION`,
  `TECHNOLOGY_ACCESS`, `FAMILY_PERSONAL`, `HEALTH_PHYSICAL`, `HOUSING_TRANSPORT`, `NONE`
- `urgency`: `ROUTINE`, `FOLLOW_UP_THIS_WEEK`, `CONTACT_WITHIN_24H`, `IMMEDIATE`
- `trend` (students only): `NEW`, `RISING`, `FALLING`, `STABLE`
- `source_system`: `LMS_FORUM`, `SUPPORT_TICKET`, `EMAIL`, `CHATBOT`, `OTHER`

**Example: `GET /students`**

```json
{
  "count": 10,
  "items": [
    {
      "student_id": "TP070455",
      "student_name": "Priya Nair",
      "signal_count": 3,
      "current_risk_score": 92,
      "current_risk_level": "CRITICAL",
      "latest_risk_score": 92,
      "average_risk_score": 70.3,
      "trend": "RISING",
      "top_stressors": ["BURNOUT_MENTAL_HEALTH", "ACADEMIC_PRESSURE"],
      "self_harm_flag": true,
      "highest_urgency": "IMMEDIATE",
      "recommended_action": "Contact the student today and connect them with campus counselling services.",
      "latest_summary": "Student expresses hopelessness and asks how to stop everything.",
      "first_event_time": "2026-10-03T17:12:00Z",
      "latest_event_time": "2026-11-06T18:40:00Z",
      "sources": ["CHATBOT", "LMS_FORUM"]
    }
  ]
}
```

**Example: one item from `GET /insights` (also the shape of each `timeline` entry)**

```json
{
  "record_id": "a1b2c3d4e5f6a7b8c9d0e1f2",
  "student_id": "TP071234",
  "student_name": "Aisyah Rahman",
  "source_system": "EMAIL",
  "risk_score": 72,
  "risk_level": "HIGH",
  "primary_stressor": "FINANCIAL",
  "secondary_stressors": ["ACADEMIC_PRESSURE"],
  "sentiment": "NEGATIVE",
  "summary": "Student cannot cover a fee gap after a loan delay and is working nights.",
  "evidence": ["remaining RM 4,850", "working nights at a cafe", "really want to continue my degree"],
  "recommended_action": "Refer to the bursary for an instalment plan or hardship fund this week.",
  "urgency": "FOLLOW_UP_THIS_WEEK",
  "self_harm_indicator": false,
  "event_time": "2026-10-13T15:41:00Z",
  "event_date": "2026-10-13",
  "raw_text": "From: \"Aisyah Rahman\" <tp071234@student.uni.example> ...",
  "s3_uri": "s3://student-retention-datalake-.../incoming/historical/02_email.txt",
  "processed_at": "2026-11-07T03:12:45Z",
  "model": "gemini-3.1-flash-lite"
}
```

**Example: `GET /stats`** (ready for Recharts: each array is already `[{name, count}]`-style)

```json
{
  "total_signals": 23,
  "total_students": 10,
  "students_needing_attention": 5,
  "self_harm_alerts": 1,
  "average_risk_score": 46.2,
  "signals_by_risk_level": [{"level": "LOW", "count": 7}, {"level": "MEDIUM", "count": 6}, {"level": "HIGH", "count": 7}, {"level": "CRITICAL", "count": 3}],
  "students_by_risk_level": [{"level": "LOW", "count": 3}, {"level": "MEDIUM", "count": 2}, {"level": "HIGH", "count": 3}, {"level": "CRITICAL", "count": 2}],
  "signals_by_stressor": [{"stressor": "FINANCIAL", "count": 5}, {"stressor": "BURNOUT_MENTAL_HEALTH", "count": 3}],
  "signals_by_source": [{"source": "EMAIL", "count": 7}, {"source": "LMS_FORUM", "count": 8}],
  "timeline": [{"date": "2026-10-02", "signals": 1, "avg_risk_score": 45.0, "high_or_critical": 0}],
  "generated_at": "2026-11-07T03:20:00Z"
}
```

(Exact numbers depend on what Gemini returns.)

**Copy-paste fetch helper for Next.js** (`lib/api.ts`):

```ts
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL;

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (!BASE) throw new Error("NEXT_PUBLIC_API_BASE_URL is not set in .env.local");
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

// usage:
// const stats = await api<any>("/stats");
// await api("/ingest", { method: "POST", headers: { "Content-Type": "application/json" },
//   body: JSON.stringify({ student_id: "TP071234", student_name: "Aisyah Rahman", source: "zendesk", text: "..." }) });
```

---

## Troubleshooting (check here first)

| Symptom | Cause | Fix |
|---|---|---|
| `'aws'` / `'sam'` is not recognized | Terminal opened before install | Close and reopen the terminal |
| `Unable to locate credentials` | CLI not configured | Run `aws configure` (Part 0.3) |
| `Binary validation failed for python` | You ran `sam build` | Not needed. Delete the `.aws-sam` folder and run `sam deploy` |
| Deploy fails: `iam:CreateRole ... AccessDenied` | Restricted account (e.g. Learner Lab) | Tell the team lead; template needs the `LabRole` variant |
| Deploy fails: bucket `already exists` | An old stack (or another teammate) in the same account/region already created it | Delete the old stack, or deploy from only one laptop |
| Deploy fails: `ROLLBACK_COMPLETE`, can't update | First deploy failed | `sam delete --stack-name student-retention` then deploy again |
| Logs: `Could not read the Gemini API key from SSM` | Parameter missing or in another region | `aws ssm get-parameter --name /retention/gemini-api-key --region ap-southeast-1`; redo Part 2 if it errors |
| Logs: `Gemini HTTP 400 ... API key not valid` | Wrong or stale key | Redo Part 2 with `--overwrite`. New Lambda containers pick it up; to force it, redeploy |
| Logs: `Gemini HTTP 404` | Model name typo | `sam deploy --parameter-overrides GeminiModel=gemini-3.1-flash-lite` |
| Logs: `Gemini HTTP 429` | Free-tier rate limit | Messages retry by themselves. Upload fewer files at once or wait a minute |
| Uploaded files but no logs at all | File not under `incoming/` | Re-upload to `s3://BUCKET/incoming/...` |
| Some rows missing | Messages failed 3 times → DLQ | `aws sqs get-queue-attributes --queue-url <DeadLetterQueueUrl> --attribute-names ApproximateNumberOfMessages`, then read the processor logs for the error. Re-upload the file after fixing |
| Browser console: `blocked by CORS policy` | Wrong URL (e.g. double `//`) or `AllowedOrigin` set to another domain | Check `NEXT_PUBLIC_API_BASE_URL` has no trailing slash; keep `AllowedOrigin` as `*` until the frontend is hosted |
| Frontend shows `undefined` URL | `.env.local` not loaded | Name must start with `NEXT_PUBLIC_`; restart `npm run dev` |
| PowerShell `curl` behaves strangely | `curl` is an alias in Windows PowerShell | Use `Invoke-RestMethod` (Part 5) or `curl.exe` |

Re-uploading the same file is safe: it overwrites the same row instead of creating a duplicate.

---

## Costs

For this demo the AWS side costs cents: Lambda, SQS and DynamoDB on-demand are pay-per-use and covered by
the free tier at this volume. The Gemini free tier has per-minute and per-day limits, which is why the queue
only runs 2 Gemini calls at a time.

## Clean up after the hackathon

```
aws s3 rm s3://BUCKET --recursive
sam delete --stack-name student-retention
aws ssm delete-parameter --name "/retention/gemini-api-key" --region ap-southeast-1
```

Then in the console: **IAM → Users → hackathon-cli → Security credentials → Deactivate/Delete** the access key.

---

## Talking points for the pitch

- **Event-driven data lake:** raw data is immutable in `incoming/`, structured output lands in `curated/` and DynamoDB. New sources (IoT check-in sensors, Wi-Fi logins) can be added by dropping files in the same place.
- **Resilient by design:** SQS buffering, automatic retries, dead-letter queue, idempotent writes.
- **Responsible AI:** Gemini is forced into a strict JSON schema; the code then validates every field. Any self-harm signal is always escalated to `CRITICAL / IMMEDIATE`, regardless of what the model scored. Evidence phrases are quoted from the source so counselors can verify the AI's reasoning. The model is told to treat messages as data, which protects against prompt injection.
- **Security:** no keys in code (SSM SecureString), private encrypted S3 bucket, least-privilege IAM roles generated per function.
- **Privacy:** all demo data is fictional. A real deployment would need student consent and compliance with Malaysia's PDPA, plus a paid Gemini tier (free-tier prompts may be used by Google to improve its products), API authentication (e.g. Amazon Cognito), and role-based access for counselors.
