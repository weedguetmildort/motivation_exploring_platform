import type { SurveyStages } from "../lib/study";
import type { SurveyDraft } from "../lib/surveyEditor";
import { questionTarget, targetFields } from "../lib/surveyConfig";

export default function SurveyItemFields({ value, onChange, settings, editing = false }: {
  value: SurveyDraft; onChange: (value: SurveyDraft) => void; settings: SurveyStages; editing?: boolean;
}) {
  const target = questionTarget(value);
  const fieldClass = "w-full rounded-lg border px-3 py-2 text-sm";
  const update = (patch: Partial<SurveyDraft>) => onChange({ ...value, ...patch });
  const scale = (patch: Partial<SurveyDraft["scale"]>) => update({ scale: { ...value.scale, ...patch } });
  return <div className="space-y-4">
    <div className="grid gap-4 sm:grid-cols-3">
      <label className="text-sm">Stage<select aria-label={editing ? "Edit question target" : "Question target"} value={target} onChange={e => update(targetFields(e.target.value))} className={fieldClass}>
        <option value="all_surveys">All surveys in this study</option><option value="post_quiz">All post-quiz surveys</option>
        {Object.entries(settings).map(([key, setting]) => <option key={key} value={key}>{setting.name}</option>)}
      </select></label>
      <label className="text-sm">Type<select aria-label={editing ? "Edit question type" : "Question type"} value={value.type} onChange={e => update({ type: e.target.value as SurveyDraft["type"] })} className={fieldClass}>
        <option value="likert">Likert (1–5)</option><option value="single_select">Single select</option>
      </select></label>
      <label className="text-sm">Category<input value={value.category} onChange={e => update({ category: e.target.value })} placeholder={editing ? undefined : "e.g., TRUST, NFC, AI Literacy"} className={fieldClass} /></label>
    </div>
    {Object.keys(settings).includes(target) && <fieldset className="rounded-lg border p-4"><legend className="text-sm">Also include in these surveys</legend>
      <div className="flex flex-wrap gap-4">{Object.entries(settings).filter(([key]) => key !== target).map(([key, setting]) => <label key={key} className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={value.stages?.includes(key) ?? false} onChange={e => update({ stages: e.target.checked ? [...(value.stages ?? []), key] : (value.stages ?? []).filter(stage => stage !== key) })} />{setting.name}
      </label>)}</div>
    </fieldset>}
    <label className="block text-sm">Prompt<textarea aria-label={editing ? "Edit question prompt" : "Question prompt"} value={value.prompt} onChange={e => update({ prompt: e.target.value })} rows={3} required className={fieldClass} /></label>
    {value.type === "likert" ? <>
      <div className="grid gap-4 sm:grid-cols-2">{["Left label", "Right label"].map((label, index) => <label key={label} className="text-sm">{label}<input value={value.scale.anchors?.[index] ?? ""} onChange={e => {
        const anchors = [...(value.scale.anchors ?? ["", ""])]; anchors[index] = e.target.value; scale({ anchors });
      }} className={fieldClass} /></label>)}</div>
      <div className="grid gap-4 sm:grid-cols-2">{(["min", "max"] as const).map(key => <label key={key} className="text-sm">{key === "min" ? "Min" : "Max"}<input type="number" value={value.scale[key]} onChange={e => scale({ [key]: Number(e.target.value) })} className={fieldClass} /></label>)}</div>
    </> : <fieldset className="rounded-lg border bg-gray-50 p-4"><legend className="text-sm">Options (at least 2)</legend><div className="grid gap-2 sm:grid-cols-2">
      {value.options.map((option, index) => <label key={option.id} className="text-sm">Option {option.id.toUpperCase()}<input value={option.label} onChange={e => update({ options: value.options.map((entry, position) => position === index ? { ...entry, label: e.target.value } : entry) })} className={fieldClass} /></label>)}
    </div></fieldset>}
    <div className="flex flex-wrap gap-4 text-sm">
      <label><input id={editing ? undefined : "required"} type="checkbox" checked={value.required} onChange={e => update({ required: e.target.checked })} /> Required</label>
      <label><input id={editing ? undefined : "reverse"} type="checkbox" checked={value.reverse_scored} onChange={e => update({ reverse_scored: e.target.checked })} /> Reverse-scored (R)</label>
      {editing && <label><input type="checkbox" checked={value.active} onChange={e => update({ active: e.target.checked })} /> Active</label>}
    </div>
  </div>;
}
