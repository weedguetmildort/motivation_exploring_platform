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

type SurveyStage = "pre_quiz" | "post_base" | "post_variant" | "complete";

type ExtendedUser = User & {
  survey_stage?: SurveyStage | null;
  survey_pre_base_completed?: boolean;
  survey_post_base_completed?: boolean;
  survey_post_variant_completed?: boolean;
};

const STAGE_CONFIG: Record<
  Exclude<SurveyStage, "complete">,
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

function isSurveyStage(value: unknown): value is SurveyStage {
  return (
    value === "pre_quiz" ||
    value === "post_base" ||
    value === "post_variant" ||
    value === "complete"
  );
}

/**
 * Returns the survey stage that should actually be shown right now.
 * Returns null when the user should not see a survey page and should be routed onward.
 */
function resolveCurrentSurveyStage(
  user: ExtendedUser | null,
): Exclude<SurveyStage, "complete"> | null {
  if (!user) return null;

  const stage = user.survey_stage;

  if (stage === "pre_quiz") {
    return user.survey_pre_base_completed ? null : "pre_quiz";
  }

  if (stage === "post_base") {
    return user.survey_post_base_completed ? null : "post_base";
  }

  if (stage === "post_variant") {
    return user.survey_post_variant_completed ? null : "post_variant";
  }

  return null;
}

/**
 * When there is no active survey to show, decide where the user should go next.
 */
function getNextRouteForResolvedGap(
  user: ExtendedUser | null,
  quizId?: string,
): string {
  if (!user) return "/dashboard";

  if (user.survey_stage === "pre_quiz" && user.survey_pre_base_completed) {
    return quizId ? `/quiz/${quizId}` : "/quiz/base";
  }

  if (user.survey_stage === "post_base" && user.survey_post_base_completed) {
    return "/quiz/variant";
  }

  if (
    user.survey_stage === "post_variant" &&
    user.survey_post_variant_completed
  ) {
    return "/dashboard";
  }

  if (user.survey_stage === "complete") {
    return "/dashboard";
  }

  return "/dashboard";
}

export default function SurveyPage() {
  const router = useRouter();
  const { quiz_id } = router.query as { quiz_id?: string };

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

  const rawSurveyStage = isSurveyStage(user?.survey_stage)
    ? user.survey_stage
    : null;

  const activeSurveyStage = resolveCurrentSurveyStage(user);
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
  }, [router]);

  useEffect(() => {
    if (!user) return;

    if (!activeSurveyStage || !config) {
      setLoadingSurvey(false);
      router.replace(getNextRouteForResolvedGap(user, quiz_id));
      return;
    }

    let cancel = false;

    (async () => {
      setLoadingSurvey(true);
      setError(null);

      try {
        const state = await getSurveyState(activeSurveyStage);
        if (cancel) return;

        setItems(state.items || []);
        setStatus(state.status);

        const initial: Record<string, number | string | string[]> = {};
        for (const a of state.answers || []) {
          initial[a.item_id] = a.value;
        }
        setValues(initial);

        if (state.status === "completed") {
          router.replace(getNextRouteForResolvedGap(user, quiz_id));
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
  }, [user, activeSurveyStage, config, quiz_id, router]);

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

      await submitSurvey(activeSurveyStage, answers);

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
          survey_stage:
            activeSurveyStage === "post_variant"
              ? "complete"
              : rawSurveyStage ?? user.survey_stage,
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
      <header className="border-b bg-white px-6 py-4">
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