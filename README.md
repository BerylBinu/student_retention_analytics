# Student Retention Analytics Engine

**APU Cloud Innovation Hackathon — Data-Driven Research & Intelligent Decision Making track**

Universities usually spot students at risk of dropping out from lagging signals like poor grades and
low attendance, often too late to help. This project reads the **unstructured** messages students
already send (support tickets, LMS forum posts, emails, chatbot conversations), uses **Gemini** to detect
early warning signs such as financial stress, burnout and isolation, and gives counsellors a ranked,
evidence-backed **At-Risk Student Dashboard** — built entirely on **Google Cloud**.

| | |
|---|---|
| **Live dashboard** | https://retention-dashboard-353252835497.asia-southeast1.run.app/ |
| **Demo video** | _add the video link here_ |
| **Pitch deck** | _add the PDF link here_ |

## How it works

![Google Cloud architecture](docs/architecture.png)

1. Student messages from university systems land in the Cloud Storage data lake (`incoming/`).
2. Eventarc triggers the processor for every new file, and retries automatically if anything fails.
3. The processor asks **Gemini** for a strict JSON analysis: risk score 0-100, main stressor, quoted evidence,
   recommended action and urgency. It validates every field and applies safety rules (any self-harm signal is
   always Critical).
4. Results are saved to Firestore, with a clean copy in the curated bucket.
5. The API ranks students, builds the charts, asks Gemini for a short **AI briefing**, and stores counsellors'
   follow-ups.
6. Counsellors see who needs help, why, and what to do next, then record a follow-up or email the student
   straight from the dashboard.

In production, connectors from the LMS, helpdesk, email and chatbot would drop messages into the data lake
automatically; the dashboard's **Live demo** page simulates one arriving (`POST /ingest`).

The diagram source is [`docs/architecture.svg`](docs/architecture.svg) (scales without blurring, e.g. for the pitch deck).

## Features

- **AI briefing:** Gemini summarises today's picture in a few sentences: main drivers of risk and who to contact first.
- **Ranked at-risk list** with risk level, trend, stressors, urgency and a **Needs follow-up** filter.
- **Student detail:** risk over time, every analysed message with the AI summary and the exact evidence quotes.
- **Counsellor follow-up:** mark a student Contacted or Resolved with a note; a new message puts them back on the list.
- **Email the student:** one click opens a kind, editable draft tailored to the student's main stressor.
- **Multilingual:** handles Malay and Manglish messages (summaries in English, evidence quoted in the original).
- **Live demo:** send a message and watch the whole Google Cloud pipeline score it in under a minute.

## Responsible AI

- Gemini must answer in a fixed schema; the code then checks and clamps every value.
- Self-harm signals always become Critical / Immediate and never fade on their own.
- Every alert shows the exact phrases that triggered it, so counsellors can check the AI's reasoning.
- Messages are treated as data, not instructions (prompt-injection guard).
- An accuracy test against a hand-written answer key measures the prompt (`backend/eval/`): 31 cases including
  Malay and Manglish.
- The AI never contacts a student: counsellors review and send every email themselves, and their follow-ups never
  change the AI's risk score.
- The AI briefing only sees the AI summaries and scores, never the raw student messages.
- All student data in this repo is fictional.

## Repository

| Folder | What's inside |
|---|---|
| [`backend/`](backend) | Google Cloud pipeline: processor and API (Cloud Run functions), mock data, accuracy test, offline tests, and the full step-by-step deploy guide |
| [`frontend/`](frontend) | Next.js + Tailwind dashboard (overview, student list, student detail, live demo) |

**Run or deploy it:** follow [`backend/README.md`](backend/README.md), Parts 0-5. To run only the dashboard
locally against the live API, see [`frontend/README.md`](frontend/README.md).

## Built with

Google Cloud Storage · Eventarc · Cloud Run functions · Firestore · Secret Manager · Cloud Run ·
Gemini API · Python · Next.js · TypeScript · Tailwind CSS

## Team

- **Person A — Cloud and pipeline:** Google Cloud architecture, data pipeline, API, deployment
- **Person B — AI, data and pitch:** mock data, Gemini prompt, risk scoring, accuracy testing, pitch deck
- **Person C — Frontend and demo:** dashboard, charts, demo flow, demo video
