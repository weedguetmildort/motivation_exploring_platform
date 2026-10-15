import { useState } from "react";
import { formatMetric, type Comparison, type Metric, type MetricDefinition } from "../lib/researchResults";

export function MetricValue({ metric, definition }: { metric?: Metric; definition: MetricDefinition }) {
  const people = metric?.participant_count ?? 0;
  const questions = metric?.observation_count ?? 0;
  const questionLabel = definition.key === "accuracy" ? (questions === 1 ? "graded answer" : "graded answers")
    : definition.key === "telemetry_coverage" ? (questions === 1 ? "shown question" : "shown questions")
    : questions === 1 ? "question" : "questions";
  return <div>
    <span className="font-semibold tabular-nums">{formatMetric(metric?.value, definition.unit)}</span>
    <div className="text-xs text-gray-500 whitespace-nowrap">{people} {people === 1 ? "person" : "people"} · {questions} {questionLabel}</div>
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
    {(overall.answers_missing_grade > 0 || overall.incomplete_completed_attempt_count > 0) && <aside aria-label="Result completeness" className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 space-y-1">
      {overall.answers_missing_grade > 0 && <p>{overall.answers_missing_grade} submitted {overall.answers_missing_grade === 1 ? "answer has" : "answers have"} no recoverable grade and {overall.answers_missing_grade === 1 ? "is" : "are"} excluded from accuracy.</p>}
      {overall.incomplete_completed_attempt_count > 0 && <p>{overall.incomplete_completed_attempt_count} completed quiz {overall.incomplete_completed_attempt_count === 1 ? "record has" : "records have"} missing answers. Older records may refer to questions that are no longer available; completed status alone does not mean every question was answered.</p>}
    </aside>}
    <div className="flex flex-wrap gap-2 mb-4" role="group" aria-label="Metric categories">
      {groups.map(name => <button key={name} type="button" aria-pressed={group === name} onClick={() => setGroup(name)} className={`rounded-full px-3 py-1.5 text-sm border ${group === name ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-700"}`}>{name}</button>)}
    </div>
    {group === "Pointer regions" && <label className="flex items-center gap-2 mb-3 text-sm">Pointer measurement<select value={pointerUnit} onChange={e => setPointerUnit(e.target.value)} className="rounded border p-2"><option value="percent">Share of observed pointer time</option><option value="seconds">Average time per question</option></select></label>}
    {group === "Verification" && <p className="mb-3 text-sm text-gray-600">Prompt categories use exploratory keyword labels. One prompt may have several labels; review the original messages before drawing conclusions.</p>}
    {group === "Pointer regions" && <p className="mb-3 text-sm text-gray-600">Pointer time measures cursor location while the page is visible and focused. It does not measure gaze or reading. People with no observed pointer time do not contribute to pointer shares.</p>}
    <div className="overflow-x-auto"><table className="w-full text-sm text-left">
      <caption className="text-left text-xs text-gray-500 pb-3">Each person contributes equally. Accuracy uses graded answers; telemetry coverage uses shown questions. Other measurements use their eligible questions. All selected quizzes combines the quiz attempts matching the filters.</caption>
      <thead><tr><th className="p-3 border-b">Quiz type</th><th className="p-3 border-b">People / quiz attempts</th><th className="p-3 border-b">Answered / graded</th>{columns.map(d => <th key={d.key} className="p-3 border-b min-w-[155px]">{d.label}</th>)}</tr></thead>
      <tbody>{[{ ...overall, quiz_id: "All selected quizzes" }, ...variants].map(row => <tr key={row.quiz_id} className="border-b last:border-0">
        <th className="p-3 font-medium whitespace-nowrap">{row.quiz_id}</th><td className="p-3 tabular-nums whitespace-nowrap">{row.participant_count} / {row.attempt_count}<div className="text-xs text-gray-500">{row.completed_attempt_count} completed</div></td>
        <td className="p-3 tabular-nums whitespace-nowrap">{row.questions_answered} / {row.questions_graded}<div className="text-xs text-gray-500">{row.questions_assigned} assigned · {row.questions_shown} shown</div></td>
        {columns.map(d => <td key={d.key} className="p-3"><MetricValue metric={row.metrics[d.key]} definition={d} /></td>)}
      </tr>)}</tbody>
    </table></div>
  </div>;
}
