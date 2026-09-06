// frontend/pages/survey.tsx
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import {
  getSurveyState,
  submitSurvey,
  type SurveyItem,
  type SurveyAnswer,
} from "../lib/surveys";

import { getNextStep, type StudyStep } from "../lib/study";

type ExtendedUser = User;

/**
 * Copy for a survey stage.
 *
 * The stage set is now open-ended — the flow schedules one interstitial survey
 * per variant (post_followup, post_links, ...) — so anything not listed here
 * falls back to text built from the step's label, rather than being a hard-coded
 * exhaustive map.
 */
type StageCopy = {
  title: string;
  description: string;
  emptyMessage: string;
  submitLabel: string;
  loadError: string;
};

const STAGE_COPY: Record<string, StageCopy> = {
  pre_quiz: {
    title: "Pre-Quiz Survey",
    description:
      "Before you begin the base quiz, please answer a few quick questions.",
    emptyMessage:
      "No survey items found for the pre-quiz survey. Add items in the Surveys Panel.",
    submitLabel: "Begin Base Quiz",
    loadError: "Failed to load the pre-quiz survey.",
  },

  post_base: {
    title: "Post-Base Quiz Survey",
    description:
      "You’ve completed the base quiz. Please answer a few follow-up questions.",
    emptyMessage:
      "No survey items found for the post-base survey. Add items in the Surveys Panel.",
    submitLabel: "Continue",
    loadError: "Failed to load the post-base survey.",
  },
};

function copyForStep(step: StudyStep | null, stage: string | null): StageCopy {
  if (stage && STAGE_COPY[stage]) return STAGE_COPY[stage];

  const label = step?.label ?? "Survey";
  return {
    title: label,
    description:
      "You’ve completed that quiz. Please answer a few questions about it before moving on.",
    emptyMessage:
      "No survey items found for this stage. Add items to the post-base survey in the Surveys Panel.",
    submitLabel: "Continue",
    loadError: "Failed to load the survey.",
  };
}

export default function SurveyPage() {
  const router = useRouter();
  const { stage } = router.query as { stage?: string };

  const [user, setUser] = useState<ExtendedUser | null>(null);
  const [checking, setChecking] = useState(true);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [loadingSurvey, setLoadingSurvey] = useState(true);
  const [items, setItems] = useState<SurveyItem[]>([]);
  const [, setStatus] = useState<"not_started" | "in_progress" | "completed">(
    "not_started",
  );

  const [values, setValues] = useState<
    Record<string, number | string | string[]>
  >({});

  // The backend decides which survey is current; this page just renders it.
  const [activeStep, setActiveStep] = useState<StudyStep | null>(null);
  const activeSurveyStage = activeStep?.key ?? null;

  // Must be memoised: copyForStep builds a fresh object for the per-variant
  // stages, and `config` is a dependency of the loader effect below — an
  // unmemoised value would re-trigger it on every render.
  const config = useMemo(
    () => (activeStep ? copyForStep(activeStep, activeSurveyStage) : null),
    [activeStep, activeSurveyStage],
  );

  useEffect(() => {
    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (cancel) return;
        setUser(res.user as ExtendedUser);
      } catch {
        if (!cancel) router.replace("/login");
      } finally {
        if (!cancel) setChecking(false);
      }
    })();

    return () => {
      cancel = true;
    };
  }, [router]);

  // Resolve which survey step is current. `stage` in the query string is only a
  // hint — if it disagrees with the backend, the backend wins.
  useEffect(() => {
    if (!user) return;
    if (!router.isReady) return;

    let cancel = false;

    (async () => {
      try {
        const next = await getNextStep();
        if (cancel) return;

        if (!next.next_step || next.next_step.kind !== "survey") {
          setLoadingSurvey(false);
          router.replace(next.next_route);
          return;
        }

        if (stage && stage !== next.next_step.key) {
          // Stale link (e.g. an old ?stage=post_variant bookmark) — send the
          // user to the survey they actually owe.
          router.replace(next.next_step.route);
          return;
        }

        setActiveStep(next.next_step);
      } catch (e) {
        console.error(e);
        if (!cancel) router.replace("/dashboard");
      }
    })();

    return () => {
      cancel = true;
    };
  }, [user, router, router.isReady, stage]);

  useEffect(() => {
    if (!user) return;
    if (!activeSurveyStage || !config) return;

    let cancel = false;

    (async () => {
      setLoadingSurvey(true);
      setError(null);

      try {
        // One request: the backend serves this stage's own saved answers while
        // sourcing the question definitions from post_base (see
        // services/surveys._question_stage_for_stage).
        const state = await getSurveyState(activeSurveyStage);
        if (cancel) return;

        setItems(state.items || []);
        setStatus(state.attempt?.status ?? "in_progress");

        const initial: Record<string, number | string | string[]> = {};
        for (const a of state.answers || []) {
          initial[a.item_id] = a.value;
        }
        setValues(initial);

        if (state.attempt?.status === "completed") {
          const next = await getNextStep();
          if (cancel) return;
          router.replace(next.next_route);
          return;
        }
      } catch (e) {
        console.error(e);
        if (!cancel) setError(config.loadError);
      } finally {
        if (!cancel) setLoadingSurvey(false);
      }
    })();

    return () => {
      cancel = true;
    };
  }, [user, activeSurveyStage, config, router]);

  const requiredUnanswered = useMemo(() => {
    return items
      .filter((i) => i.required)
      .filter((i) => {
        const v = values[i.id];
        if (v === undefined) return true;
        if (typeof v === "string" && v.trim() === "") return true;
        if (Array.isArray(v) && v.length === 0) return true;
        return false;
      });
  }, [items, values]);

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  function setLikert(itemId: string, n: number) {
    setValues((prev) => ({ ...prev, [itemId]: n }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (!activeSurveyStage || !config) return;

    setError(null);

    if (requiredUnanswered.length > 0) {
      setError("Please answer all required questions before continuing.");
      return;
    }

    setSaving(true);
    try {
      const answers: SurveyAnswer[] = items
        .map((i) => {
          const v = values[i.id];
          if (v === undefined) return null;
          if (typeof v === "string" && v.trim() === "") return null;
          if (Array.isArray(v) && v.length === 0) return null;
          return { item_id: i.id, value: v };
        })
        .filter(Boolean) as SurveyAnswer[];

      // Saves under this stage's own response document.
      await submitSurvey(activeSurveyStage, answers);

      // Ask the backend where to go rather than optimistically re-deriving the
      // flow here — it has just recorded this step as complete.
      const next = await getNextStep();
      router.replace(next.next_route);
    } catch (e) {
      console.error(e);
      setError("Failed to save your responses.");
    } finally {
      setSaving(false);
    }
  }

  function renderLikertRow(item: SurveyItem) {
    const value = (values[item.id] as number | undefined) ?? null;
    const min = item.scale_min ?? 1;
    const max = item.scale_max ?? 5;
    const left = item.scale_left_label ?? "Strongly disagree";
    const right = item.scale_right_label ?? "Strongly agree";

    return (
      <div className="space-y-2 rounded-lg border border-gray-200 bg-white p-4">
        <p className="text-sm font-medium text-gray-900">
          {item.prompt}
          {item.required && <span className="text-red-500"> *</span>}
        </p>

        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>
            {min} = {left}
          </span>
          <span>
            {max} = {right}
          </span>
        </div>

        <div className="mt-2 flex justify-between gap-2">
          {Array.from({ length: max - min + 1 }).map((_, idx) => {
            const n = min + idx;
            const checked = value === n;

            return (
              <label
                key={n}
                className={[
                  "flex flex-1 cursor-pointer flex-col items-center rounded-md border px-2 py-2 text-xs transition",
                  checked
                    ? "border-blue-500 bg-blue-50 text-blue-700 shadow-sm"
                    : "border-gray-200 bg-gray-50 text-gray-700 hover:border-blue-300 hover:bg-blue-50/60",
                ].join(" ")}
              >
                <input
                  id={`${item.id}-${n}`}
                  type="radio"
                  name={item.id}
                  value={n}
                  checked={checked}
                  onChange={() => setLikert(item.id, n)}
                  className="sr-only"
                />
                <span className="text-sm font-semibold">{n}</span>
              </label>
            );
          })}
        </div>
      </div>
    );
  }

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading…</div>
      </div>
    );
  }

  if (!user) return null;
  if (!activeSurveyStage || !config) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white px-6 h-[8dvh] max-h-24 overflow-hidden overflow-hidden">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">
              {config.title}
            </h1>
            <p className="text-sm text-gray-600">{config.description}</p>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white transition hover:bg-blue-700"
            >
              Back to Dashboard
            </button>
            <button
              onClick={onLogout}
              className="rounded-lg bg-gray-100 px-4 py-2 text-sm hover:bg-gray-200"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl p-6">
        <form
          onSubmit={onSubmit}
          className="space-y-6 rounded-xl border bg-white p-6 shadow-sm"
        >
          {error && (
            <div className="text-sm text-red-600" role="alert">
              {error}
            </div>
          )}

          {loadingSurvey ? (
            <div className="text-sm text-gray-500">Loading survey…</div>
          ) : items.length === 0 ? (
            <div className="text-sm text-gray-500">{config.emptyMessage}</div>
          ) : (
            <>
              {items.map((item) =>
                item.type === "likert" ? (
                  <div key={item.id}>{renderLikertRow(item)}</div>
                ) : (
                  <div
                    key={item.id}
                    className="rounded-lg border border-gray-200 bg-white p-4"
                  >
                    <p className="text-sm font-medium text-gray-900">
                      {item.prompt}
                      {item.required && (
                        <span className="text-red-500"> *</span>
                      )}
                    </p>
                    <p className="mt-2 text-xs text-gray-500">
                      Unsupported question type:{" "}
                      <span className="font-medium">{item.type}</span>
                    </p>
                  </div>
                ),
              )}

              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {saving ? "Saving…" : config.submitLabel}
                </button>
              </div>
            </>
          )}
        </form>
      </main>
    </div>
  );
}
