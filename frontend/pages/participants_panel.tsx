// frontend/pages/participants_panel.tsx
import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { apiFetch } from "../lib/fetcher";
import PageHeader from "../components/PageHeader";

type Participant = {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  assigned_var: "followup" | "double" | "links";
  survey_stage: "pre_quiz" | "post_base" | "post_variant" | "complete";
  demographics_completed: boolean;
  survey_pre_base_completed: boolean;
  quiz_base_completed: boolean;
  survey_post_base_completed: boolean;
  quiz_variant_completed: boolean;
  survey_post_variant_completed: boolean;
  last_active_at: string | null;
  consent_declined_at: string | null;
  quiz_sets: SetId[] | null;
  created_at: string | null;
};

type Tab = "all" | "active" | "complete" | "declined";

const ALL_SETS = ["a", "b", "c", "d"] as const;
type SetId = (typeof ALL_SETS)[number];

// Toggle a set letter in/out of the current selection, kept sorted & stable.
function toggleSet(current: SetId[], s: SetId): SetId[] {
  return current.includes(s)
    ? current.filter((x) => x !== s)
    : ALL_SETS.filter((x) => x === s || current.includes(x));
}

// A/B/C/D toggle chips. Empty selection = "no restriction" (all questions).
function SetChips({
  value,
  onChange,
  label,
}: {
  value: SetId[];
  onChange: (next: SetId[]) => void;
  label: string;
}) {
  return (
    <span
      role="group"
      aria-label={label}
      className="inline-flex flex-wrap items-center gap-1"
    >
      {ALL_SETS.map((s) => {
        const on = value.includes(s);
        return (
          <button
            key={s}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(toggleSet(value, s))}
            className={`rounded px-1.5 py-0.5 text-xs font-medium border transition ${
              on
                ? "bg-indigo-600 text-white border-indigo-600"
                : "bg-white text-gray-500 border-gray-300 hover:bg-gray-50"
            }`}
          >
            {s.toUpperCase()}
          </button>
        );
      })}
      {value.length === 0 && (
        <span className="text-xs text-gray-400">all</span>
      )}
    </span>
  );
}

const VARIANT_LABELS: Record<string, { label: string; color: string }> = {
  followup:  { label: "Follow-up",  color: "bg-purple-100 text-purple-800" },
  double:    { label: "Dual-Agent", color: "bg-blue-100 text-blue-800" },
  links:     { label: "Links",      color: "bg-green-100 text-green-800" },
};

// The three study conditions ("cases"), in a fixed display order.
const VARIANT_ORDER: Participant["assigned_var"][] = ["followup", "double", "links"];

type NextAssignment = {
  next: Participant["assigned_var"];
  source: "override" | "rotation";
};

const STEPS = [
  { key: "demographics_completed",        label: "Demo" },
  { key: "survey_pre_base_completed",     label: "Pre-Survey" },
  { key: "quiz_base_completed",           label: "Quiz Base" },
  { key: "survey_post_base_completed",    label: "Post-Survey" },
  { key: "quiz_variant_completed",        label: "Quiz Variant" },
  { key: "survey_post_variant_completed", label: "Final Survey" },
] as const;

function relativeTime(iso: string | null): string {
  if (!iso) return "Never";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 2)   return "Just now";
  if (mins < 60)  return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)   return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function isActiveRecently(p: Participant): boolean {
  if (!p.last_active_at) return false;
  return Date.now() - new Date(p.last_active_at).getTime() < 7 * 24 * 60 * 60 * 1000;
}

function StageProgress({ p }: { p: Participant }) {
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {STEPS.map((step) => {
        const done = p[step.key];
        return (
          <span
            key={step.key}
            className={`rounded px-1.5 py-0.5 text-xs font-medium ${
              done
                ? "bg-green-100 text-green-800"
                : "bg-gray-100 text-gray-400"
            }`}
          >
            {done ? "✓ " : ""}{step.label}
          </span>
        );
      })}
    </div>
  );
}

export default function ParticipantsPanelPage() {
  const router = useRouter();
  const [user, setUser]               = useState<User | null>(null);
  const [checking, setChecking]       = useState(true);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState<string | null>(null);
  const [activeTab, setActiveTab]     = useState<Tab>("all");
  const [nextAssignment, setNextAssignment] = useState<NextAssignment | null>(null);
  const [assignmentBusy, setAssignmentBusy] = useState(false);
  const [defaultSets, setDefaultSets] = useState<SetId[]>([]);

  // Auth gate
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const res = await getMe();
        if (!cancel) {
          if (!res.user.is_admin) { router.replace("/dashboard"); return; }
          setUser(res.user);
        }
      } catch {
        if (!cancel) router.replace("/login");
      } finally {
        if (!cancel) setChecking(false);
      }
    })();
    return () => { cancel = true; };
  }, []);

  // Load participants after auth resolves
  useEffect(() => {
    if (!user) return;
    let cancel = false;
    setLoading(true);
    setError(null);
    apiFetch<Participant[]>("/api/users")
      .then((data) => { if (!cancel) setParticipants(data); })
      .catch(() => { if (!cancel) setError("Failed to load participants."); })
      .finally(() => { if (!cancel) setLoading(false); });

    // Fetch the next-assignment indicator independently — a failure here must
    // never block the roster from rendering.
    apiFetch<NextAssignment>("/api/users/next-assignment")
      .then((data) => { if (!cancel) setNextAssignment(data); })
      .catch(() => { /* leave the indicator hidden on failure */ });

    // Fetch the global default question-set restriction (also independent).
    apiFetch<{ sets: SetId[] | null }>("/api/users/quiz-default-sets")
      .then((data) => { if (!cancel) setDefaultSets(data.sets ?? []); })
      .catch(() => { /* leave as no restriction on failure */ });

    return () => { cancel = true; };
  }, [user]);

  async function updateNextAssignment(variant: Participant["assigned_var"] | null) {
    if (assignmentBusy) return;
    setAssignmentBusy(true);
    try {
      const updated = await apiFetch<NextAssignment>("/api/users/next-assignment", {
        method: "PUT",
        body: JSON.stringify({ variant }),
      });
      setNextAssignment(updated);
    } catch {
      alert("Failed to update the next assignment.");
    } finally {
      setAssignmentBusy(false);
    }
  }

  async function updateDefaultSets(next: SetId[]) {
    const sets = next.length ? next : null;
    const prev = defaultSets;
    setDefaultSets(next); // optimistic
    try {
      const res = await apiFetch<{ sets: SetId[] | null }>("/api/users/quiz-default-sets", {
        method: "PUT",
        body: JSON.stringify({ sets }),
      });
      setDefaultSets(res.sets ?? []);
    } catch {
      setDefaultSets(prev); // roll back
      alert("Failed to update the default question sets.");
    }
  }

  async function updateParticipantSets(id: string, next: SetId[]) {
    const quiz_sets = next.length ? next : null;
    try {
      const updated = await apiFetch<Participant>(`/api/users/${id}/quiz-sets`, {
        method: "PATCH",
        body: JSON.stringify({ quiz_sets }),
      });
      setParticipants((prev) =>
        prev.map((p) => (p.id === id ? { ...p, quiz_sets: updated.quiz_sets ?? null } : p)),
      );
    } catch {
      alert("Failed to update the participant's question sets.");
    }
  }

  async function onLogout() {
    try { await logout(); } finally { router.replace("/login"); }
  }

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading participants panel…</div>
      </div>
    );
  }
  if (!user) return null;

  const filtered = participants.filter((p) => {
    if (activeTab === "active")   return isActiveRecently(p) && p.survey_stage !== "complete";
    if (activeTab === "complete") return p.survey_stage === "complete";
    if (activeTab === "declined") return p.consent_declined_at != null;
    return true;
  });

  const counts = {
    all:      participants.length,
    active:   participants.filter((p) => isActiveRecently(p) && p.survey_stage !== "complete").length,
    complete: participants.filter((p) => p.survey_stage === "complete").length,
    declined: participants.filter((p) => p.consent_declined_at != null).length,
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "all",      label: `All (${counts.all})` },
    { key: "active",   label: `Active (${counts.active})` },
    { key: "complete", label: `Complete (${counts.complete})` },
    { key: "declined", label: `Declined (${counts.declined})` },
  ];

  // Cases per study condition: how many participants we have in each arm.
  // "Enrolled" excludes anyone who declined consent (not a usable case);
  // "complete" is those who finished the full study.
  const caseCounts = VARIANT_ORDER.map((variant) => {
    const inVariant = participants.filter((p) => p.assigned_var === variant);
    return {
      variant,
      label: VARIANT_LABELS[variant].label,
      color: VARIANT_LABELS[variant].color,
      enrolled: inVariant.filter((p) => p.consent_declined_at == null).length,
      complete: inVariant.filter((p) => p.survey_stage === "complete").length,
    };
  });

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Participants Panel"
        subtitle={`${participants.length} participant${participants.length !== 1 ? "s" : ""} enrolled`}
        onDashboard={() => router.push("/dashboard")}
        onLogout={onLogout}
      />

      <div className="page-container">
        {/* Tabs */}
        <div className="mb-4 flex flex-wrap gap-2">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                activeTab === t.key
                  ? "bg-blue-600 text-white"
                  : "bg-white border text-gray-600 hover:bg-gray-50"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Cases by condition — usable N per study arm */}
        <div
          role="group"
          aria-label="Cases by condition"
          className="mb-4 rounded-lg border bg-white px-4 py-3 shadow-sm"
        >
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
            Cases by condition
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            {caseCounts.map((c) => (
              <div key={c.variant} className="flex items-center gap-2 text-sm">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${c.color}`}>
                  {c.label}
                </span>
                <span className="text-gray-700">{c.enrolled} enrolled</span>
                <span className="text-gray-300">·</span>
                <span className="text-gray-700">{c.complete} complete</span>
              </div>
            ))}
          </div>
        </div>

        {/* Next sign-up — pin the next case to even out the spread (one-shot) */}
        <div
          role="group"
          aria-label="Next sign-up"
          className="mb-4 rounded-lg border bg-white px-4 py-3 shadow-sm"
        >
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              Next sign-up
            </span>
            {nextAssignment?.next && (
              <span className="text-sm text-gray-700">
                {"→ "}
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    VARIANT_LABELS[nextAssignment.next]?.color ?? "bg-gray-100 text-gray-700"
                  }`}
                >
                  {VARIANT_LABELS[nextAssignment.next]?.label ?? nextAssignment.next}
                </span>{" "}
                <span className="text-gray-400">({nextAssignment.source})</span>
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {VARIANT_ORDER.map((v) => (
              <button
                key={v}
                onClick={() => updateNextAssignment(v)}
                disabled={assignmentBusy}
                className="rounded-full border px-3 py-1 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
              >
                Set {VARIANT_LABELS[v].label}
              </button>
            ))}
            <button
              onClick={() => updateNextAssignment(null)}
              disabled={assignmentBusy}
              className="rounded-full border px-3 py-1 text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-60"
            >
              Reset to rotation
            </button>
          </div>
        </div>

        {/* Default question sets stamped onto new sign-ups (Phase 11) */}
        <div className="mb-4 rounded-lg border bg-white px-4 py-3 shadow-sm">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              Default question sets (new sign-ups)
            </span>
            <span className="text-xs text-gray-400">
              empty = no restriction (all questions)
            </span>
          </div>
          <SetChips
            value={defaultSets}
            onChange={updateDefaultSets}
            label="Default question sets"
          />
        </div>

        {loading && <p className="text-gray-500">Loading…</p>}
        {error && <p className="text-red-600">{error}</p>}

        {!loading && !error && filtered.length === 0 && (
          <p className="text-gray-500">No participants in this tab.</p>
        )}

        <div className="space-y-3">
          {filtered.map((p) => {
            const variant = VARIANT_LABELS[p.assigned_var] ?? { label: p.assigned_var, color: "bg-gray-100 text-gray-700" };
            const declined = p.consent_declined_at != null;
            const complete = p.survey_stage === "complete";

            return (
              <div
                key={p.id}
                className="flex items-start justify-between rounded-lg border bg-white px-4 py-3 shadow-sm"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-gray-900">
                      {p.first_name} {p.last_name}
                    </span>
                    <span className="text-sm text-gray-500">{p.email}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${variant.color}`}>
                      {variant.label}
                    </span>
                    {complete && (
                      <span className="rounded-full bg-green-600 px-2 py-0.5 text-xs font-medium text-white">
                        Complete
                      </span>
                    )}
                    {declined && (
                      <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                        Declined
                      </span>
                    )}
                  </div>
                  <StageProgress p={p} />
                  <div className="mt-1.5 flex items-center gap-2">
                    <span className="text-xs text-gray-500">Sets:</span>
                    <SetChips
                      value={p.quiz_sets ?? []}
                      onChange={(next) => updateParticipantSets(p.id, next)}
                      label={`Question sets for ${p.email}`}
                    />
                  </div>
                </div>

                <div className="ml-4 shrink-0 text-right text-xs text-gray-500">
                  <div>Last active</div>
                  <div className="font-medium text-gray-700">{relativeTime(p.last_active_at)}</div>
                  {p.created_at && (
                    <div className="mt-1 text-gray-400">
                      Joined {new Date(p.created_at).toLocaleDateString()}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
