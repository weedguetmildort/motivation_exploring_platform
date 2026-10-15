import { useState } from "react";
import { formatMetric, type Comparison, type Metric, type MetricDefinition } from "../lib/researchResults";

export function MetricValue({ metric, definition }: { metric?: Metric; definition: MetricDefinition }) {
  const people = metric?.participant_count ?? 0;
  const questions = metric?.observation_count ?? 0;
  return <div>
    <span className="font-semibold tabular-nums">{formatMetric(metric?.value, definition.unit)}</span>
    <div className="text-xs text-gray-500 whitespace-nowrap">{people} {people === 1 ? "person" : "people"} · {questions} {questions === 1 ? "question" : "questions"}</div>
    {metric?.denominator != null && metric.denominator > 0 && <div className="text-xs text-gray-500" title="Combined counts across participants; the displayed average weights each participant equally.">
      Combined: {Number.isInteger(metric.numerator) ? metric.numerator : metric.numerator?.toFixed(1)} / {Number.isInteger(metric.denominator) ? metric.denominator : metric.denominator.toFixed(1)}
      {definition.key.endsWith("_click_rate") ? " opportunities" : definition.key.endsWith("_share") ? " ms" : ""}
    </div>}
  </div>;
}
export default function ResearchComparison({ overall, variants, definitions }: { overall: Comparison; variants: Comparison[]; definitions: MetricDefinition[] }) {
  const [group, setGroup] = useState("Performance");
  const [pointerUnit, setPointerUnit] = useState("percent");
  const groups = [...new Set(definitions.map(d => d.group))];
  const columns = definitions.filter(d => d.group === group && (group !== "Pointer regions" || d.unit === pointerUnit));
  return <div>
    <div className="flex flex-wrap gap-2 mb-4" role="group" aria-label="Metric categories">
      {groups.map(name => <button key={name} type="button" aria-pressed={group === name} onClick={() => setGroup(name)} className={`rounded-full px-3 py-1.5 text-sm border ${group === name ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-700"}`}>{name}</button>)}
    </div>
    {group === "Pointer regions" && <label className="flex items-center gap-2 mb-3 text-sm">Pointer measurement<select value={pointerUnit} onChange={e => setPointerUnit(e.target.value)} className="rounded border p-2"><option value="percent">Share of observed pointer time</option><option value="seconds">Average time per question</option></select></label>}
    {group === "Verification" && <p className="mb-3 text-sm text-gray-600">Prompt categories use exploratory keyword labels. One prompt may have several labels; review the original messages before drawing conclusions.</p>}
    {group === "Pointer regions" && <p className="mb-3 text-sm text-gray-600">Pointer time measures cursor location while the page is visible and focused. It does not measure gaze or reading. People with no observed pointer time do not contribute to pointer shares.</p>}
    <div className="overflow-x-auto"><table className="w-full text-sm text-left">
      <caption className="text-left text-xs text-gray-500 pb-3">Each person contributes equally. Counts vary by available and eligible measurements. Combined counts describe the underlying observations.</caption>
      <thead><tr><th className="p-3 border-b">Quiz type</th><th className="p-3 border-b">People / answered</th>{columns.map(d => <th key={d.key} className="p-3 border-b min-w-[155px]">{d.label}</th>)}</tr></thead>
      <tbody>{[{ ...overall, quiz_id: "All selected quizzes" }, ...variants].map(row => <tr key={row.quiz_id} className="border-b last:border-0">
        <th className="p-3 font-medium whitespace-nowrap">{row.quiz_id}</th><td className="p-3 tabular-nums">{row.participant_count} / {row.questions_answered}</td>
        {columns.map(d => <td key={d.key} className="p-3"><MetricValue metric={row.metrics[d.key]} definition={d} /></td>)}
      </tr>)}</tbody>
    </table></div>
  </div>;
}
