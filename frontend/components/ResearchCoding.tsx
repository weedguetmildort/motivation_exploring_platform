import { useEffect, useState } from "react";
import { apiFetch } from "../lib/fetcher";

type Annotation = { _id: string; source: "human" | "llm"; model: string | null; reviewer_id: string | null;
  labels: Record<string, string>; evidence: { dimension: string; turn_id: string; quote: string }[]; notes: string; independent_review: boolean };
type CodingData = { packet: { packet_hash: string; answer: { answered_at: string }; limitations: string[];
  turns: { turn_id: string; role: string; text: string; trigger: string | null; agent: string | null; displayed: boolean | null }[];
  suggestions: { item_id: string; text: string }[] };
  rubric: { key: string; description: string; options: string[] }[]; rubric_version: string; partition: string;
  evaluator: { enabled: boolean; model: string | null; reason: string | null }; annotations: Annotation[] };

export default function ResearchCoding({ path }: { path: string }) {
  const [data, setData] = useState<CodingData | null>(null);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [evidence, setEvidence] = useState<Record<string, { turn_id: string; quote: string }>>({});
  const [notes, setNotes] = useState("");
  const [independent, setIndependent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [route, query = ""] = path.split("?");
  const endpoint = `${route}/coding?${query}`;
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError(null); setNotice(null);
    apiFetch<CodingData>(endpoint, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      setData(result); setLabels(Object.fromEntries(result.rubric.map(d => [d.key, "insufficient_evidence"])));
      setEvidence({}); setNotes(""); setIndependent(false);
    }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to load coding packet."); });
    return () => controller.abort();
  }, [endpoint, refresh]);
  async function save(source: "review" | "evaluate") {
    if (!data || busy) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const body = source === "evaluate" ? { packet_hash: data.packet.packet_hash } : {
        packet_hash: data.packet.packet_hash, labels, notes, independent_review: independent,
        evidence: Object.entries(evidence).filter(([, value]) => value.quote && value.turn_id)
          .map(([dimension, value]) => ({ dimension, ...value })),
      };
      const annotation = await apiFetch<Annotation>(`${route}/coding/${source}?${query}`, { method: "POST", body: JSON.stringify(body) });
      setData(current => current ? { ...current, annotations: [...current.annotations.filter(a => a._id !== annotation._id), annotation] } : current);
      setNotice(source === "review" ? "Human review saved. Refresh cohort results to include this review." : "Provisional model coding saved. Human validation is still required.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to save coding."); }
    finally { setBusy(false); }
  }
  const sources = data ? [...data.packet.turns.map(t => ({ id: t.turn_id, text: t.text, role: t.role, trigger: t.trigger })),
    ...data.packet.suggestions.map(s => ({ id: `suggestion:${s.item_id}`, text: s.text, role: "suggestion", trigger: null }))] : [];
  return <section aria-label="Conversation coding" className="space-y-4 rounded border bg-gray-50 p-4">
    <p className="text-sm">Code observable behavior in the saved, pre-submission conversation. Keyword measures and LLM labels are exploratory. No written reasoning means reasoning was not observed.</p>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {!data && !error && <p role="status">Loading coding packet…</p>}
    <button type="button" disabled={busy} className="rounded border px-3 py-1 text-sm" onClick={() => setRefresh(v => v + 1)}>Reload coding packet</button>
    {notice && <p role="status" className="text-sm text-blue-800">{notice}</p>}
    {data && <>
      <p className="text-xs text-gray-600">Rubric: {data.rubric_version} · Participant split: {data.partition} · Packet: {data.packet.packet_hash.slice(0, 12)}</p>
      {data.packet.limitations.length > 0 && <p className="text-sm text-amber-900">Packet limitations: {data.packet.limitations.map(v => v.replaceAll("_", " ")).join(", ")}</p>}
      <details><summary className="cursor-pointer font-medium text-sm">Evidence sources ({sources.length})</summary><div className="space-y-3 mt-3">{sources.map(source => <div key={source.id} className="rounded border bg-white p-3 text-sm"><p className="font-medium break-all">{source.id} · {source.role}{source.trigger ? ` · ${source.trigger}` : ""}</p><p className="whitespace-pre-wrap mt-1">{source.text}</p></div>)}</div></details>
      <fieldset disabled={busy || !data.packet.answer.answered_at} className="space-y-4">
        <legend className="font-semibold mb-3">Human review</legend>
        {data.rubric.map(dimension => {
          const role = dimension.key.startsWith("ai_") ? "assistant" : dimension.key === "suggestion_quality" ? "suggestion" : "user";
          const available = sources.filter(s => s.role === role && s.trigger !== "auto_question");
          const selected = evidence[dimension.key] || { turn_id: "", quote: "" };
          return <div key={dimension.key} className="space-y-2 rounded border bg-white p-3">
            <label className="block text-sm font-medium">{dimension.key.replaceAll("_", " ")}
              <select className="block w-full mt-1 rounded border p-2" value={labels[dimension.key]} onChange={e => setLabels(v => ({ ...v, [dimension.key]: e.target.value }))}>
                {dimension.options.map(option => <option key={option} value={option}>{option.replaceAll("_", " ")}</option>)}
              </select></label>
            <p className="text-xs text-gray-600">{dimension.description}</p>
            <label className="block text-xs">Evidence source for {dimension.key.replaceAll("_", " ")}
              <select className="block w-full mt-1 rounded border p-2" value={selected.turn_id} onChange={e => setEvidence(v => ({ ...v, [dimension.key]: { ...selected, turn_id: e.target.value } }))}>
                <option value="">Select a source when supporting a positive label</option>{available.map(s => <option key={s.id} value={s.id}>{s.id} — {s.text.slice(0, 80)}</option>)}
              </select></label>
            <label className="block text-xs">Exact quote for {dimension.key.replaceAll("_", " ")}
              <textarea maxLength={2000} className="block w-full mt-1 rounded border p-2" value={selected.quote} onChange={e => setEvidence(v => ({ ...v, [dimension.key]: { ...selected, quote: e.target.value } }))} /></label>
          </div>;
        })}
        <label className="block text-sm">Reviewer notes<textarea maxLength={4000} className="block w-full mt-1 rounded border p-2" value={notes} onChange={e => setNotes(e.target.value)} /></label>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={independent} onChange={e => setIndependent(e.target.checked)} />I coded independently before viewing other human or model labels. Only independent reviews qualify for validation.</label>
        <button type="button" onClick={() => save("review")} className="rounded bg-blue-600 text-white px-4 py-2 text-sm">{busy ? "Working…" : "Save human review"}</button>
      </fieldset>
      <div className="rounded border bg-white p-3 space-y-2">
        <h5 className="font-medium">Optional model coding</h5>
        <p className="text-sm">This sends the saved conversation text to your configured research AI service. Condition labels, account profile fields, and the final submission outcome are excluded. Free text may still contain personal details. Model labels remain provisional.</p>
        <p className="text-xs text-gray-600">{data.evaluator.enabled ? `Evaluator: ${data.evaluator.model}` : data.evaluator.reason}</p>
        <button type="button" disabled={busy || !data.evaluator.enabled || !data.packet.answer.answered_at} onClick={() => save("evaluate")} className="rounded border px-4 py-2 text-sm disabled:opacity-50">Run optional AI coding</button>
      </div>
      <details><summary className="cursor-pointer text-sm font-medium">Existing labels — view after independent coding ({data.annotations.length})</summary><div className="space-y-3 mt-3">{data.annotations.map(annotation => <div key={annotation._id} className="rounded border bg-white p-3 text-sm">
        <p className="font-medium">{annotation.source === "human" ? `Human reviewer ${annotation.reviewer_id}` : `Provisional model: ${annotation.model}`}</p>
        <dl>{Object.entries(annotation.labels).map(([key, value]) => <div key={key}>{key.replaceAll("_", " ")}: <strong>{value.replaceAll("_", " ")}</strong></div>)}</dl>
        {annotation.evidence.map((e, i) => <p key={i} className="mt-2">{e.dimension.replaceAll("_", " ")} · {e.turn_id}: “{e.quote}”</p>)}
        {annotation.notes && <p className="mt-2">{annotation.notes}</p>}
      </div>)}</div></details>
    </>}
  </section>;
}
