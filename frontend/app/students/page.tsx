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
        subtitle="Ranked by risk. A student's score is their most serious warning sign, so one urgent message is enough to reach out."
      />
      <StudentTable students={students} />
    </div>
  );
}