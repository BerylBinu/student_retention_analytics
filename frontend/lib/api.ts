// Talks to the team's AWS API. The address comes from .env.local.
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL;

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (!BASE) throw new Error("NEXT_PUBLIC_API_BASE_URL is not set in .env.local");
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

// ---------- Data shapes (match backend/src/api/app.py) ----------

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface Student {
  student_id: string;
  student_name: string;
  signal_count: number;
  current_risk_score: number;
  current_risk_level: RiskLevel;
  latest_risk_score: number;
  average_risk_score: number;
  trend: "NEW" | "RISING" | "FALLING" | "STABLE";
  top_stressors: string[];
  self_harm_flag: boolean;
  highest_urgency: string;
  recommended_action: string;
  latest_summary: string;
  first_event_time: string;
  latest_event_time: string;
  sources: string[];
}

export interface Insight {
  record_id: string;
  student_id: string;
  student_name: string;
  source_system: string;
  risk_score: number;
  risk_level: RiskLevel;
  primary_stressor: string;
  secondary_stressors: string[];
  sentiment: string;
  summary: string;
  evidence: string[];
  recommended_action: string;
  urgency: string;
  self_harm_indicator: boolean;
  event_time: string;
  event_date: string;
  raw_text: string;
  s3_uri: string;
  processed_at: string;
  model: string;
}

export interface StudentDetail extends Student {
  timeline: Insight[];
}

export interface Stats {
  total_signals: number;
  total_students: number;
  students_needing_attention: number;
  self_harm_alerts: number;
  average_risk_score: number;
  signals_by_risk_level: { level: RiskLevel; count: number }[];
  students_by_risk_level: { level: RiskLevel; count: number }[];
  signals_by_stressor: { stressor: string; count: number }[];
  signals_by_source: { source: string; count: number }[];
  timeline: { date: string; signals: number; avg_risk_score: number; high_or_critical: number }[];
  generated_at: string;
}

// ---------- Friendly labels and colours ----------

const LABELS: Record<string, string> = {
  FINANCIAL: "Financial",
  ACADEMIC_PRESSURE: "Academic pressure",
  BURNOUT_MENTAL_HEALTH: "Burnout / mental health",
  SOCIAL_ISOLATION: "Social isolation",
  TECHNOLOGY_ACCESS: "Technology access",
  FAMILY_PERSONAL: "Family / personal",
  HEALTH_PHYSICAL: "Physical health",
  HOUSING_TRANSPORT: "Housing / transport",
  NONE: "None",
  LMS_FORUM: "LMS forum",
  SUPPORT_TICKET: "Support ticket",
  EMAIL: "Email",
  CHATBOT: "Chatbot",
  OTHER: "Other",
  ROUTINE: "Routine",
  FOLLOW_UP_THIS_WEEK: "Follow up this week",
  CONTACT_WITHIN_24H: "Contact within 24h",
  IMMEDIATE: "Immediate",
  NEW: "New",
  RISING: "Rising",
  FALLING: "Falling",
  STABLE: "Stable",
  POSITIVE: "Positive",
  NEUTRAL: "Neutral",
  NEGATIVE: "Negative",
  MIXED: "Mixed",
};

export function label(value: string | undefined | null): string {
  if (!value) return "-";
  return LABELS[value] ?? value.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

// Tailwind classes for each risk level: badge, solid bar, soft background
export const RISK_STYLE: Record<RiskLevel, { badge: string; bar: string; text: string }> = {
  LOW: { badge: "bg-emerald-100 text-emerald-800 ring-emerald-200", bar: "bg-emerald-500", text: "text-emerald-700" },
  MEDIUM: { badge: "bg-amber-100 text-amber-800 ring-amber-200", bar: "bg-amber-400", text: "text-amber-700" },
  HIGH: { badge: "bg-orange-100 text-orange-800 ring-orange-200", bar: "bg-orange-500", text: "text-orange-700" },
  CRITICAL: { badge: "bg-red-100 text-red-800 ring-red-200", bar: "bg-red-600", text: "text-red-700" },
};

export function riskStyle(level: string) {
  return RISK_STYLE[(level as RiskLevel)] ?? RISK_STYLE.LOW;
}

export function formatDate(iso: string | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-MY", { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(iso: string | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-MY", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Asia/Kuala_Lumpur",
  });
}

export const TREND_ICON: Record<string, string> = {
  RISING: "\u2191",
  FALLING: "\u2193",
  STABLE: "\u2192",
  NEW: "\u2022",
};