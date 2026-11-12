"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { label, formatDate, riskStyle, TREND_ICON, type Student } from "@/lib/api";
import { Avatar, CaseBadge, RiskBadge, StressorChip } from "@/components/ui";

const FILTERS = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

export default function StudentTable({ students }: { students: Student[] }) {
  const router = useRouter();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("ALL");
  const [query, setQuery] = useState("");
  const [followUpOnly, setFollowUpOnly] = useState(false);

  // High / critical students nobody has acted on yet (or who wrote again after being contacted)
  const needsFollowUp = (s: Student) =>
    (s.current_risk_level === "HIGH" || s.current_risk_level === "CRITICAL") && (s.needs_follow_up ?? true);
  const followUpCount = students.filter(needsFollowUp).length;

  const q = query.trim().toLowerCase();
  const rows = students.filter(
    (s) =>
      (filter === "ALL" || s.current_risk_level === filter) &&
      (!followUpOnly || needsFollowUp(s)) &&
      (!q || s.student_name.toLowerCase().includes(q) || s.student_id.toLowerCase().includes(q)),
  );

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/70">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4">
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => {
            const count = f === "ALL" ? students.length : students.filter((s) => s.current_risk_level === f).length;
            const active = filter === f;
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset ${
                  active ? "bg-slate-900 text-white ring-slate-900" : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
                }`}
              >
                {f === "ALL" ? "All" : label(f)} ({count})
              </button>
            );
          })}
          <button
            onClick={() => setFollowUpOnly(!followUpOnly)}
            className={`rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset ${
              followUpOnly ? "bg-amber-500 text-white ring-amber-500" : "bg-amber-50 text-amber-800 ring-amber-200 hover:bg-amber-100"
            }`}
          >
            Needs follow-up ({followUpCount})
          </button>
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search name or ID"
          className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 sm:w-56"
        />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead>
            <tr className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3 font-medium">Student</th>
              <th className="px-4 py-3 font-medium">Risk</th>
              <th className="px-4 py-3 font-medium">Trend</th>
              <th className="px-4 py-3 font-medium">Main stressors</th>
              <th className="px-4 py-3 font-medium">Urgency</th>
              <th className="px-4 py-3 font-medium">Follow-up</th>
              <th className="px-4 py-3 font-medium">Last signal</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((s) => (
              <tr
                key={s.student_id}
                onClick={() => router.push(`/students/${s.student_id}`)}
                className="cursor-pointer hover:bg-slate-50"
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <Avatar name={s.student_name} level={s.current_risk_level} />
                    <div>
                      <p className="font-semibold text-slate-900">{s.student_name}</p>
                      <p className="text-xs text-slate-400">
                        {s.student_id} &middot; {s.signal_count} message{s.signal_count === 1 ? "" : "s"}
                      </p>
                      {s.self_harm_flag && (
                        <p className="mt-0.5 text-xs font-semibold text-red-700">Wellbeing alert</p>
                      )}
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <RiskBadge level={s.current_risk_level} score={s.current_risk_score} />
                  <div className="mt-1.5 h-1.5 w-24 rounded-full bg-slate-100">
                    <div
                      className={`h-1.5 rounded-full ${riskStyle(s.current_risk_level).bar}`}
                      style={{ width: `${s.current_risk_score}%` }}
                    />
                  </div>
                </td>
                <td className="px-4 py-3 text-slate-600">
                  <span className={s.trend === "RISING" ? "font-medium text-red-700" : s.trend === "FALLING" ? "text-emerald-700" : ""}>
                    {TREND_ICON[s.trend]} {label(s.trend)}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {s.top_stressors.length ? s.top_stressors.map((t) => <StressorChip key={t} value={t} />) : <span className="text-slate-400">-</span>}
                  </div>
                </td>
                <td className="px-4 py-3 text-slate-600">{label(s.highest_urgency)}</td>
                <td className="px-4 py-3">
                  <CaseBadge status={s.case_status} newMessage={s.case_new_message} />
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-slate-500">{formatDate(s.latest_event_time)}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-slate-500">
                  No students match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}