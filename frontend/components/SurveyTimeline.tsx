import type { SurveyStages } from "../lib/study";
import { studyPageUrl } from "../lib/studySelection";

export default function SurveyTimeline({ stages, onChange }: { stages: SurveyStages; onChange: (value: SurveyStages) => void }) {
  const positions: Record<string, string> = { pre_quiz: "Before the base quiz", post_base: "After the base quiz",
    post_followup: "After Follow-up Questions", post_double: "After Dual Agent", post_links: "After Embedded Links" };
  function enableAll(enabled: boolean) {
    onChange(Object.fromEntries(Object.entries(stages).map(([key, value]) => [key, { ...value, enabled }])));
  }
  return <section aria-labelledby="survey-schedule-title" className="rounded-xl border bg-white p-5 shadow-sm">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="survey-schedule-title" className="text-lg font-semibold">Survey schedule</h2>
      <div className="flex gap-2"><button type="button" onClick={() => enableAll(true)} className="rounded-lg border px-3 py-2 text-sm">Enable all</button>
        <button type="button" onClick={() => enableAll(false)} className="rounded-lg border px-3 py-2 text-sm">Disable all</button></div>
    </div>
    <p className="mt-2 text-sm text-gray-600">Names are for admins only. Participants see neutral survey numbers. Changes apply to new enrollments; existing schedules stay saved. Admin previews use these settings immediately after saving.</p>
    <ol className="mt-4 space-y-3">{Object.entries(stages).map(([key, value]) => <li key={key} className="flex flex-wrap items-center gap-3 rounded-xl border p-4">
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.enabled} aria-label={`Enable ${key}`} onChange={e => onChange({ ...stages, [key]: { ...value, enabled: e.target.checked } })} />{positions[key] ?? key}</label>
      <input aria-label={`Admin name for ${key}`} value={value.name} maxLength={120} required onChange={e => onChange({ ...stages, [key]: { ...value, name: e.target.value } })} className="min-w-48 flex-1 rounded-lg border px-3 py-2 text-sm" />
      <a className="text-sm font-medium text-blue-700 underline" href={studyPageUrl(`/surveys_panel?stage=${key}`)}>Edit questions</a>
    </li>)}</ol>
    <p className="mt-3 text-xs text-gray-500">Post-variant surveys follow their quiz type as the order rotates. The last quiz’s survey is also optional; disabling it ends the journey at that quiz.</p>
  </section>;
}
