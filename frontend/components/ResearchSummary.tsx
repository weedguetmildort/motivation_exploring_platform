import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../lib/fetcher";
import { demographicLabel, formatMetric, type Results } from "../lib/researchResults";
import ResearchComparison, { MetricValue } from "./ResearchComparison";
import ResearchParticipant from "./ResearchParticipant";
import ResearchStatistics from "./ResearchStatistics";

export default function ResearchSummary() {
  const [data, setData] = useState<Results | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [ageMin, setAgeMin] = useState("");
  const [ageMax, setAgeMax] = useState("");
  const [quiz, setQuiz] = useState("");
  const [status, setStatus] = useState("completed");
  const [version, setVersion] = useState("");
  const [questionSet, setQuestionSet] = useState("");
  const [position, setPosition] = useState("");
  const [includeTests, setIncludeTests] = useState(false);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const detail = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const timer = setTimeout(() => { setSearch(searchInput.trim()); setPage(1); }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);
  const parameters = new URLSearchParams({ filters: JSON.stringify(filters), search, status, page: String(page), include_tests: String(includeTests), include_archived: String(includeArchived) });
  for (const [key, value] of Object.entries({ age_min: ageMin, age_max: ageMax, quiz_id: quiz, version, question_set: questionSet, variant_position: position })) if (value) parameters.set(key, value);
  const query = parameters.toString();
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(null);
    apiFetch<Results>(`/api/research/results?${query}`, { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) { setData(result); setPage(result.page); } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to load research results."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [query, refresh]);
  function reset() {
    setFilters({}); setSearchInput(""); setSearch(""); setAgeMin(""); setAgeMax(""); setQuiz("");
    setStatus("completed"); setVersion(""); setQuestionSet(""); setPosition(""); setIncludeTests(false); setIncludeArchived(false); setPage(1); setSelected(null);
  }
  function setFilter(key: string, value: string) {
    setFilters(previous => { const next = { ...previous }; if (value) next[key] = value; else delete next[key]; return next; });
    setPage(1); setSelected(null);
  }
  const inputClass = "mt-1 w-full rounded-lg border border-gray-300 bg-white p-2 text-sm";
  function demographicSelect(facet: Results["facets"][number]) {
    return <label key={facet.key} className="text-sm">{facet.label}
      <select value={filters[facet.key] ?? ""} onChange={e => setFilter(facet.key, e.target.value)} className={inputClass}>
        <option value="">All responses</option>{facet.options.map(option => <option key={option.value} value={option.value}>{demographicLabel(facet.key, option.value)} ({option.count})</option>)}
        <option value="__missing__">Not provided ({facet.missing_count})</option>
      </select>
    </label>;
  }
  return <div className="space-y-6">
    <p className="text-sm text-gray-600">AI agreement means a submitted answer matched an AI recommendation that appeared on screen. It does not establish that AI changed the student’s mind. A dash means unavailable or ineligible.</p>
    <section aria-label="Participant and study filters" className="rounded-xl border bg-gray-50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4"><h2 className="font-semibold text-lg">Filter participants and results</h2><div className="flex gap-2"><button type="button" onClick={reset} className="rounded border bg-white px-3 py-2 text-sm">Reset filters</button><button type="button" onClick={() => setRefresh(v => v + 1)} className="rounded border bg-white px-3 py-2 text-sm">Refresh results</button></div></div>
      <label className="block text-sm font-medium">Search name, email, or participant ID
        <input type="search" value={searchInput} onChange={e => { setSearchInput(e.target.value); setSelected(null); }} placeholder="Find a participant…" className={inputClass} />
      </label>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
        {data?.facets.filter(f => !f.key.startsWith("other_")).map(demographicSelect)}
        <label className="text-sm">Minimum age<input type="number" min={0} max={130} value={ageMin} onChange={e => { setAgeMin(e.target.value); setPage(1); }} className={inputClass} /></label>
        <label className="text-sm">Maximum age<input type="number" min={0} max={130} value={ageMax} onChange={e => { setAgeMax(e.target.value); setPage(1); }} className={inputClass} /></label>
      </div>
      <details className="mt-3"><summary className="text-sm cursor-pointer font-medium">Study and attempt filters</summary><div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-3">
        <label className="text-sm">Quiz type<select value={quiz} onChange={e => { setQuiz(e.target.value); setPage(1); }} className={inputClass}><option value="">All quiz types</option>{data?.quiz_ids.map(id => <option key={id} value={id}>{id}</option>)}</select></label>
        <label className="text-sm">Attempt status<select value={status} onChange={e => { setStatus(e.target.value); setPage(1); }} className={inputClass}><option value="completed">Completed attempts</option><option value="in_progress">In-progress attempts</option><option value="all">All attempts</option></select></label>
        <label className="text-sm">Study version<select value={version} onChange={e => { setVersion(e.target.value); setPage(1); }} className={inputClass}><option value="">All versions</option>{data?.study_versions.map(v => <option key={v} value={v}>{v}</option>)}</select></label>
        <label className="text-sm">Question set<select value={questionSet} onChange={e => { setQuestionSet(e.target.value); setPage(1); }} className={inputClass}><option value="">All sets</option>{["a", "b", "c", "d"].map(v => <option key={v} value={v}>{v.toUpperCase()}</option>)}</select></label>
        <label className="text-sm">Quiz position<input type="number" min={1} value={position} onChange={e => { setPosition(e.target.value); setPage(1); }} placeholder="Any position" className={inputClass} /></label>
      </div>
      <div className="flex flex-wrap gap-4 mt-4 text-sm"><label className="flex items-center gap-2"><input type="checkbox" checked={includeTests} onChange={e => { setIncludeTests(e.target.checked); setSelected(null); setPage(1); }} />Include admin / test accounts</label><label className="flex items-center gap-2"><input type="checkbox" checked={includeArchived} onChange={e => { setIncludeArchived(e.target.checked); setSelected(null); setPage(1); }} />Include reset attempts</label></div>
      </details>
      <details className="mt-3"><summary className="text-sm cursor-pointer">Filter self-described responses</summary><div className="grid sm:grid-cols-3 gap-3 mt-3">{data?.facets.filter(f => f.key.startsWith("other_")).map(demographicSelect)}</div></details>
      <p className="mt-3 text-sm text-gray-600">Showing {status === "all" ? "all" : status === "completed" ? "completed" : "in-progress"} attempts{quiz ? ` · ${quiz}` : ""}{version ? ` · study version ${version}` : ""}{questionSet ? ` · set ${questionSet.toUpperCase()}` : ""}{position ? ` · position ${position}` : ""} · {includeTests ? "including test accounts" : "excluding test accounts"} · {includeArchived ? "including resets" : "excluding resets"}</p>
      <p className="mt-3 text-xs text-gray-500">Filters combine across fields. Race / ethnicity matches any of a participant’s selected responses. Option counts reflect all included accounts. Search also narrows the cohort averages. Completed attempts are selected by default.</p>
    </section>
    {loading && <p role="status">Loading research results…</p>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {data && !loading && !error && <>
      <div className="flex flex-wrap gap-3 text-sm"><span className="rounded-lg bg-blue-50 px-4 py-3"><strong>{data.matched_accounts}</strong> matching accounts</span><span className="rounded-lg bg-blue-50 px-4 py-3"><strong>{data.overall.participant_count}</strong> people with selected attempts</span><span className="rounded-lg bg-blue-50 px-4 py-3"><strong>{data.overall.attempt_count}</strong> selected quiz attempts</span><span className="rounded-lg bg-blue-50 px-4 py-3"><strong>{data.overall.questions_answered}</strong> answered questions</span><span className="rounded-lg bg-blue-50 px-4 py-3"><strong>{data.overall.questions_graded}</strong> graded answers</span></div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">{["accuracy", "wrong_ai_agreement", "active_ms", "telemetry_coverage"].map(key => {
        const definition = data.metric_definitions.find(d => d.key === key);
        return definition && <div key={key} className="rounded-xl border p-4"><h3 className="text-sm text-gray-600 mb-2">{definition.label}</h3><MetricValue metric={data.overall.metrics[key]} definition={definition} /></div>;
      })}</div>
      <section className="rounded-xl border p-4"><h2 className="text-lg font-semibold mb-4">Averages for filtered participants</h2>
        {data.overall.participant_count ? <ResearchComparison overall={data.overall} variants={data.variants} definitions={data.metric_definitions} /> : <p>No attempts match the selected study filters. Matching accounts are listed below.</p>}
      </section>
      <ResearchStatistics query={query} includeTests={includeTests} includeArchived={includeArchived} />
      <section className="rounded-xl border p-4"><h2 className="text-lg font-semibold mb-2">Individual participants</h2><p className="text-sm text-gray-600 mb-3">Accounts with no selected attempts remain searchable. Open a participant to inspect all their quiz results independently of the cohort filters.</p>
        <div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr>{["Participant", "Gender", "Academic level / year", "Selected attempts", "Answered", "Accuracy", "Details"].map(label => <th key={label} className="p-2 border-b">{label}</th>)}</tr></thead><tbody>{data.participants.map(person => <tr key={person.participant_id} className="border-b last:border-0">
          <td className="p-2"><div className="font-medium">{person.name || person.participant_id}{person.is_test ? " (test)" : ""}</div><div className="text-gray-600">{person.email}</div></td>
          <td className="p-2">{demographicLabel("gender", person.demographics.gender)}</td><td className="p-2">{demographicLabel("academic_level", person.demographics.academic_level)} / {demographicLabel("year", person.demographics.year)}</td>
          <td className="p-2">{person.attempt_count}</td><td className="p-2">{person.questions_answered}</td><td className="p-2">{formatMetric(person.accuracy, "percent")}</td>
          <td className="p-2"><button type="button" aria-label={`View results for ${person.name || person.email || person.participant_id}`} className="text-blue-700 underline" onClick={() => { setSelected(person.participant_id); setTimeout(() => detail.current?.scrollIntoView?.({ behavior: "smooth", block: "start" }), 0); }}>View results</button></td>
        </tr>)}</tbody></table></div>
        {!data.participants.length && <p className="py-4 text-gray-600">No participants match these filters.</p>}
        <div className="mt-4 flex items-center justify-between"><button type="button" disabled={page <= 1} onClick={() => setPage(v => v - 1)} className="rounded border px-3 py-2 text-sm disabled:opacity-40">Previous page</button><span className="text-sm">Page {data.total_pages ? page : 0} of {data.total_pages}</span><button type="button" disabled={page >= data.total_pages} onClick={() => setPage(v => v + 1)} className="rounded border px-3 py-2 text-sm disabled:opacity-40">Next page</button></div>
      </section>
    </>}
    {selected && <div ref={detail}><ResearchParticipant participantId={selected} includeTests={includeTests} includeArchived={includeArchived} onClose={() => setSelected(null)} /></div>}
  </div>;
}
