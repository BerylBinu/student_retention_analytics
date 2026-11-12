import Link from "next/link";
import { api, label, riskStyle, formatDate, type Stats, type Student } from "@/lib/api";
import { AiBriefing } from "@/components/AiBriefing";
import { Avatar, BarList, Card, Donut, ErrorBox, Icon, RiskBadge, STRESSOR_COLOR, StatCard } from "@/components/ui";

function levelFor(score: number) {
  if (score >= 80) return "CRITICAL";
  if (score >= 60) return "HIGH";
  if (score >= 30) return "MEDIUM";
  return "LOW";
}

export default async function OverviewPage() {
  let stats: Stats;
  let students: Student[];
  try {
    const [s, list] = await Promise.all([api<Stats>("/stats"), api<{ items: Student[] }>("/students")]);
    stats = s;
    students = list.items;
  } catch (e) {
    return <ErrorBox message={(e as Error).message} />;
  }

  const priority = students.filter((s) => s.current_risk_level === "CRITICAL" || s.current_risk_level === "HIGH").slice(0, 5);
  const levelOrder = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
  const byLevel = levelOrder.map((lv) => ({
    key: lv,
    name: label(lv),
    count: stats.students_by_risk_level.find((r) => r.level === lv)?.count ?? 0,
  }));

  return (
    <div className="space-y-6">
      {/* Hero */}
      <section className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-600 via-indigo-700 to-violet-700 p-6 text-white shadow-lg sm:p-8">
        <div className="absolute -right-16 -top-16 h-56 w-56 rounded-full bg-white/10" />
        <div className="absolute -bottom-20 right-24 h-40 w-40 rounded-full bg-white/5" />
        <div className="relative">
          <p className="text-sm font-medium text-indigo-200">Student Retention Analytics</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">
            {stats.students_needing_attention} students need support right now
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-indigo-100">
            Gemini AI read {stats.total_signals} unstructured messages from LMS forums, support tickets, emails and the campus chatbot,
            and flagged the students showing early signs of dropping out.
          </p>
          <Link
            href="/students"
            className="mt-5 inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-indigo-700 shadow hover:bg-indigo-50"
          >
            Review at-risk students <Icon name="arrow" className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {stats.self_harm_alerts > 0 && (
        <Link
          href="/students"
          className="flex items-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900 hover:bg-red-100"
        >
          <Icon name="heart" className="h-5 w-5 shrink-0 text-red-600" />
          <span>
            <span className="font-semibold">
              {stats.self_harm_alerts} student{stats.self_harm_alerts > 1 ? "s" : ""} flagged for possible self-harm risk.
            </span>{" "}
            Please review and arrange wellbeing contact today.
          </span>
        </Link>
      )}

      <AiBriefing />

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard title="Students monitored" value={stats.total_students} hint={`${stats.total_signals} messages analysed`} icon="users" />
        <StatCard title="Need attention" value={stats.students_needing_attention} hint="High or critical risk" icon="alert" tone="orange" />
        <StatCard
          title="Self-harm alerts"
          value={stats.self_harm_alerts}
          hint={stats.self_harm_alerts ? "Contact today" : "None right now"}
          icon="heart"
          tone={stats.self_harm_alerts ? "red" : "emerald"}
        />
        <StatCard title="Average risk" value={stats.average_risk_score} hint="Score out of 100" icon="gauge" />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Priority list */}
        <Card title="Priority students" subtitle="Highest risk first, with the AI's recommended next step" className="lg:col-span-3">
          {priority.length === 0 ? (
            <p className="text-sm text-slate-500">No high or critical risk students right now.</p>
          ) : (
            <ul className="-mx-2 space-y-1">
              {priority.map((s) => (
                <li key={s.student_id}>
                  <Link href={`/students/${s.student_id}`} className="flex items-center gap-3 rounded-xl px-2 py-2.5 hover:bg-slate-50">
                    <Avatar name={s.student_name} level={s.current_risk_level} />
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900">
                        {s.student_name}
                        <span className="text-xs font-normal text-slate-400">{s.student_id}</span>
                        {s.self_harm_flag && (
                          <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-800">Wellbeing alert</span>
                        )}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-slate-500">{s.recommended_action}</p>
                    </div>
                    <RiskBadge level={s.current_risk_level} score={s.current_risk_score} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <Link href="/students" className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-600 hover:text-indigo-800">
            See all {stats.total_students} students <Icon name="arrow" className="h-4 w-4" />
          </Link>
        </Card>

        {/* Risk distribution */}
        <Card title="Students by risk level" subtitle="Based on each student's most recent message" className="lg:col-span-2">
          <Donut rows={byLevel} centerLabel="students" />
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="What students are struggling with" subtitle="Main stressor the AI found in each message">
          <BarList
            rows={stats.signals_by_stressor.map((r) => ({ name: label(r.stressor), key: r.stressor, count: r.count }))}
            colorFor={(k) => STRESSOR_COLOR[k] ?? "bg-slate-400"}
          />
        </Card>
        <Card title="Where the signals came from" subtitle="Unstructured sources feeding the data lake">
          <div className="grid grid-cols-2 gap-3">
            {stats.signals_by_source.map((r) => (
              <div key={r.source} className="rounded-xl bg-slate-50 p-4 ring-1 ring-slate-100">
                <p className="text-2xl font-bold tabular-nums text-slate-900">{r.count}</p>
                <p className="mt-0.5 text-sm text-slate-500">{label(r.source)}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Daily risk timeline */}
      <Card title="Risk signals over time" subtitle="Average risk score of messages each day. Hover a bar for details.">
        {stats.timeline.length === 0 ? (
          <p className="text-sm text-slate-500">No data yet.</p>
        ) : (
          <>
            <div className="relative h-52">
              {[80, 60, 30].map((v) => (
                <div key={v} className="absolute inset-x-0 border-t border-dashed border-slate-200" style={{ bottom: `${v}%` }}>
                  <span className="absolute -top-2.5 right-0 bg-white pl-1 text-[10px] text-slate-400">{v}</span>
                </div>
              ))}
              <div className="relative flex h-full items-end gap-1.5 border-b border-slate-200 pr-6">
                {stats.timeline.map((d) => (
                  <div key={d.date} className="group relative flex h-full flex-1 items-end">
                    <div
                      className={`w-full rounded-t-md opacity-90 transition group-hover:opacity-100 ${riskStyle(levelFor(d.avg_risk_score)).bar}`}
                      style={{ height: `${Math.max(3, d.avg_risk_score)}%` }}
                    />
                    <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs text-white shadow-lg group-hover:block">
                      {formatDate(d.date)}: avg {d.avg_risk_score}, {d.signals} message{d.signals === 1 ? "" : "s"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-2 flex justify-between pr-6 text-xs text-slate-400">
              <span>{formatDate(stats.timeline[0].date)}</span>
              <span>{formatDate(stats.timeline[stats.timeline.length - 1].date)}</span>
            </div>
          </>
        )}
      </Card>

      <p className="text-xs text-slate-400">
        Updated {formatDate(stats.generated_at)}. Risk levels: Low 0-29, Medium 30-59, High 60-79, Critical 80-100.
      </p>
    </div>
  );
}