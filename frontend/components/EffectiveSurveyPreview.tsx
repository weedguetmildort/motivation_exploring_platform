import { useEffect, useState } from "react";
import { getSurveyPreview, type SurveyItem } from "../lib/surveys";
import type { SurveyStages } from "../lib/study";

export default function EffectiveSurveyPreview({ settings, stage, onStageChange, revision }: {
  settings: SurveyStages; stage: string; onStageChange: (stage: string) => void; revision: unknown;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<SurveyItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true); setError("");
    getSurveyPreview(stage).then(result => { if (!cancelled) setItems(result); })
      .catch(() => { if (!cancelled) setError("Could not load the effective survey."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, stage, revision]);
  return <section aria-label="Effective survey preview" className="mb-6 rounded-xl border bg-white p-6 shadow-sm">
    <h2 className="text-lg font-semibold">Effective survey preview</h2>
    <p className="mt-1 text-sm text-gray-600">Includes active shared questions and additions for this stage. Already opened surveys keep their saved questions.</p>
    {stage === "post_variant" && <p className="mt-2 text-sm text-gray-600">This admin preview includes additions for every possible variant. Participants see additions only for the variants assigned to them.</p>}
    <label className="mt-3 block text-sm">Preview survey<select aria-label="Preview survey" value={stage} onChange={e => onStageChange(e.target.value)} className="ml-3 rounded border p-2">{Object.entries(settings).map(([key, item]) => <option key={key} value={key}>{item.name}{item.enabled ? "" : " (disabled for new enrollments)"}</option>)}</select></label>
    <p className="mt-3 text-sm">{settings[stage]?.enabled ? "Enabled" : "Disabled"}</p>
    <button type="button" onClick={() => setOpen(value => !value)} aria-expanded={open} className="mt-3 rounded-lg border px-3 py-2 text-sm">{open ? "Hide preview" : "Preview effective survey"}</button>
    {open && (loading ? <p role="status">Loading preview…</p> : error ? <p role="alert">{error}</p> : <>
      <p className="mt-3 text-sm">{items.length} active questions</p>
      <ol className="mt-3 list-inside list-decimal space-y-2">{items.map(item => <li key={item.id}>{item.prompt}{item.required ? " (required)" : " (optional)"}</li>)}</ol>
    </>)}
  </section>;
}
