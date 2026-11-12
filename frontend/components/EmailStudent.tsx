import { Icon } from "@/components/ui";

// Demo-safe email domain. The student IDs in our mock data look like real APU TP numbers, so we never
// build a real university address: a click during a demo must not email an actual student.
// In a real deployment, the student's address would come from the university's student directory.
const STUDENT_EMAIL_DOMAIN = "student.example.edu";

// One gentle, non-judgemental line per stressor. The email never mentions risk scores, the AI or the
// messages we analysed: it simply offers help with the kind of problem the student is facing.
const STRESSOR_LINE: Record<string, string> = {
  FINANCIAL:
    "If money is making things harder at the moment, we can go through the support that's available together, such as instalment plans and financial assistance.",
  ACADEMIC_PRESSURE:
    "If your coursework feels like a lot right now, we can help you plan a way forward, including extensions or extra academic support where appropriate.",
  BURNOUT_MENTAL_HEALTH:
    "University can be exhausting at times, and our counselling team is here if you'd like someone to talk to.",
  SOCIAL_ISOLATION:
    "Settling in isn't always easy, and we'd be glad to help you connect with student clubs, peer mentors or other support on campus.",
  TECHNOLOGY_ACCESS:
    "If you're having trouble with a laptop or internet access, we can help you find an equipment loan or access to the campus labs.",
  FAMILY_PERSONAL:
    "If things at home are difficult right now, we can help with options such as a deferral or a lighter study load while you deal with them.",
  HEALTH_PHYSICAL:
    "If your health is affecting your studies, we can help arrange support or adjustments with your lecturers.",
  HOUSING_TRANSPORT:
    "If travel or accommodation is getting in the way, we can look at options together, including support with attendance arrangements.",
};

function firstName(fullName: string): string {
  return (fullName || "").trim().split(/\s+/)[0] || "there";
}

function draftEmail(name: string, stressors: string[]) {
  const main = stressors.find((s) => STRESSOR_LINE[s]);
  const lines = [
    `Hi ${firstName(name)},`,
    "",
    "I hope you're doing well. I'm reaching out from Student Support to check in and see how things are going this semester.",
    "",
    ...(main ? [STRESSOR_LINE[main], ""] : []),
    "If you'd like to talk, just reply to this email and we can set up a short meeting, in person or online, at a time that suits you.",
    "",
    "Kind regards,",
    "Student Support Team",
  ];
  return { subject: "Checking in from Student Support", body: lines.join("\n") };
}

export function EmailStudent({
  studentId,
  studentName,
  stressors,
  selfHarm,
}: {
  studentId: string;
  studentName: string;
  stressors: string[];
  selfHarm: boolean;
}) {
  const to = `${studentId}@${STUDENT_EMAIL_DOMAIN}`;
  const { subject, body } = draftEmail(studentName, stressors);
  const mailto = `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  const gmail =
    "https://mail.google.com/mail/?view=cm&fs=1" +
    `&to=${encodeURIComponent(to)}&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;

  return (
    <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/60 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-indigo-700">Reach out</p>
      {selfHarm && (
        <p className="mt-2 text-sm font-medium text-red-800">
          Possible self-harm risk: call or meet the student in person today. Use email only as a follow-up.
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <a
          href={mailto}
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
        >
          <Icon name="mail" className="h-4 w-4" />
          Email {firstName(studentName)}
        </a>
        <a
          href={gmail}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-50"
        >
          Open in Gmail
        </a>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Opens a draft to <span className="font-medium text-slate-700">{to}</span> for you to review and edit. Nothing is
        sent until you press Send.
      </p>
    </div>
  );
}
