// frontend/pages/survey.tsx
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { getMe, invalidateMeCache, logout, type User } from "../lib/auth";
import ProgressBar, { type StepId } from "../components/ProgressBar";
import PageHeader from "../components/PageHeader";
import {
  getSurveyState,
  submitSurvey,
  type SurveyItem,
  type SurveyAnswer,
} from "../lib/surveys";

type SurveyStage = "pre_quiz" | "post_base" | "post_variant" | "complete";

type ActiveSurveyStage = Exclude<SurveyStage, "complete">;

type ExtendedUser = User & {
  assigned_var?: string | null;
  survey_stage?: SurveyStage | null;
  survey_pre_base_completed?: boolean;
  survey_post_base_completed?: boolean;
  survey_post_variant_completed?: boolean;
  quiz_base_completed?: boolean;
  quiz_variant_completed?: boolean;
};

const STAGE_CONFIG: Record<
  ActiveSurveyStage,
  {
    title: string;
    description: string;
    emptyMessage: string;
    submitLabel: string;
    loadError: string;
  }
> = {
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
    submitLabel: "Continue to Variant Quiz",
    loadError: "Failed to load the post-base survey.",
  },

  post_variant: {
    title: "Final Survey",
    description:
      "You’ve completed the variant quiz. Please answer a few final questions.",
    emptyMessage:
      "No survey items found for the post-variant survey. Add items in the Surveys Panel.",
    submitLabel: "Finish",
    loadError: "Failed to load the final survey.",
  },
};


function isActiveSurveyStage(value: unknown): value is ActiveSurveyStage {
  return (
    value === "pre_quiz" || value === "post_base" || value === "post_variant"
  );
}

/**
 * Returns the survey stage that should actually be shown right now.
 * Returns null when the user should not see a survey page and should be routed onward.
 */
function resolveCurrentSurveyStage(
  user: ExtendedUser | null,
): ActiveSurveyStage | null {
  if (!user) return null;

  if (!user.survey_pre_base_completed) {
    return "pre_quiz";
  }

  if (user.quiz_base_completed && !user.survey_post_base_completed) {
    return "post_base";
  }

  if (user.quiz_variant_completed && !user.survey_post_variant_completed) {
    return "post_variant";
  }

  return null;
}

/**
 * Decide which survey definition to load for a given active survey stage.
 * post_variant reuses the post_base questions.
 */
function getLoadStage(activeStage: ActiveSurveyStage): ActiveSurveyStage {
  if (activeStage === "post_variant") {
    return "post_base";
  }

  return activeStage;
}

/**
 * When there is no active survey to show, decide where the user should go next.
 */
function getNextRouteForResolvedGap(
  user: ExtendedUser | null,
  quizId?: string,
): string {
  if (!user) return "/dashboard";

  if (!user.survey_pre_base_completed) {
    return quizId ? `/survey?quiz_id=${quizId}` : "/survey";
  }

  if (!user.quiz_base_completed) {
    return "/quiz/base";
  }

  if (!user.survey_post_base_completed) {
    return "/survey";
  }

  if (!user.quiz_variant_completed) {
    return user.assigned_var ? `/quiz/${user.assigned_var}` : "/dashboard";
  }

  if (!user.survey_post_variant_completed) {
    return "/survey";
  }

  return "/dashboard";
}

export default function SurveyPage() {
  const router = useRouter();
  const { quiz_id, stage } = router.query as {
    quiz_id?: string;
    stage?: string;
  };

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

  function isUnansweredValue(value: unknown): boolean {
    if (value === undefined || value === null) return true;
    if (typeof value === "string") return value.trim() === "";
    if (typeof value === "number") return !Number.isFinite(value);
    if (Array.isArray(value)) return value.length === 0;
    return false;
  }

  const forcedStage = isActiveSurveyStage(stage) ? stage : null;

  const activeSurveyStage = forcedStage ?? resolveCurrentSurveyStage(user);
  const loadStage = activeSurveyStage ? getLoadStage(activeSurveyStage) : null;
  const config = activeSurveyStage ? STAGE_CONFIG[activeSurveyStage] : null;

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
  }, []);

  useEffect(() => {
    if (!user) return;

    if (!activeSurveyStage || !config || !loadStage) {
      setLoadingSurvey(false);
      router.replace(getNextRouteForResolvedGap(user, quiz_id));
      return;
    }

    let cancel = false;

    (async () => {
      setLoadingSurvey(true);
      setError(null);

      try {
        // Load question definitions from the mapped load stage.
        // For post_variant, this pulls the post_base questions.
        const questionState = await getSurveyState(loadStage);
        if (cancel) return;

        // Load completion status / saved answers from the actual active stage.
        // For post_variant, this reads the user's post_variant progress.
        const responseState =
          loadStage === activeSurveyStage
            ? questionState
            : await getSurveyState(activeSurveyStage);

        if (cancel) return;

        setItems(questionState.items || []);
        setStatus(responseState.status);

        const initial: Record<string, number | string | string[]> = {};
        for (const a of responseState.answers || []) {
          initial[a.item_id] = a.value;
        }
        setValues(initial);

        if (responseState.status === "completed") {
          invalidateMeCache();
          const refreshed = await getMe();
          if (cancel) return;
          router.replace(
            getNextRouteForResolvedGap(refreshed.user as ExtendedUser, quiz_id),
          );
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
  }, [user, activeSurveyStage, loadStage, config, quiz_id]);

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

      // Submit under the actual active stage.
      // For post_variant, this saves under post_variant.
      await submitSurvey(activeSurveyStage, answers);
      invalidateMeCache();

      const optimisticUser: ExtendedUser | null =
        user &&
        ({
          ...user,
          survey_pre_base_completed:
            activeSurveyStage === "pre_quiz"
              ? true
              : user.survey_pre_base_completed,
          survey_post_base_completed:
            activeSurveyStage === "post_base"
              ? true
              : user.survey_post_base_completed,
          survey_post_variant_completed:
            activeSurveyStage === "post_variant"
              ? true
              : user.survey_post_variant_completed,
        } as ExtendedUser);

      router.replace(getNextRouteForResolvedGap(optimisticUser, quiz_id));
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

        <div className="flex items-center justify-between text-sm text-gray-400">
          <span>{left}</span>
          <span>{right}</span>
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

  const surveyStepId: StepId | undefined = (() => {
    if (activeSurveyStage === "pre_quiz") return "survey_pre";
    if (activeSurveyStage === "post_base") return "survey_post_base";
    if (activeSurveyStage === "post_variant") return "survey_final";
    return undefined;
  })();

  const surveyStepNum = activeSurveyStage === "pre_quiz" ? 1 : activeSurveyStage === "post_base" ? 3 : 5;

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title={
          <>
            {config.title}
            <span className="ml-3 text-base font-normal text-gray-400">
              Step {surveyStepNum} of 5
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
