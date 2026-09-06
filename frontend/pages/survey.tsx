// frontend/pages/survey.tsx
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { getMe, invalidateMeCache, logout, type User } from "../lib/auth";
import ProgressBar from "../components/ProgressBar";
import PageHeader from "../components/PageHeader";
import {
  stageConfigFor,
  surveyPath,
  stepIndexForPath,
  buildStudySteps,
} from "../lib/studySteps";
import { getNextStep } from "../lib/study";
import {
  getSurveyState,
  submitSurvey,
  type SurveyItem,
  type SurveyAnswer,
} from "../lib/surveys";

// Which survey is current, and where a participant goes next, are both decided
// by the backend (GET /study/next). The three hand-written ladders that used to
// live here duplicated that logic and could not express one survey per variant.

export default function SurveyPage() {
  const router = useRouter();
  const { quiz_id, stage } = router.query as {
    quiz_id?: string;
    stage?: string;
  };

  const [user, setUser] = useState<User | null>(null);
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

  function isUnansweredValue(value: unknown): boolean {
    if (value === undefined || value === null) return true;
    if (typeof value === "string") return value.trim() === "";
    if (typeof value === "number") return !Number.isFinite(value);
    if (Array.isArray(value)) return value.length === 0;
    return false;
  }

  // The backend decides which survey is current; `?stage=` is only a hint.
  const [activeSurveyStage, setActiveSurveyStage] = useState<string | null>(null);

  // Must be memoised: stageConfigFor builds a fresh object, and `config` is a
  // dependency of the loader effect below.
  const config = useMemo(
    () => (user && activeSurveyStage ? stageConfigFor(user, activeSurveyStage) : null),
    [user, activeSurveyStage],
  );

  useEffect(() => {
    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (cancel) return;

        setUser(res.user as User);
      } catch {
        if (!cancel) router.replace("/login");
      } finally {
        if (!cancel) setChecking(false);
      }
    })();

    return () => {
      cancel = true;
    };
  }, []);

  // Resolve which survey step is current. A stale `?stage=` link (e.g. an old
  // post_variant bookmark) is redirected to the survey the participant owes.
  useEffect(() => {
    if (!user) return;

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
          router.replace(next.next_step.route);
          return;
        }

        setActiveSurveyStage(next.next_step.key);
      } catch (e) {
        console.error(e);
        if (!cancel) router.replace("/dashboard");
      }
    })();

    return () => {
      cancel = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, stage]);

  useEffect(() => {
    if (!user || !activeSurveyStage || !config) return;

    let cancel = false;

    (async () => {
      setLoadingSurvey(true);
      setError(null);

      try {
        // One request: the backend serves this stage's own saved answers while
        // sourcing the question definitions from the post_base item bank
        // (services/surveys._question_stage_for_stage).
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
          invalidateMeCache();
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, activeSurveyStage, config]);

  const requiredUnanswered = useMemo(() => {
    return items
      .filter((i) => i.required)
      .filter((i) => isUnansweredValue(values[i.id]));
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
          if (isUnansweredValue(v)) return null;
          return { item_id: i.id, value: v };
        })
        .filter(Boolean) as SurveyAnswer[];

      // Saves under this stage's own response document.
      await submitSurvey(activeSurveyStage, answers);
      invalidateMeCache();

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
      <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-5 sm:p-6">
        <p className="text-base font-medium text-gray-900 leading-snug">
          {item.prompt}
          {item.required && <span className="text-red-500"> *</span>}
        </p>

        <div className="flex gap-2 sm:gap-3">
          {Array.from({ length: max - min + 1 }).map((_, idx) => {
            const n = min + idx;
            const checked = value === n;

            return (
              <label
                key={n}
                className={[
                  "flex flex-1 cursor-pointer flex-col items-center rounded-xl border-2 py-4 transition select-none",
                  checked
                    ? "border-blue-500 bg-blue-50 shadow-sm"
                    : "border-gray-200 bg-white hover:border-blue-300 hover:bg-blue-50/50",
                ].join(" ")}
              >
                <input
                  type="radio"
                  name={item.id}
                  value={n}
                  checked={checked}
                  onChange={() => setLikert(item.id, n)}
                  className="sr-only"
                />
                <span className={`text-lg font-bold leading-none ${checked ? "text-blue-600" : "text-gray-500"}`}>{n}</span>
              </label>
            );
          })}
        </div>

        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-gray-700">{left}</span>
          <span className="text-sm font-semibold text-gray-700">{right}</span>
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

  // Position within this participant's own flow, which is no longer 5 steps.
  const allSteps = buildStudySteps(user);
  const surveyStepIndex = stepIndexForPath(allSteps, surveyPath(activeSurveyStage));
  const surveyStepId = surveyStepIndex === -1 ? undefined : allSteps[surveyStepIndex].id;
  const surveyStepNum = surveyStepIndex === -1 ? 1 : surveyStepIndex + 1;

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title={
          <>
            {config.title}
            <span className="ml-3 text-base font-normal text-gray-400">
              Step {surveyStepNum} of {allSteps.length}
            </span>
          </>
        }
        subtitle={config.description}
        onDashboard={() => router.push("/dashboard")}
        onLogout={onLogout}
      />

      <main className="px-4 py-8 sm:px-12 sm:py-10">
        <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[340px_1fr] lg:items-start lg:gap-12">

          {/* Sidebar */}
          <aside className="lg:sticky lg:top-6">
            <ProgressBar user={user} activeStep={surveyStepId} collapsible />
          </aside>

          {/* Form */}
          <form
            onSubmit={onSubmit}
            className="space-y-6 rounded-xl border bg-white p-8 shadow-sm"
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
                      className="rounded-xl border border-gray-200 bg-white p-5 sm:p-6"
                    >
                      <p className="text-base font-medium text-gray-900 leading-snug">
                        {item.prompt}
                        {item.required && (
                          <span className="text-red-500"> *</span>
                        )}
                      </p>
                      <p className="mt-2 text-sm text-gray-500">
                        Unsupported question type:{" "}
                        <span className="font-medium">{item.type}</span>
                      </p>
                    </div>
                  ),
                )}

                <div className="flex justify-end pt-4">
                  <button
                    type="submit"
                    disabled={saving}
                    className="rounded-xl bg-blue-600 px-8 py-3 text-base font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition"
                  >
                    {saving ? "Saving…" : config.submitLabel}
                  </button>
                </div>
              </>
            )}
          </form>

        </div>
      </main>
    </div>
  );
}
