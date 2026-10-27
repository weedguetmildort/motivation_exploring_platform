import { useEffect, useState } from "react";
import { apiFetch } from "../lib/fetcher";
import type { StudyAccessPolicy } from "../lib/studySelection";

type Participant = { id: string; name: string; email: string; approved: boolean; available: boolean;
  reason: string | null; status: string; completed_steps: number; total_steps: number;
  approved_at: string | null; interview_at: string | null; notes: string;
  access_history: { approved: boolean; admin_id: string | null; via?: string; code_version?: number; at: string; notes?: string }[] };

export default function StudyInterviewAccess() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ participants: Participant[]; total: number; access_policy?: StudyAccessPolicy } | null>(null);
  const requiresApproval = data?.access_policy?.requires_approval !== false;
  const [drafts, setDrafts] = useState<Record<string, { notes: string; interview: string }>>({});
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => { const timer = setTimeout(() => { setQuery(search.trim()); setPage(1); }, 300); return () => clearTimeout(timer); }, [search]);
  useEffect(() => {
    const controller = new AbortController();
    apiFetch<{ participants: Participant[]; total: number; access_policy?: StudyAccessPolicy }>(`/api/studies/participants?search=${encodeURIComponent(query)}&page=${page}`, { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted && result && Array.isArray(result.participants)) setData(result); })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to load approvals."); });
    return () => controller.abort();
  }, [query, page, refresh]);
  function draft(person: Participant) { return drafts[person.id] ?? { notes: person.notes ?? "", interview: person.interview_at ? new Date(person.interview_at).toISOString().slice(0, 16) : "" }; }
  async function save(person: Participant, approved: boolean) {
    setBusy(person.id); setError(""); setNotice("");
    try {
      const values = draft(person);
      await apiFetch(`/api/studies/participants/${person.id}/study-2-access`, { method: "PATCH", body: JSON.stringify({ approved,
        interview_at: values.interview ? new Date(`${values.interview}Z`).toISOString() : null, notes: values.notes }) });
      setNotice(`${person.name || person.email}: Study 2 ${requiresApproval ? "access" : "approval"} ${approved ? "approved" : requiresApproval ? "revoked" : "removed"}. ${requiresApproval ? "" : "Approval is optional in the current mode. "}Saved progress is preserved.`);
      setRefresh(value => value + 1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to update approval."); }
    finally { setBusy(""); }
  }
  return <section aria-label="Study 2 interview approval" className="rounded-xl border bg-white p-4 space-y-3">
    <h2 className="text-lg font-semibold">{requiresApproval ? "Study 2 interview access" : "Study 2 access"}</h2>
    <p className="text-sm text-gray-600">Study 1 is open to registered participants. {requiresApproval ? "Participants unlock Study 2 with the access code above, or approve them here. A revoked participant cannot re-enter with a code." : "Study 2 approval is optional in the current mode; removing approval does not block access."} Study 1 completion is {data?.access_policy?.requires_study1_completion === false ? "optional" : "required"}. Approval preserves progress and never grants admin access. Access rules are controlled by STUDY_ACCESS_MODE.</p>
    <label className="block text-sm">Find participant for Study 2<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Name, email, or account ID" className="block mt-1 w-full rounded border p-2" /></label>
    <button type="button" onClick={() => setRefresh(value => value + 1)} className="rounded border px-3 py-2 text-sm">Refresh interview access</button>
    {error && <p role="alert" className="text-red-700">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{["Participant", "Study 2 status", "Interview details", "Access"].map(label => <th key={label} className="p-2 border-b">{label}</th>)}</tr></thead>
      <tbody>{data?.participants.map(person => <tr key={person.id} className="border-b">
        <td className="p-2"><strong>{person.name || person.email}</strong><div>{person.email}</div></td>
        <td className="p-2">{person.approved || !requiresApproval ? person.status.replaceAll("_", " ") : "Not approved"}<div>{person.completed_steps} of {person.total_steps} steps</div>{person.reason && <div className="text-gray-600">{person.reason}</div>}{person.approved_at && <div>Approved {new Date(person.approved_at).toLocaleString()}</div>}</td>
        <td className="p-2"><details><summary className="cursor-pointer">Date, notes, and approval history</summary>
          <label className="block">Interview date/time (UTC)<input type="datetime-local" aria-label={`Interview time for ${person.email}`} value={draft(person).interview} onChange={e => setDrafts(previous => ({ ...previous, [person.id]: { ...draft(person), interview: e.target.value } }))} className="block rounded border p-2" /></label>
          <label className="block mt-2">Interviewer notes<textarea aria-label={`Interview notes for ${person.email}`} maxLength={4000} value={draft(person).notes} onChange={e => setDrafts(previous => ({ ...previous, [person.id]: { ...draft(person), notes: e.target.value } }))} className="block rounded border p-2" /></label>
          {person.access_history?.map((entry, i) => <p key={i} className="text-xs mt-2">{entry.approved ? "Approved" : "Revoked"} · {new Date(entry.at).toLocaleString()} · {entry.via === "access_code" ? `Access code v${entry.code_version}` : `Admin ${entry.admin_id}`}{entry.notes ? ` · ${entry.notes}` : ""}</p>)}
        </details></td>
        <td className="p-2"><button disabled={!!busy} onClick={() => save(person, true)} className="rounded border px-3 py-2">{person.approved ? "Save approval details" : "Approve Study 2 access"}</button>{person.approved && <button disabled={!!busy} onClick={() => save(person, false)} className="ml-2 rounded border px-3 py-2">{requiresApproval ? "Revoke access" : "Remove approval"}</button>}</td>
      </tr>)}</tbody></table></div>
    {data && !data.participants.length && <p>No matching participants.</p>}
    <div className="flex gap-3 items-center"><button disabled={page === 1} onClick={() => setPage(value => value - 1)}>Previous approvals page</button><span>Page {page}</span><button disabled={!data || page * 25 >= data.total} onClick={() => setPage(value => value + 1)}>Next approvals page</button></div>
  </section>;
}
