"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, formatDateTime, label, type CaseEvent, type CaseStatus as Status } from "@/lib/api";
import { CaseBadge } from "@/components/ui";

const STATUSES: { value: Status; hint: string }[] = [
  { value: "OPEN", hint: "Still needs contact" },
  { value: "CONTACTED", hint: "Reached out, waiting or in progress" },
  { value: "RESOLVED", hint: "Support in place" },
];

// Lets a counsellor record what they did about a student. Saved to the API (Firestore "cases"
// collection); the AI's risk score is never changed by this.
export function CaseStatus({
  studentId,
  status,
  note,
  updatedAt,
  newMessage,
  history,
}: {
  studentId: string;
  status: Status;
  note: string;
  updatedAt?: string;
  newMessage?: boolean;
  history: CaseEvent[];
}) {
  const router = useRouter();
  const [choice, setChoice] = useState<Status>(status);
  const [text, setText] = useState(note);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  async function save() {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await api(`/students/${encodeURIComponent(studentId)}/case`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: choice, note: text }),
      });
      setSaved(true);
      router.refresh(); // reload the page data so the badge and history update
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <span>Current:</span>
          <CaseBadge status={status} newMessage={newMessage} />
          {updatedAt && <span className="text-xs text-slate-400">updated {formatDateTime(updatedAt)}</span>}
        </div>
        {newMessage && (
          <p className="mt-2 text-sm text-amber-800">
            The student has sent a new message since this was last updated. Please review it below.
          </p>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          {STATUSES.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => setChoice(s.value)}
              title={s.hint}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ring-1 ring-inset ${
                choice === s.value ? "bg-slate-900 text-white ring-slate-900" : "bg-white text-slate-700 ring-slate-200 hover:bg-slate-50"
              }`}
            >
              {label(s.value)}
            </button>
          ))}
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, 500))}
          rows={3}
          placeholder="Short note, e.g. Called student, meeting on Friday about instalment plan"
          className="mt-3 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
        />
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60"
          >
            {saving ? "Saving..." : "Save follow-up"}
          </button>
          <span className="text-xs text-slate-400">{text.length}/500</span>
          {saved && !error && <span className="text-sm text-emerald-700">Saved</span>}
          {error && <span className="text-sm text-red-700">Could not save: {error}</span>}
        </div>
      </div>

      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">History</p>
        {history.length === 0 ? (
          <p className="mt-2 text-sm text-slate-400">No follow-up recorded yet.</p>
        ) : (
          <ol className="mt-2 space-y-3">
            {history.slice(0, 6).map((h, i) => (
              <li key={i} className="border-l-2 border-slate-200 pl-3">
                <div className="flex flex-wrap items-center gap-2">
                  <CaseBadge status={h.status} />
                  <span className="text-xs text-slate-400">{formatDateTime(h.at)}</span>
                </div>
                {h.note && <p className="mt-1 text-sm text-slate-700">{h.note}</p>}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
