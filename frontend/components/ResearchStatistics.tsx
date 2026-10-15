import { useEffect, useState } from "react";
import { apiFetch } from "../lib/fetcher";

type Pair = { study_id?: string; metric: string; left: string; right: string; paired_participants: number; difference: number | null;
  participant_bootstrap_95_interval: [number, number] | null; p_exploratory: number | null; p_holm: number | null };
type Association = { study_id?: string; quiz_id: string; item_prompt: string; metric: string; participants: number; spearman_rho: number | null;
  participant_bootstrap_95_interval: [number, number] | null };
type Statistics = { paired: { comparisons: Pair[]; limitations: string[] }; surveys: { associations: Association[]; limitations: string } };
type Validation = { human_agreement: { dimension: string; n: number; agreement: number | null; kappa: number | null; reviewer_a: string; reviewer_b: string }[];
  model_validation: { dimension: string; model: string; n: number; agreement: number | null; abstentions: number;
    classes: { label: string; support: number; precision: number | null; recall: number | null }[] }[]; limitations: string };
const number = (value: number | null, digits = 3) => value == null ? "—" : value.toFixed(digits);
const difference = (value: number | null) => value == null ? "—" : `${(value * 100).toFixed(1)} pp`;

export default function ResearchStatistics({ query, includeTests, includeArchived }: { query: string; includeTests: boolean; includeArchived: boolean }) {
  const [requestedQuery, setRequestedQuery] = useState<string | null>(null);
  const [data, setData] = useState<Statistics | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setData(null); setValidation(null); setError(null); setLoading(false);
    if (requestedQuery !== query) return () => controller.abort();
    setLoading(true);
    Promise.all([apiFetch<Statistics>(`/api/research/statistics?${query}`, { signal: controller.signal }),
      apiFetch<Validation>(`/api/research/coding/validation?include_tests=${includeTests}&include_archived=${includeArchived}&study=${new URLSearchParams(query).get("study") ?? "study-1"}`, { signal: controller.signal })])
      .then(([statistics, report]) => { if (!controller.signal.aborted) { setData(statistics); setValidation(report); } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to compute analysis."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [query, requestedQuery, includeTests, includeArchived, refresh]);
  return <section aria-label="Research analysis" className="rounded-xl border p-4 space-y-4">
    <h2 className="font-semibold text-lg">Paired comparisons and coding validation</h2>
    <p className="text-sm text-gray-600">Comparisons use the current participant and study filters, match each student across rotated variants, and exclude retakes and incomplete attempts. Base is always first and is omitted from these comparisons. Coding validation covers the included account types and reset setting across the study, independently of demographic filters.</p>
    <button type="button" disabled={loading} onClick={() => { setRequestedQuery(query); setRefresh(v => v + 1); }} className="rounded border px-4 py-2 text-sm disabled:opacity-50">{loading ? "Computing analysis…" : "Compute research analysis"}</button>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {data && <>
      <h3 className="font-medium">Exploratory paired effects</h3>
      <p className="text-xs text-gray-600">Differences and intervals are percentage points, left minus right. Effects stay within each study; protocols are not pooled. Each student contributes equally. Holm-adjusted p-values cover the displayed accuracy and wrong-AI comparison family; they do not turn an exploratory analysis into a preregistered result.</p>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{["Outcome", "Comparison", "Paired students", "Difference", "95% bootstrap interval", "Exploratory p", "Holm p"].map(label => <th key={label} className="p-2 border-b">{label}</th>)}</tr></thead><tbody>{data.paired.comparisons.map(row => <tr key={`${row.study_id}:${row.metric}:${row.left}:${row.right}`} className="border-b">
        <td className="p-2">{row.metric.replaceAll("_", " ")}</td><td className="p-2">{row.left} − {row.right}</td><td className="p-2">{row.paired_participants}</td><td className="p-2">{difference(row.difference)}</td><td className="p-2">{row.participant_bootstrap_95_interval?.map(difference).join(" to ") ?? "—"}</td><td className="p-2">{number(row.p_exploratory)}</td><td className="p-2">{number(row.p_holm)}</td>
      </tr>)}</tbody></table></div>
      {!data.paired.comparisons.length && <p className="text-sm">No rotated-variant comparisons are available for these filters.</p>}
      <details><summary className="cursor-pointer text-sm">Analysis assumptions and exclusions</summary><ul className="list-disc pl-5 text-sm mt-2">{data.paired.limitations.map(text => <li key={text}>{text}</li>)}</ul></details>
      <h3 className="font-medium">Survey–behavior associations</h3><p className="text-xs text-gray-600">{data.surveys.limitations}</p>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{["Quiz", "Survey item", "Behavior", "Students", "Spearman correlation", "95% bootstrap interval"].map(label => <th key={label} className="p-2 border-b">{label}</th>)}</tr></thead><tbody>{data.surveys.associations.map((row, index) => <tr key={index} className="border-b"><td className="p-2">{row.study_id ? `${row.study_id} · ` : ""}{row.quiz_id}</td><td className="p-2">{row.item_prompt}</td><td className="p-2">{row.metric.replaceAll("_", " ")}</td><td className="p-2">{row.participants}</td><td className="p-2">{number(row.spearman_rho)}</td><td className="p-2">{row.participant_bootstrap_95_interval?.map(v => number(v)).join(" to ") ?? "—"}</td></tr>)}</tbody></table></div>
      {!data.surveys.associations.length && <p className="text-sm">No matching completed Likert responses and quiz measurements are available.</p>}
    </>}
    {validation && <>
      <h3 className="font-medium">Independent coding validation</h3><p className="text-xs text-gray-600">{validation.limitations}</p>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{["Dimension", "Reviewer pair", "Questions", "Agreement", "Cohen’s kappa"].map(label => <th key={label} className="p-2 border-b">{label}</th>)}</tr></thead><tbody>{validation.human_agreement.map((row, i) => <tr key={i} className="border-b"><td className="p-2">{row.dimension.replaceAll("_", " ")}</td><td className="p-2">{row.reviewer_a.slice(0, 8)} / {row.reviewer_b.slice(0, 8)}</td><td className="p-2">{row.n}</td><td className="p-2">{number(row.agreement)}</td><td className="p-2">{number(row.kappa)}</td></tr>)}</tbody></table></div>
      {!validation.human_agreement.length && <p className="text-sm">Two independent reviewers must code holdout conversations before agreement can be measured.</p>}
      {validation.model_validation.map(row => <details key={`${row.model}:${row.dimension}`}><summary className="cursor-pointer text-sm">{row.model} · {row.dimension.replaceAll("_", " ")} · {row.n} questions · agreement {number(row.agreement)} · {row.abstentions} abstentions</summary><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{["Label", "Human support", "Precision", "Recall"].map(label => <th key={label} className="p-2 border-b">{label}</th>)}</tr></thead><tbody>{row.classes.map(label => <tr key={label.label}><td className="p-2">{label.label.replaceAll("_", " ")}</td><td className="p-2">{label.support}</td><td className="p-2">{number(label.precision)}</td><td className="p-2">{number(label.recall)}</td></tr>)}</tbody></table></div></details>)}
    </>}
  </section>;
}
