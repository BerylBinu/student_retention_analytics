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

```
 Student messages ──► Cloud Storage ──► Eventarc ──► Cloud Run function ──► Gemini
 (tickets, forums,     (raw data lake)   (event,       (processor: prompt,
  emails, chatbot)                        auto-retry)   validation, safety rules)
                                                              │
                                                              ▼
 Counsellor ◄── Next.js dashboard ◄── Cloud Run function ◄── Firestore  (+ curated bucket)
                (Cloud Run)           (API)
```

1. A raw message lands in the Cloud Storage data lake (`incoming/`).
2. Eventarc triggers the processor, which asks Gemini for a strict JSON analysis: risk score 0-100,
   main stressor, quoted evidence, recommended action and urgency.
3. The processor validates every field and applies safety rules (any self-harm signal is always
   escalated to Critical), then saves the result to Firestore.
4. The API turns those results into a ranked student list, per-student timelines and chart data.
5. The dashboard shows who needs help now, why, and what to do next.

## Responsible AI

- Gemini must answer in a fixed schema; the code then checks and clamps every value.
- Self-harm signals always become Critical / Immediate and never fade on their own.
- Every alert shows the exact phrases that triggered it, so counsellors can check the AI's reasoning.
- Messages are treated as data, not instructions (prompt-injection guard).
- An accuracy test against a hand-written answer key measures the prompt (`backend/eval/`).
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
