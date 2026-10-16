import type { Enrollment } from "./StudyShell";
import type { StudyId } from "../lib/studySelection";

type Props = { studies: Enrollment[]; current: StudyId; busy: boolean; onSelect: (study: Enrollment) => void };

export default function AdminStudySelector({ studies, current, busy, onSelect }: Props) {
  return <section aria-labelledby="study-workspace-title" className="rounded-2xl border bg-white p-6 shadow-sm">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <h2 id="study-workspace-title" className="text-lg font-semibold text-gray-900">Study workspace</h2>
      <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600">Admin only</span>
    </div>
    <p className="mb-5 text-sm text-gray-600">Choose the study to preview and manage. Progress below belongs to your own account; participant results are in the admin panel.</p>
    <div className="grid gap-4 sm:grid-cols-2">
      {studies.map(study => <div key={study.study_id} className={`rounded-xl border p-5 ${study.study_id === current ? "border-blue-500 bg-blue-50" : "border-gray-200"}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold text-gray-900">{study.label}</h3>
          {study.study_id === current && <span className="text-xs font-semibold text-blue-700">Current workspace</span>}
        </div>
        <p className="mt-2 text-sm text-gray-600">{study.study_id === "study-1" ? "Open participation" : "Interview · approval required"}</p>
        <p className="mt-3 text-sm text-gray-700">Preview progress: {study.finished ? "Completed" : study.total_steps ? `${study.completed_steps} of ${study.total_steps} steps` : "Ready to start"}</p>
        <button type="button" disabled={busy || !study.available || study.study_id === current} onClick={() => onSelect(study)}
          className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-default disabled:bg-gray-100 disabled:text-gray-500">
          {study.study_id === current ? "Selected" : `Open ${study.label}`}
        </button>
      </div>)}
    </div>
  </section>;
}
