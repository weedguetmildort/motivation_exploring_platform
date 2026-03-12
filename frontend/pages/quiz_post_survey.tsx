import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import {
  getSurveyState,
  submitSurvey,
  type SurveyItem,
  type SurveyAnswer,
} from "../lib/surveys";

export default function QuizPostSurveyPage() {
  const router = useRouter();

  // Always load the question definitions from post_quiz
  const QUESTION_STAGE = "post_quiz";

  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [loadingSurvey, setLoadingSurvey] = useState(true);
  const [items, setItems] = useState<SurveyItem[]>([]);
  const [status, setStatus] = useState<
    "not_started" | "in_progress" | "completed"
  >("not_started");
  const [values, setValues] = useState<
    Record<string, number | string | string[]>
  >({});

  if (!user) return null;

  const surveyStage = user.survey_stage;

  if (!surveyStage) {
    setError("No survey stage is assigned to this user.");
    return null;
  }

  useEffect(() => {
    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (cancel) return;
        setUser(res.user);
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
    if (!user.survey_stage) {
      setError("No survey stage is assigned to this user.");
      setLoadingSurvey(false);
      return;
    }

    let cancel = false;

    (async () => {
      setLoadingSurvey(true);
      setError(null);

      try {
        // 1) Load shared question definitions from post_quiz
        const questionState = await getSurveyState(QUESTION_STAGE);
        if (cancel) return;

        // 2) Load this user's actual response state from their current survey stage
        const responseState = await getSurveyState(surveyStage);
        if (cancel) return;

        setItems(questionState.items || []);
        setStatus(responseState.status);

        const initial: Record<string, number | string | string[]> = {};
        for (const a of responseState.answers || []) {
          initial[a.item_id] = a.value;
        }
        setValues(initial);

        // Redirect only if the user's current survey stage is already completed
        if (responseState.status === "completed") {
          router.replace("/dashboard");
          return;
        }
      } catch (e) {
        console.error(e);
        if (!cancel) setError("Failed to load the survey.");
      } finally {
        if (!cancel) setLoadingSurvey(false);
      }
    })();

    return () => {
      cancel = true;
    };
  }, [user, router]);

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

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading…</div>
      </div>
    );
  }

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
    setError(null);

    if (!surveyStage) {
      setError("No survey stage is assigned to this user.");
      return;
    }

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

      await submitSurvey(surveyStage, answers);

      router.replace("/dashboard");
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

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">
              Post Survey
            </h1>
            <p className="text-sm text-gray-600">
              A few quick questions now that you’ve finished.
            </p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="text-sm px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
            >
              Back to Dashboard
            </button>
            <button
              onClick={onLogout}
              className="bg-gray-100 hover:bg-gray-200 px-4 py-2 rounded-lg text-sm"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto p-6">
        <form
          onSubmit={onSubmit}
          className="space-y-6 rounded-xl bg-white p-6 shadow-sm border"
        >
          {error && (
            <div className="text-sm text-red-600" role="alert">
              {error}
            </div>
          )}

          {loadingSurvey ? (
            <div className="text-sm text-gray-500">Loading survey…</div>
          ) : items.length === 0 ? (
            <div className="text-sm text-gray-500">
              No survey items found for stage{" "}
              <span className="font-medium">{QUESTION_STAGE}</span>.
            </div>
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
                  className="rounded-lg px-4 py-2 bg-blue-600 text-white text-sm font-medium disabled:opacity-60"
                >
                  {saving ? "Saving…" : "Finish"}
                </button>
              </div>
            </>
          )}
        </form>
      </main>
    </div>
  );
}
