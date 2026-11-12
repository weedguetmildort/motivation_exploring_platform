// New-participant settings for one study: which variant the next sign-up
// starts with, and (Study 1) the default question sets stamped on sign-up.
// Both save immediately; they are not part of the Study Flow page's Save.
import { useEffect, useState } from "react";
import { apiFetch } from "../lib/fetcher";
import type { StudyId } from "../lib/studySelection";
import SetChips, { type SetId } from "./SetChips";

type Variant = "followup" | "double" | "links";
type NextAssignment = { next: Variant; source: "override" | "rotation" };

const VARIANT_LABELS: Record<Variant, { label: string; color: string }> = {
  followup: { label: "Follow-up", color: "bg-purple-100 text-purple-800" },
  double: { label: "Dual-Agent", color: "bg-blue-100 text-blue-800" },
  links: { label: "Links", color: "bg-green-100 text-green-800" },
};
const VARIANT_ORDER: Variant[] = ["followup", "double", "links"];

export default function NewParticipantSettings({ study, onDefaultSetsChange }: {
  study: StudyId;
  onDefaultSetsChange?: (sets: SetId[]) => void;
}) {
  const [nextAssignment, setNextAssignment] = useState<NextAssignment | null>(null);
  const [busy, setBusy] = useState(false);
  const [defaultSets, setDefaultSets] = useState<SetId[]>([]);
  const [error, setError] = useState("");
  const base = `/api/studies/${study}/users`;
  // Only Study 1 sign-ups are stamped with default sets; Study 2 enrollments never are.
  const hasDefaultSets = study === "study-1";

  useEffect(() => {
    let cancel = false;
    setNextAssignment(null); setDefaultSets([]); setError("");
    apiFetch<NextAssignment>(`${base}/next-assignment`)
      .then((data) => { if (!cancel) setNextAssignment(data); })
      .catch(() => { /* leave the indicator hidden on failure */ });
    if (hasDefaultSets) {
      apiFetch<{ sets: SetId[] | null }>(`${base}/quiz-default-sets`)
        .then((data) => { if (!cancel) { setDefaultSets(data.sets ?? []); onDefaultSetsChange?.(data.sets ?? []); } })
        .catch(() => { /* leave as no restriction on failure */ });
    }
    return () => { cancel = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [study]);

  async function updateNextAssignment(variant: Variant | null) {
    if (busy) return;
    setBusy(true); setError("");
    try {
      setNextAssignment(await apiFetch<NextAssignment>(`${base}/next-assignment`, {
        method: "PUT", body: JSON.stringify({ variant }),
      }));
    } catch {
      setError("Failed to update the next sign-up.");
    } finally {
      setBusy(false);
    }
  }

  async function updateDefaultSets(next: SetId[]) {
    const previous = defaultSets;
    setDefaultSets(next); onDefaultSetsChange?.(next); // optimistic
    try {
      const res = await apiFetch<{ sets: SetId[] | null }>(`${base}/quiz-default-sets`, {
        method: "PUT", body: JSON.stringify({ sets: next.length ? next : null }),
      });
      setDefaultSets(res.sets ?? []); onDefaultSetsChange?.(res.sets ?? []);
    } catch {
      setDefaultSets(previous); onDefaultSetsChange?.(previous); // roll back
      setError("Failed to update the default question sets.");
    }
  }

  return (
    <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold">New participants</h2>
      <p className="mt-1 text-sm text-gray-600">These save as soon as you click.</p>
      {error && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <div role="group" aria-label="Next sign-up" className="mt-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">Next sign-up starts with</span>
          {nextAssignment?.next && (
            <span className="text-sm text-gray-700">
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${VARIANT_LABELS[nextAssignment.next]?.color ?? "bg-gray-100 text-gray-700"}`}>
                {VARIANT_LABELS[nextAssignment.next]?.label ?? nextAssignment.next}
              </span>{" "}
              <span className="text-gray-400">({nextAssignment.source})</span>
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {VARIANT_ORDER.map((v) => (
            <button key={v} type="button" onClick={() => updateNextAssignment(v)} disabled={busy}
              className="rounded-full border px-3 py-1 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60">
              Set {VARIANT_LABELS[v].label}
            </button>
          ))}
          <button type="button" onClick={() => updateNextAssignment(null)} disabled={busy}
            className="rounded-full border px-3 py-1 text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-60">
            Reset to rotation
          </button>
        </div>
        <p className="mt-1 text-xs text-gray-500">Pins the first variant for the next participant only, then rotation resumes.</p>
      </div>

      {hasDefaultSets && (
        <div className="mt-4">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">Default question sets</span>
            <SetChips value={defaultSets} onChange={updateDefaultSets} label="Default question sets" />
          </div>
          <p className="text-xs text-gray-500">
            Stamped on each new Study 1 sign-up. A quiz without its own set draws only from these sets;
            none selected means the whole bank.
          </p>
        </div>
      )}
    </section>
  );
}
