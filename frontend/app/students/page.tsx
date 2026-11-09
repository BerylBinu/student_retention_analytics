import { api, type Student } from "@/lib/api";
import { ErrorBox, PageHeader } from "@/components/ui";
import StudentTable from "./StudentTable";

export default async function StudentsPage() {
  let students: Student[];
  try {
    students = (await api<{ items: Student[] }>("/students")).items;
  } catch (e) {
    return <ErrorBox message={(e as Error).message} />;
  }

  return (
    <div>
      <PageHeader
        title="At-risk students"
        subtitle="Ranked by current risk, based on each student's most recent message. Anyone flagged for possible self-harm stays critical until a counsellor follows up."
      />
      <StudentTable students={students} />
    </div>
  );
}