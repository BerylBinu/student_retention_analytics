"use client";

import { useState } from "react";
import Link from "next/link";
import { api, label, type Insight } from "@/lib/api";
import { Card, Chip, PageHeader, RiskBadge, SafetyBanner } from "@/components/ui";

// Ready-made messages for the demo video (same stories as backend/mock_data/samples/live_demo)
const PRESETS = [
  {
    name: "Aisyah: thinking of deferring",
    student_id: "TP071234",
    student_name: "Aisyah Rahman",
    source: "EMAIL",
    text:
      "Hi, I'm thinking of deferring next semester. I can't keep up with work and classes, the bursary said instalments are not possible for my case. I failed the cloud quiz yesterday. I don't know what else to do. Aisyah",
  },
  {
    name: "Chen Wei: feeling better",
    student_id: "TP072210",
    student_name: "Chen Wei",
    source: "LMS_FORUM",
    text:
      "Thank you to the peer mentor programme, I joined the Chinese students' society and found a group for SE. Feeling much better now.",
  },
  {
    name: "Priya: chatbot crisis",
    student_id: "TP070455",
    student_name: "Priya Nair",
    source: "CHATBOT",
    text:
      "Student: is there a way to just stop everything\nBot: I'm not sure I understand. Do you mean withdraw from your programme?\nStudent: i dont know. i feel like nothing i do matters and i don't see the point of anything anymore",
  },
];

const SOURCES = ["EMAIL", "LMS_FORUM", "SUPPORT_TICKET", "CHATBOT", "OTHER"];
const POLL_EVERY_MS = 4000;
const GIVE_UP_AFTER_MS = 180000;

type Phase = "idle" | "sending" | "waiting" | "done" | "error";

export default function DemoPage() {
  const [form, setForm] = useState({ student_id: "", student_name: "", source: "EMAIL", text: "" });
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<Insight | null>(null);
  const [seconds, setSeconds] = useState(0);

  const busy = phase === "sending" || phase === "waiting";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.text.trim()) return;
    setPhase("sending");
    setError("");
    setResult(null);
    setSeconds(0);

    try {
      const queued = await api<{ status: string; s3_key: string }>("/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_id: form.student_id.trim().toUpperCase(),
          student_name: form.student_name.trim(),
          source: form.source,
          text: form.text.trim(),
        }),
      });

      setPhase("waiting");
      const started = Date.now();
      const query = form.student_id.trim()
        ? `/insights?student_id=${encodeURIComponent(form.student_id.trim().toUpperCase())}&limit=100`
        : "/insights?limit=1000";

      while (Date.now() - started < GIVE_UP_AFTER_MS) {
        await new Promise((r) => setTimeout(r, POLL_EVERY_MS));
        setSeconds(Math.round((Date.now() - started) / 1000));
        const res = await api<{ items: Insight[] }>(query);
        const match = res.items.find((i) => i.s3_uri?.endsWith(queued.s3_key));
        if (match) {
          setResult(match);
          setPhase("done");
          return;
        }
      }
      throw new Error("The AI has not finished after 3 minutes. Check the Students page in a moment, or ask Person A to check the pipeline.");
    } catch (err) {
      setError((err as Error).message);
      setPhase("error");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Live demo: analyse a new message"
        subtitle="Sends a message into the AWS pipeline (S3, Lambda, Gemini, DynamoDB) and shows the AI result when it is ready."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="New message">
          <div className="mb-4 flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.name}
                type="button"
                disabled={busy}
                onClick={() => setForm({ student_id: p.student_id, student_name: p.student_name, source: p.source, text: p.text })}
                className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50"
              >
                {p.name}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Student ID">
                <input
                  value={form.student_id}
                  onChange={(e) => setForm({ ...form, student_id: e.target.value })}
                  placeholder="TP071234"
                  className={inputCls}
                />
              </Field>
              <Field label="Student name">
                <input
                  value={form.student_name}
                  onChange={(e) => setForm({ ...form, student_name: e.target.value })}
                  placeholder="Aisyah Rahman"
                  className={inputCls}
                />
              </Field>
            </div>
            <Field label="Source">
              <select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} className={inputCls}>
                {SOURCES.map((s) => (
                  <option key={s} value={s}>
                    {label(s)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Message">
              <textarea
                value={form.text}
                onChange={(e) => setForm({ ...form, text: e.target.value })}
                rows={7}
                placeholder="Paste a student message, email or forum post..."
                className={inputCls}
              />
            </Field>
            <button
              type="submit"
              disabled={busy || !form.text.trim()}
              className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {phase === "sending" ? "Sending..." : phase === "waiting" ? "AI is analysing..." : "Analyse message"}
            </button>
          </form>
        </Card>

        <Card title="AI result">
          {phase === "idle" && <p className="text-sm text-slate-500">Pick a ready-made message or type your own, then press Analyse.</p>}

          {busy && (
            <div className="space-y-3 text-sm">
              <Step done={phase === "waiting"} text="Message uploaded to the S3 data lake" />
              <Step done={false} active={phase === "waiting"} text={`Gemini is reading the message (${seconds}s)`} />
              <Step done={false} text="Result saved to DynamoDB" />
              <p className="pt-2 text-xs text-slate-400">This usually takes 10 to 60 seconds.</p>
            </div>
          )}

          {phase === "error" && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}

          {phase === "done" && result && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <RiskBadge level={result.risk_level} score={result.risk_score} />
                <span className="text-sm font-medium">{label(result.primary_stressor)}</span>
                <span className="text-xs text-slate-400">{label(result.sentiment)} sentiment</span>
              </div>
              {result.self_harm_indicator && <SafetyBanner action={result.recommended_action} />}
              <p className="text-sm text-slate-700">{result.summary}</p>
              {result.evidence?.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {result.evidence.map((e, i) => (
                    <span key={i} className="rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs text-amber-900">
                      &ldquo;{e}&rdquo;
                    </span>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap gap-1">
                {result.secondary_stressors?.map((s) => <Chip key={s}>{label(s)}</Chip>)}
              </div>
              <p className="text-sm">
                <span className="font-medium">Recommended:</span> {result.recommended_action}{" "}
                <span className="text-slate-500">({label(result.urgency)})</span>
              </p>
              {result.student_id && (
                <Link
                  href={`/students/${result.student_id}`}
                  className="inline-block rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
                >
                  Open {result.student_name || result.student_id}&apos;s profile &rarr;
                </Link>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

const inputCls =
  "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100";

function Field({ label: text, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-600">{text}</span>
      {children}
    </label>
  );
}

function Step({ text, done, active }: { text: string; done: boolean; active?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className={`grid h-5 w-5 place-items-center rounded-full text-xs ${
          done ? "bg-emerald-500 text-white" : active ? "animate-pulse bg-indigo-500 text-white" : "bg-slate-200 text-slate-400"
        }`}
      >
        {done ? "\u2713" : ""}
      </span>
      <span className={done || active ? "text-slate-900" : "text-slate-400"}>{text}</span>
    </div>
  );
}