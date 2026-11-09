import Link from "next/link";
import { api, label, formatDate, formatDateTime, riskStyle, TREND_ICON, type StudentDetail } from "@/lib/api";
import { Avatar, riskHex, Card, Chip, ErrorBox, RiskBadge, SafetyBanner, StressorChip } from "@/components/ui";

export default async function StudentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let s: StudentDetail;
  try {
    s = await api<StudentDetail>(`/students/${encodeURIComponent(id)}`);
  } catch (e) {
    return (
      <div className="space-y-4">
        <BackLink />
        <ErrorBox message={(e as Error).message} />
      </div>
    );
  }

  const timeline = s.timeline ?? [];
  const newestFirst = [...timeline].reverse();

  return (
    <div className="space-y-6">
      <BackLink />

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200/70">
        <div className="flex items-center gap-4">
        <Avatar name={s.student_name} level={s.current_risk_level} size="lg" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{s.student_name}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {s.student_id} &middot; {s.signal_count} message{s.signal_count === 1 ? "" : "s"} since {formatDate(s.first_event_time)}
          </p>
          <div className="mt-2 flex flex-wrap gap-1">
            {s.sources.map((src) => (
              <Chip key={src}>{label(src)}</Chip>
            ))}
          </div>
        </div>
        </div>
        <div className="text-right">
          <p className={`text-5xl font-semibold tabular-nums ${riskStyle(s.current_risk_level).text}`}>{s.current_risk_score}</p>
          <div className="mt-1 flex items-center justify-end gap-2">
            <RiskBadge level={s.current_risk_level} />
            <span className="text-sm text-slate-500">
              {TREND_ICON[s.trend]} {label(s.trend)}
            </span>
          </div>
        </div>
      </div>

      {s.self_harm_flag && <SafetyBanner action={s.recommended_action} />}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Recommended next step" className="lg:col-span-2">
          <p className="text-base text-slate-900">{s.recommended_action || "-"}</p>
          <dl className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
            <Info term="Urgency" value={label(s.highest_urgency)} />
            <Info term="Latest score" value={String(s.latest_risk_score)} />
            <Info term="Average score" value={String(s.average_risk_score)} />
          </dl>
          <div className="mt-5 border-t border-slate-100 pt-4">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Latest AI summary</p>
            <p className="mt-1 text-sm text-slate-700">{s.latest_summary || "-"}</p>
          </div>
          <div className="mt-4">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Main stressors</p>
            <div className="mt-1.5 flex flex-wrap gap-1">
              {s.top_stressors.length ? s.top_stressors.map((t) => <StressorChip key={t} value={t} />) : <span className="text-sm text-slate-400">None detected</span>}
            </div>
          </div>
        </Card>

        <Card title="Risk over time">
          <RiskChart points={timeline.map((t) => ({ score: t.risk_score, date: t.event_time, level: t.risk_level }))} />
        </Card>
      </div>

      {/* Timeline */}
      <Card title="Message timeline (newest first)">
        <ol className="space-y-4">
          {newestFirst.map((t) => (
            <li key={t.record_id} className="rounded-xl border border-slate-200 border-l-4 p-4" style={{ borderLeftColor: riskHex(t.risk_level) }}>
              <div className="flex flex-wrap items-center gap-2">
                <RiskBadge level={t.risk_level} score={t.risk_score} />
                <span className="text-sm font-medium text-slate-900">{label(t.primary_stressor)}</span>
                <span className="text-xs text-slate-400">
                  {label(t.source_system)} &middot; {formatDateTime(t.event_time)} &middot; {label(t.sentiment)}
                </span>
                {t.self_harm_indicator && (
                  <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-semibold text-red-800">Self-harm indicator</span>
                )}
              </div>
              <p className="mt-2 text-sm text-slate-700">{t.summary}</p>
              {t.evidence?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {t.evidence.map((e, i) => (
                    <span key={i} className="rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs text-amber-900">
                      &ldquo;{e}&rdquo;
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-2 text-xs text-slate-500">
                <span className="font-medium">Suggested:</span> {t.recommended_action} ({label(t.urgency)})
              </p>
              {t.raw_text && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs font-medium text-indigo-600">Show original message</summary>
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs text-slate-600">{t.raw_text}</pre>
                </details>
              )}
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/students" className="text-sm font-medium text-indigo-600 hover:underline">
      &larr; All students
    </Link>
  );
}

function Info({ term, value }: { term: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{term}</dt>
      <dd className="mt-0.5 font-medium text-slate-900">{value}</dd>
    </div>
  );
}

// Small line chart of each message's risk score, drawn with plain SVG.
function RiskChart({ points }: { points: { score: number; date: string; level: string }[] }) {
  if (points.length === 0) return <p className="text-sm text-slate-500">No data.</p>;
  const W = 300;
  const H = 160;
  const pad = 14;
  const x = (i: number) => (points.length === 1 ? W / 2 : pad + (i * (W - 2 * pad)) / (points.length - 1));
  const y = (v: number) => H - pad - (v / 100) * (H - 2 * pad);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.score)}`).join(" ");
  const dot: Record<string, string> = { LOW: "#10b981", MEDIUM: "#f59e0b", HIGH: "#f97316", CRITICAL: "#dc2626" };

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {[80, 60, 30].map((v) => (
          <g key={v}>
            <line x1={pad} x2={W - pad} y1={y(v)} y2={y(v)} stroke="#e2e8f0" strokeDasharray="3 3" />
            <text x={W - pad} y={y(v) - 3} textAnchor="end" fontSize="9" fill="#94a3b8">
              {v}
            </text>
          </g>
        ))}
        <path d={path} fill="none" stroke="#6366f1" strokeWidth="2" />
        {points.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.score)} r="4.5" fill={dot[p.level] ?? "#6366f1"} stroke="white" strokeWidth="1.5">
            <title>{`${formatDate(p.date)}: ${p.score}`}</title>
          </circle>
        ))}
      </svg>
      <div className="mt-1 flex justify-between text-xs text-slate-400">
        <span>{formatDate(points[0].date)}</span>
        {points.length > 1 && <span>{formatDate(points[points.length - 1].date)}</span>}
      </div>
    </div>
  );
}