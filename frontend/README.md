# Frontend: At-Risk Student Dashboard

A Next.js dashboard that shows the results of the Student Retention Analytics Engine. It reads live data from the team's Google Cloud API (see [`../backend`](../backend)) and helps student support staff answer three questions:

1. **Who needs help right now?** Students ranked by risk, with the most serious cases first.
2. **Why?** The stressors the AI found (financial, academic pressure, burnout and so on) and the exact phrases that triggered each alert.
3. **What should we do?** The AI's recommended next step and how urgently to act.

## Pages

| Page | Address | What it shows | API used |
|---|---|---|---|
| Overview | `/` | Headline numbers, priority students, risk-level donut chart, top stressors, message sources, daily risk trend | `GET /stats`, `GET /students` |
| Students | `/students` | Every student ranked by risk, with filters by risk level and search by name or ID | `GET /students` |
| Student detail | `/students/{student_id}` | Risk score and trend, recommended action, risk-over-time chart, and every analysed message with the AI summary, evidence quotes and original text | `GET /students/{student_id}` |
| Live demo | `/demo` | Send a new message into the pipeline and watch the AI result arrive | `POST /ingest`, then `GET /insights` |

### How the live demo works

1. The message is sent to `POST /ingest`, which saves it to the Cloud Storage data lake.
2. Cloud Storage triggers the processing Cloud Run function (through Eventarc), which asks Gemini to analyse it and stores the result in Firestore.
3. The page checks `GET /insights` every 4 seconds until the new result appears (usually 10 to 60 seconds), then shows it.

Six ready-made messages match the files in `backend/mock_data/samples/live_demo`: Aisyah, Chen Wei and Priya (English), plus Nurul (Malay), Daniel and Kevin (Manglish) to show the AI reading mixed-language messages.

### Handling self-harm signals

When the AI flags a possible self-harm risk, the dashboard shows a calm, clearly visible banner with the recommended action ("prioritise wellbeing contact"). It deliberately avoids flashing or alarming wording. The flag appears on the Overview, in the student list and on the student's page.

### Reaching out to a student

Each student page has an **Email** button under "Recommended next step". It opens a ready-written draft in the
counsellor's own email app (or in Gmail with **Open in Gmail**), tailored to the student's main stressor. The
counsellor reviews and edits it, then sends it themselves: the AI never contacts a student on its own, and the
email never mentions risk scores, the AI or the analysed messages. Addresses use the demo domain
`student.example.edu` (set in `components/EmailStudent.tsx`) so a demo click can't reach a real student; a real
deployment would take the address from the university's student directory. For a possible self-harm risk, the
button area reminds the counsellor to call or meet the student first and use email only as a follow-up.

## Run it on your computer

You need [Node.js](https://nodejs.org) (LTS version).

```bash
cd frontend
npm install
```

Create a file called `.env.local` in the `frontend` folder with the API address from the backend deployment (the `ApiBaseUrl` stack output, no trailing slash):

```
NEXT_PUBLIC_API_BASE_URL=https://retention-api-XXXXXXXXXX.asia-southeast1.run.app
```

Then start the app:

```bash
npm run dev -- --webpack
```

Open http://localhost:3000.

To check the production build:

```bash
npm run build
npm run start
```

> **Windows PowerShell tip:** if `npm` fails with "running scripts is disabled on this system", run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use `npm.cmd` instead of `npm`.

## Deploy it to Google Cloud Run

The public dashboard runs on Cloud Run, Google's service for hosting web apps. The steps (including how
the API address is passed in at build time) are in [`../backend/README.md`](../backend/README.md),
Part 5. `.gcloudignore` keeps `node_modules`, `.next` and `.env*` files out of the upload.

## Folder map

```
frontend/
  app/
    layout.tsx               Sidebar and page frame
    page.tsx                 Overview
    loading.tsx              Loading screen while data is fetched
    students/
      page.tsx               Student list (fetches data)
      StudentTable.tsx       Filters, search and table (runs in the browser)
      [id]/page.tsx          Student detail
    demo/page.tsx            Live demo form
  components/
    ui.tsx                   Shared pieces: cards, badges, charts, icons, alert banner
    Nav.tsx                  Sidebar links
  lib/
    api.ts                   API helper, data types, friendly labels and colours
  next.config.ts             Next.js settings
```

## Design notes

- **Live data, no caching.** Every page fetches fresh data from the API when it opens, so new AI results show up straight away. `cacheComponents` is turned off in `next.config.ts` for this reason.
- **No chart library.** The charts (donut, bars, risk timeline) are plain SVG and Tailwind, so there are fewer dependencies to install.
- **Friendly labels.** API values like `BURNOUT_MENTAL_HEALTH` and `FOLLOW_UP_THIS_WEEK` are turned into readable text in `lib/api.ts`. Each risk level and stressor has one colour, used the same way on every page.
- **Risk levels:** Low 0-29, Medium 30-59, High 60-79, Critical 80-100. A student's current score comes from their most recent message, so a student who gets help moves down the list. Safety rule (set in the backend): anyone flagged for possible self-harm stays Critical until a counsellor follows up. The detail page also shows the peak score for context.

## Built with

Next.js 16 (App Router), React, TypeScript, Tailwind CSS 4.