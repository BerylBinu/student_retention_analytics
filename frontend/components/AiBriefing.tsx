"use client";

import { useEffect, useState } from "react";
import { api, formatDateTime, type Briefing } from "@/lib/api";

// Loads after the rest of the Overview, so the page never waits on Gemini. The API only asks Gemini again
// when the data has changed; otherwise it returns the saved briefing instantly.
export function AiBriefing() {
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api<Briefing>("/briefing")
      .then((b) => active && setBriefing(b))
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, []);

  if (error) return null; // the briefing is a bonus: hide it rather than show an error

  return (
    <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-indigo-100">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-indigo-700">
          <span className="inline-block h-2 w-2 rounded-full bg-indigo-500" />
          {briefing?.source === "summary" ? "Today's briefing" : "AI briefing for counsellors"}
        </p>
        {briefing && (
          <p className="text-xs text-slate-400">
            {briefing.source === "ai" ? "Written by Gemini from the analysed messages" : "Summary of the latest numbers"}
            {briefing.generated_at ? ` · ${formatDateTime(briefing.generated_at)}` : ""}
          </p>
        )}
      </div>

      {!briefing ? (
        <div className="mt-4 space-y-2" aria-label="Loading briefing">
          <div className="h-5 w-2/3 animate-pulse rounded bg-slate-100" />
          <div className="h-4 w-full animate-pulse rounded bg-slate-100" />
          <div className="h-4 w-5/6 animate-pulse rounded bg-slate-100" />
          <p className="pt-1 text-xs text-slate-400">Gemini is reading the latest results...</p>
        </div>
      ) : (
        <>
          <h2 className="mt-3 text-lg font-semibold text-slate-900">{briefing.headline}</h2>
          {briefing.points.length > 0 && (
            <ul className="mt-3 space-y-2">
              {briefing.points.map((p, i) => (
                <li key={i} className="flex gap-3 text-sm text-slate-700">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400" />
                  <span>{p}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 text-xs text-slate-400">
            AI-generated to help prioritise. Always check the student&apos;s messages before acting.
          </p>
        </>
      )}
    </section>
  );
}
