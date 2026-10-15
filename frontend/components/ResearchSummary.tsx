import { useEffect, useState } from "react";
import { apiFetch } from "../lib/fetcher";

type Summary = {
  participant_id: string; attempt_id: string; quiz_id: string; attempt_status: string;
  questions_assigned: number; questions_answered: number; accuracy: number | null;
  wrong_ai_exposure_questions: number; wrong_ai_agreement_rate: number | null;
  telemetry_questions: number; questions_with_quality_flags: number;
  median_active_ms: number | null; suggestion_click_rate: number | null; reference_click_rate: number | null;
};
const percentage = (value: number | null) => value == null ? "—" : `${(value * 100).toFixed(1)}%`;

export default function ResearchSummary() {
  const [rows, setRows] = useState<Summary[]>([]);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    apiFetch<{ variants: Summary[] }>("/api/export/research-summary")
      .then(data => { if (!cancelled) setRows(data.variants); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);
  if (loading) return <p>Loading research analytics…</p>;
  if (error) return <p role="alert">Unable to load research analytics.</p>;
  return <div>
    <p className="mb-4 text-sm text-gray-600">AI agreement means the submitted answer matched an incorrect AI recommendation that appeared on screen. It does not establish that AI changed the student’s mind. Pointer time describes cursor location. A dash means unavailable or ineligible. Test accounts and reset attempts are excluded.</p>
    {!rows.length ? <p>No research attempts yet.</p> : <div className="overflow-x-auto"><table className="w-full text-sm text-left">
      <thead><tr>{["Participant", "Quiz", "Answered", "Accuracy", "Wrong AI agreement", "Wrong AI opportunities", "Median active time", "Suggestions used", "References opened", "Tracked questions", "Quality flags"].map(label => <th key={label} className="p-2 border-b">{label}</th>)}</tr></thead>
      <tbody>{rows.map(row => <tr key={row.attempt_id}>
        <td className="p-2 border-b">{row.participant_id}</td><td className="p-2 border-b">{row.quiz_id} ({row.attempt_status})</td>
        <td className="p-2 border-b">{row.questions_answered}/{row.questions_assigned}</td><td className="p-2 border-b">{percentage(row.accuracy)}</td>
        <td className="p-2 border-b">{percentage(row.wrong_ai_agreement_rate)}</td><td className="p-2 border-b">{row.wrong_ai_exposure_questions}</td>
        <td className="p-2 border-b">{row.median_active_ms == null ? "—" : `${(row.median_active_ms / 1000).toFixed(1)}s`}</td>
        <td className="p-2 border-b">{percentage(row.suggestion_click_rate)}</td><td className="p-2 border-b">{percentage(row.reference_click_rate)}</td>
        <td className="p-2 border-b">{row.telemetry_questions}/{row.questions_assigned}</td><td className="p-2 border-b">{row.questions_with_quality_flags}</td>
      </tr>)}</tbody>
    </table></div>}
  </div>;
}
