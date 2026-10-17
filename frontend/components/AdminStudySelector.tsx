import type { Enrollment } from "./StudyShell";
import { DEFAULT_ACCESS_POLICY, type StudyId, type StudyAccessPolicy } from "../lib/studySelection";

type Props = { studies: Enrollment[]; current: StudyId; busy: boolean; onSelect: (study: Enrollment) => void;
  isAdmin?: boolean; policy?: StudyAccessPolicy };

export default function AdminStudySelector({ studies, current, busy, onSelect, isAdmin = true, policy = DEFAULT_ACCESS_POLICY }: Props) {
  return <section aria-labelledby="study-workspace-title" className="rounded-2xl border bg-white p-6 shadow-sm">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <h2 id="study-workspace-title" className="text-lg font-semibold text-gray-900">{isAdmin ? "Study workspace" : "Choose a study"}</h2>
      <span className="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600">{isAdmin ? "Admin only" : "Progress saved separately"}</span>
    </div>
    <p className="mb-5 text-sm text-gray-600">{isAdmin ? "Choose the study to preview and manage. Progress below belongs to your own account; participant results are in the admin panel." : "You can complete the studies in either order. Choose a study to start or resume."}</p>
    <div className="grid gap-4 sm:grid-cols-2">
      {studies.map(study => <div key={study.study_id} className={`rounded-xl border p-5 ${study.study_id === current ? "border-blue-500 bg-blue-50" : "border-gray-200"}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold text-gray-900">{study.label}</h3>
          {study.study_id === current && <span className="text-xs font-semibold text-blue-700">{isAdmin ? "Current workspace" : "Current study"}</span>}
        </div>
        <p className="mt-2 text-sm text-gray-600">{study.study_id === "study-1" ? "Open participation" :
          [policy.requires_study1_completion && "Complete Study 1 first", policy.requires_approval && "Approval required"].filter(Boolean).join(" · ") || "Open participation"}</p>
        <p className="mt-3 text-sm text-gray-700">{isAdmin ? "Preview progress: " : "Progress: "}{study.finished ? "Completed" : study.total_steps ? `${study.completed_steps} of ${study.total_steps} steps` : "Ready to start"}</p>
        {!study.available && study.reason && <p className="mt-2 text-sm text-gray-600">{study.reason}</p>}
        <button type="button" disabled={busy || !study.available || study.study_id === current} onClick={() => onSelect(study)}
          className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-default disabled:bg-gray-100 disabled:text-gray-500">
          {study.study_id === current ? "Selected" : !study.available ? "Locked" : `Open ${study.label}`}
        </button>
      </div>)}
    </div>
  </section>;
}
