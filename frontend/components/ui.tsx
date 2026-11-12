import { label, riskStyle } from "@/lib/api";

// ---------- Icons (simple line icons, no library needed) ----------
const ICONS: Record<string, string> = {
  grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  users: "M16 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6M22 19v-1a4 4 0 0 0-3-3.87M16 4.13a3 3 0 0 1 0 5.74",
  bolt: "M13 2 4 14h7l-1 8 9-12h-7z",
  alert: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0",
  heart: "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8",
  gauge: "M12 14l4-4M3.3 17a9 9 0 1 1 17.4 0",
  mail: "M4 4h16v16H4zM22 6l-10 7L2 6",
  chart: "M3 3v18h18M7 14l4-4 4 4 5-5",
  arrow: "M5 12h14M13 6l6 6-6 6",
};

export function Icon({ name, className = "h-5 w-5" }: { name: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d={ICONS[name] ?? ICONS.grid} />
    </svg>
  );
}

// ---------- Colours ----------
export const STRESSOR_COLOR: Record<string, string> = {
  FINANCIAL: "bg-amber-500",
  ACADEMIC_PRESSURE: "bg-indigo-500",
  BURNOUT_MENTAL_HEALTH: "bg-rose-500",
  SOCIAL_ISOLATION: "bg-violet-500",
  TECHNOLOGY_ACCESS: "bg-sky-500",
  FAMILY_PERSONAL: "bg-pink-500",
  HEALTH_PHYSICAL: "bg-teal-500",
  HOUSING_TRANSPORT: "bg-orange-500",
};

const RISK_HEX: Record<string, string> = { LOW: "#10b981", MEDIUM: "#f59e0b", HIGH: "#f97316", CRITICAL: "#dc2626" };
export function riskHex(level: string) {
  return RISK_HEX[level] ?? "#6366f1";
}

// ---------- Small building blocks ----------
export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-slate-500">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function RiskBadge({ level, score }: { level: string; score?: number }) {
  const s = riskStyle(level);
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${s.badge}`}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: riskHex(level) }} />
      {score !== undefined && <span className="tabular-nums">{score}</span>}
      {label(level)}
    </span>
  );
}

export function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 ring-1 ring-inset ring-slate-200">
      {children}
    </span>
  );
}

export function StressorChip({ value }: { value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-white px-2 py-0.5 text-xs font-medium text-slate-700 ring-1 ring-inset ring-slate-200">
      <span className={`h-2 w-2 rounded-full ${STRESSOR_COLOR[value] ?? "bg-slate-400"}`} />
      {label(value)}
    </span>
  );
}

export function Avatar({ name, level, size = "md" }: { name: string; level?: string; size?: "md" | "lg" }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  const dim = size === "lg" ? "h-14 w-14 text-lg" : "h-9 w-9 text-xs";
  return (
    <span
      className={`grid shrink-0 place-items-center rounded-full font-semibold text-white ring-2 ring-white ${dim}`}
      style={{ background: level ? riskHex(level) : "#6366f1" }}
    >
      {initials || "?"}
    </span>
  );
}

export function Card({
  title,
  subtitle,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200/70 ${className}`}>
      {title && (
        <div className="mb-5">
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatCard({
  title,
  value,
  hint,
  icon,
  tone = "indigo",
}: {
  title: string;
  value: string | number;
  hint?: string;
  icon: string;
  tone?: "indigo" | "orange" | "red" | "emerald";
}) {
  const tones = {
    indigo: "bg-indigo-50 text-indigo-600",
    orange: "bg-orange-50 text-orange-600",
    red: "bg-red-50 text-red-600",
    emerald: "bg-emerald-50 text-emerald-600",
  };
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200/70">
      <div className="flex items-start justify-between">
        <p className="text-sm font-medium text-slate-500">{title}</p>
        <span className={`grid h-9 w-9 place-items-center rounded-xl ${tones[tone]}`}>
          <Icon name={icon} className="h-4.5 w-4.5" />
        </span>
      </div>
      <p className="mt-3 text-3xl font-bold tabular-nums text-slate-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

// Horizontal bar chart. No extra library needed.
export function BarList({
  rows,
  colorFor,
}: {
  rows: { name: string; count: number; key?: string }[];
  colorFor?: (key: string) => string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  if (rows.length === 0) return <p className="text-sm text-slate-500">No data yet.</p>;
  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.key ?? r.name} className="text-sm">
          <div className="mb-1 flex justify-between">
            <span className="text-slate-600">{r.name}</span>
            <span className="font-semibold tabular-nums text-slate-900">{r.count}</span>
          </div>
          <div className="h-2 rounded-full bg-slate-100">
            <div
              className={`h-2 rounded-full ${colorFor ? colorFor(r.key ?? r.name) : "bg-indigo-500"}`}
              style={{ width: `${(r.count / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

// Donut chart drawn with SVG circles.
export function Donut({ rows, centerLabel }: { rows: { key: string; name: string; count: number }[]; centerLabel: string }) {
  const total = rows.reduce((a, r) => a + r.count, 0);
  const R = 52;
  const C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg viewBox="0 0 140 140" className="h-36 w-36 -rotate-90">
        <circle cx="70" cy="70" r={R} fill="none" stroke="#f1f5f9" strokeWidth="18" />
        {total > 0 &&
          rows.map((r) => {
            const len = (r.count / total) * C;
            const el = (
              <circle
                key={r.key}
                cx="70"
                cy="70"
                r={R}
                fill="none"
                stroke={riskHex(r.key)}
                strokeWidth="18"
                strokeDasharray={`${len} ${C - len}`}
                strokeDashoffset={-offset}
              />
            );
            offset += len;
            return el;
          })}
        <g className="rotate-90" style={{ transformOrigin: "70px 70px" }}>
          <text x="70" y="68" textAnchor="middle" fontSize="26" fontWeight="700" fill="#0f172a">
            {total}
          </text>
          <text x="70" y="86" textAnchor="middle" fontSize="10" fill="#64748b">
            {centerLabel}
          </text>
        </g>
      </svg>
      <ul className="space-y-2 text-sm">
        {rows.map((r) => (
          <li key={r.key} className="flex items-center gap-2.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: riskHex(r.key) }} />
            <span className="w-16 text-slate-600">{r.name}</span>
            <span className="font-semibold tabular-nums">{r.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
      <p className="font-semibold">Could not load data from the API.</p>
      <p className="mt-1 break-words">{message}</p>
      <p className="mt-2 text-red-700">
        Check that <code>.env.local</code> has the right address, then stop and restart <code>npm run dev</code>.
      </p>
    </div>
  );
}

// Calm, clear alert for possible self-harm. No flashing, no alarming wording.
export function SafetyBanner({ action }: { action?: string }) {
  return (
    <div className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm">
      <Icon name="heart" className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
      <div>
        <p className="font-semibold text-red-900">Possible risk of self-harm: prioritise wellbeing contact</p>
        <p className="mt-1 text-red-800">
          {action || "Contact the student today and connect them with campus counselling services."}
        </p>
      </div>
    </div>
  );
}
// Counsellor follow-up status. "New message" means the student wrote again after the last update.
const CASE_STYLE: Record<string, string> = {
  OPEN: "bg-slate-100 text-slate-700 ring-slate-200",
  CONTACTED: "bg-sky-100 text-sky-800 ring-sky-200",
  RESOLVED: "bg-emerald-100 text-emerald-800 ring-emerald-200",
};

export function CaseBadge({ status, newMessage }: { status?: string; newMessage?: boolean }) {
  const s = status || "OPEN";
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${CASE_STYLE[s] ?? CASE_STYLE.OPEN}`}>
        {label(s)}
      </span>
      {newMessage && (
        <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-inset ring-amber-200">
          New message
        </span>
      )}
    </span>
  );
}
