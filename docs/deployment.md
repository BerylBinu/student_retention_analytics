# Deploying to Google Cloud

Total time: about 60-90 minutes the first time. The API itself is documented in
[`backend/README.md`](../backend/README.md#api-reference).

> **Windows users:** use **PowerShell**. Every command below is one line unless it says otherwise.
> Run everything from the `backend` folder unless a step says `cd` somewhere else.

## Part 0 — One-time setup

### 0.1 Start the Google Cloud free trial (10 min)

1. Go to https://console.cloud.google.com/freetrial and sign in with your Google account.
2. Country: **Malaysia**. Accept the terms. Add a card when asked. It's only for identity checks:
   the free trial gives free credit and **does not charge you** unless you choose to upgrade later.
3. Click **Start free**.

### 0.2 Create the project (2 min)

1. In the console, click the **project picker** at the top (next to the Google Cloud logo) → **New project**.
2. Project name: `student-retention`. Click **Create**.
3. Note the **Project ID** shown under the name (it may have numbers added, like `student-retention-471203`).
   You'll paste it below.
4. Check billing is attached: menu ☰ → **Billing**. It should show your free trial billing account.
   If it says "This project has no billing account", click **Link a billing account** and pick the trial one.

### 0.3 Install the Google Cloud CLI (`gcloud`) (10 min)

1. Download and run https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe
   (macOS/Linux: https://cloud.google.com/sdk/docs/install). Keep the default options.
2. On the last screen, leave **Run 'gcloud init'** ticked and click **Finish**. A terminal opens:
   - It opens your browser to sign in: use the same Google account.
   - "Pick cloud project to use": choose your project ID.
   - If asked about a default region/zone, you can skip it (we pass the region in every command).
3. **Close and reopen PowerShell**, then check:

```
gcloud --version
gcloud config get-value project
```

The second line should print your project ID. If not: `gcloud config set project YOUR-PROJECT-ID`

### 0.4 Python and a Gemini key

- Python 3.10+ for the local scripts: `python --version`.
- Gemini API key from https://aistudio.google.com → **Get API key**. Treat it like a password.

---

## Part 1 — Test everything on your laptop first (5 min)

```
python mock_data/generate_mock_data.py
python -m unittest discover -s tests
```

The second command should end with `OK` (32 tests). Then check your Gemini key:

```
$env:GEMINI_API_KEY="paste-your-key-here"
python scripts/test_gemini_key.py
```

Expected: a JSON block with `risk_score`, `primary_stressor`, evidence phrases and `Success! Your key works.`

---

## Part 2 — One-time Google Cloud setup (15 min)

### 2.0 Session variables (run this block in EVERY new PowerShell window)

Replace `your-project-id` with your Project ID the first time. These short names are used by every command below.

```
$PROJECT = "your-project-id"
$REGION  = "asia-southeast1"
$RAW     = "$PROJECT-raw"
$CURATED = "$PROJECT-curated"
$SA      = "retention-fn@$PROJECT.iam.gserviceaccount.com"
gcloud config set project $PROJECT
```

Later (after Part 3) also run this line to get the API address:

```
$API = gcloud functions describe retention-api --region=$REGION --format="value(serviceConfig.uri)"
```

### 2.1 Turn on the Google Cloud services we use (2 min)

```
gcloud services enable cloudfunctions.googleapis.com run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com eventarc.googleapis.com pubsub.googleapis.com storage.googleapis.com firestore.googleapis.com secretmanager.googleapis.com logging.googleapis.com
```

Wait for `Operation ... finished successfully`.

### 2.2 Create the Firestore database (1 min)

```
gcloud firestore databases create --location=$REGION
```

### 2.3 Create the two data lake buckets (1 min)

```
gcloud storage buckets create gs://$RAW --location=$REGION --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets create gs://$CURATED --location=$REGION --uniform-bucket-level-access --public-access-prevention
```

The bucket and the processor **must be in the same region** (`asia-southeast1`), or the trigger can't be created.

### 2.4 Store the secrets in Secret Manager (2 min)

**Why:** keys must never be in code or GitHub. Secret Manager keeps them encrypted, and only our
functions' service account may read them.

Gemini key (writing it to a temporary file avoids an extra line break, then the file is deleted):

```
$k = "paste-your-gemini-key-here"
Set-Content -Path key.txt -Value $k -NoNewline -Encoding ascii
gcloud secrets create gemini-api-key --data-file=key.txt
Remove-Item key.txt
```

Demo-reset token (a random password that protects `POST /admin/reset-demo`):

```
$ADMIN = -join ((48..57) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
Set-Content -Path admin.txt -Value $ADMIN -NoNewline -Encoding ascii
gcloud secrets create admin-token --data-file=admin.txt
Remove-Item admin.txt
```

### 2.5 Create the service account and grant permissions (3 min)

The functions run as `retention-fn`, which gets only the permissions it needs:

```
gcloud iam service-accounts create retention-fn --display-name="Student retention functions"
```

Wait ~10 seconds (new accounts take a moment to appear), then grant its roles:

```
foreach ($role in "roles/datastore.user","roles/storage.objectAdmin","roles/secretmanager.secretAccessor","roles/eventarc.eventReceiver","roles/run.invoker","roles/logging.logWriter") { gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:$SA" --role=$role --condition=None --quiet | Out-Null; Write-Host "granted $role" }
```

Let Cloud Storage send "file created" events (Google's docs require this for storage triggers):

```
$GCS_SA = (gcloud storage service-agent --project=$PROJECT | Out-String).Trim()
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:$GCS_SA" --role=roles/pubsub.publisher --condition=None --quiet | Out-Null
```

Let Cloud Build build our code (needed on some newer projects; harmless otherwise):

```
$NUM = gcloud projects describe $PROJECT --format="value(projectNumber)"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:$NUM-compute@developer.gserviceaccount.com" --role=roles/cloudbuild.builds.builder --condition=None --quiet | Out-Null
```

Permissions can take 1-2 minutes to apply before the next part works.

---

## Part 3 — Deploy the backend (10 min)

### 3.1 The processor (AI step)

```
gcloud functions deploy retention-processor --gen2 --runtime=python313 --region=$REGION --source=src/processor --entry-point=handle_upload --trigger-bucket=$RAW --service-account=$SA --trigger-service-account=$SA --retry --max-instances=2 --concurrency=1 --timeout=300s --memory=512Mi --set-env-vars="FIRESTORE_COLLECTION=insights,CURATED_BUCKET=$CURATED,GEMINI_MODEL=gemini-3.1-flash-lite,MIN_SECONDS_PER_CALL=9" --set-secrets=GEMINI_API_KEY=gemini-api-key:latest
```

What the important flags mean:
- `--trigger-bucket=$RAW` — run for every new file in the raw bucket (the code ignores anything outside `incoming/`).
- `--retry` — if a file fails for a temporary reason (rate limit, Gemini busy), Google Cloud retries it later.
- `--max-instances=2 --concurrency=1` and `MIN_SECONDS_PER_CALL=9` — at most ~13 Gemini calls a minute (free tier allows 15).
- `--set-secrets` — the Gemini key is read from Secret Manager, never stored in the code.

The first deploy takes 3-5 minutes. If it fails with a permission error mentioning **Eventarc** or a
**service agent**, wait 2 minutes and run the same command again (Google's docs note the first trigger in a
new project can fail while permissions finish setting up).

### 3.2 The API

```
gcloud functions deploy retention-api --gen2 --runtime=python313 --region=$REGION --source=src/api --entry-point=handle_http --trigger-http --allow-unauthenticated --service-account=$SA --max-instances=5 --timeout=60s --memory=512Mi --set-env-vars="FIRESTORE_COLLECTION=insights,RAW_BUCKET=$RAW,ALLOWED_ORIGIN=*,GEMINI_MODEL=gemini-3.1-flash-lite" --set-secrets="ADMIN_TOKEN=admin-token:latest,GEMINI_API_KEY=gemini-api-key:latest"
```

Get its address and test it:

```
$API = gcloud functions describe retention-api --region=$REGION --format="value(serviceConfig.uri)"
$API
Invoke-RestMethod "$API/health"
```

You should see `status: ok`. **`$API` is the API URL**; the dashboard needs it in Part 5.

---

## Part 4 — Load the data and watch it work (5 min)

Upload the 20 historical messages (they must go under `incoming/`):

```
gcloud storage cp "mock_data/samples/historical/*" gs://$RAW/incoming/historical/
```

Watch progress (repeats every 20 seconds and stops at 20):

```
while ($true) { $c = (Invoke-RestMethod "$API/stats").total_signals; Write-Host "$(Get-Date -Format T)  analysed: $c / 20"; if ([int]$c -ge 20) { Write-Host "Done!" -ForegroundColor Green; break }; Start-Sleep 20 }
```

It takes about 2-3 minutes. To see the processor's own log lines:

```
gcloud functions logs read retention-processor --gen2 --region=$REGION --limit=30
```

Look for `Saved ... student=TP071234 risk=67/HIGH stressor=FINANCIAL`. A line like `retrying in 60s` is
the rate-limit handling working, not an error. Then open `$API/students` in a browser.

---

## Part 5 — Deploy the dashboard to Cloud Run (10 min)

The dashboard is in `../frontend`. Next.js bakes `NEXT_PUBLIC_API_BASE_URL` into the app **when it is built**,
so we pass it as a *build* setting.

1. First check it builds on your laptop (catches errors before uploading):

```
cd ..\frontend
npm install
npm run build
```

2. Deploy (from the `frontend` folder, with `$API` set):

```
gcloud run deploy retention-dashboard --source . --region=$REGION --allow-unauthenticated --memory=1Gi --set-build-env-vars="NEXT_PUBLIC_API_BASE_URL=$API,GOOGLE_NODE_RUN_SCRIPTS=build"
```

If it asks to create an Artifact Registry repository, answer **Y**. The build takes 3-6 minutes.
At the end it prints a **Service URL** (`https://retention-dashboard-….run.app`). That's the public
dashboard link. To print it again:

```
gcloud run services describe retention-dashboard --region=$REGION --format="value(status.url)"
```

3. Go back to the backend folder: `cd ..\backend`

---

## Part 6 — Live demo and reset

**Sending live messages:** use the dashboard's **Live demo** page. Each result takes 10-60 seconds because of the
free-tier pacing. **Don't press Send twice** — the backend retries on its own, and a second press creates a duplicate.

**Reset to the original 20 messages** (deletes only messages sent from the Live demo page, plus every
counsellor follow-up record, so all students start as "Not contacted"):

```
$ADMIN = (gcloud secrets versions access latest --secret=admin-token | Out-String).Trim()
Invoke-RestMethod -Method Post -Uri "$API/admin/reset-demo" -Headers @{ "X-Admin-Token" = $ADMIN }
```

Expected: `deleted: 3  remaining: 20  cases_cleared: 2` (numbers depend on what you sent and saved). Then refresh the dashboard page (it has no caching).

---

## Part 7 — Updating after code changes

Re-run only the deploy command for what changed (from the `backend` folder, after the Part 2.0 block):

| What changed | Command | Then |
|---|---|---|
| `src/processor/` (e.g. the prompt) | Part 3.1 deploy command | Re-upload the files (Part 4) so they're re-scored |
| `src/api/` | Part 3.2 deploy command | Nothing |
| `../frontend` | Part 5 deploy command | Refresh the dashboard |
| Gemini key | `Set-Content key.txt` as in 2.4, then `gcloud secrets versions add gemini-api-key --data-file=key.txt`, `Remove-Item key.txt` | Re-run the Part 3.1 and 3.2 deploys |

Re-uploading the same files is safe: each file always gets the same ID, so results are overwritten, not duplicated.

---

## Troubleshooting (check here first)

| Symptom | Cause | Fix |
|---|---|---|
| `'gcloud' is not recognized` | Terminal opened before install | Close and reopen PowerShell |
| Commands fail with `$PROJECT` empty or `gs://-raw` | New PowerShell window | Run the Part 2.0 block again |
| `Billing account ... not found` / `billing must be enabled` | Project not linked to the trial | Part 0.2 step 4 |
| `database already exists` (2.2) or `already exists` (2.3, 2.4, 2.5) | You ran it before | Fine, carry on |
| Bucket create: `name is not available` | Bucket names are global | Use `$RAW = "$PROJECT-raw2"` (and the same for `$CURATED`) everywhere |
| `Service account ... does not exist` (2.5) | Account still being created | Wait 30 seconds, run the line again |
| Processor deploy: permission error about **Eventarc**/**service agent** | First trigger in a new project | Wait 2 minutes, run the same deploy again |
| Deploy: `Build failed ... missing permission on the build service account` | Cloud Build permission | Run the last command in 2.5, wait 2 minutes, deploy again |
| Logs: `GEMINI_API_KEY is not set` | Deployed without `--set-secrets` | Re-run the Part 3.1 command exactly |
| Logs: `Permission 'secretmanager.versions.access' denied` | Role missing | Re-run the `foreach` line in 2.5 |
| Logs: `Gemini HTTP 400 ... API key not valid` | Wrong key in the secret | Part 7 "Gemini key" row |
| Logs: `Gemini HTTP 429 ... retrying in 60s` | Free-tier limit | Normal; it waits and retries by itself |
| Logs: `Gemini daily free-tier quota used up` | Requests-per-day limit | Google Cloud keeps retrying; it resets at 4pm Malaysia time |
| Uploaded files but no processor logs | Wrong bucket/folder, or trigger not ready | Files must be in `gs://$RAW/incoming/...`; check `gcloud eventarc triggers list --location=$REGION`; re-upload |
| `/admin/reset-demo` returns 403 | Wrong or empty token | Re-run the `$ADMIN = gcloud secrets versions access ...` line |
| Dashboard build fails on Cloud Run | Code doesn't build | Run `npm run build` locally (Part 5 step 1) and fix the first error it shows |
| Dashboard loads but shows `API ... failed` | Built with the wrong/empty API URL | Check `$API` prints a URL, then re-run the Part 5 deploy |
| Browser console: `blocked by CORS policy` | `ALLOWED_ORIGIN` set to another site | Keep `ALLOWED_ORIGIN=*`, or set it to the exact dashboard URL |

---

## Costs

The free trial's credit covers this many times over. Cloud Run functions, Firestore, Cloud Storage and
Secret Manager all have monthly free allowances far above a hackathon demo; everything scales to zero
when nobody is using it. Gemini is billed separately by Google AI Studio (free tier).

## Clean up

Deleting the project removes everything in it (buckets, database, functions, dashboard):

```
gcloud projects delete $PROJECT
```
