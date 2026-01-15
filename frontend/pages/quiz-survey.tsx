import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { saveQuizPreSurvey } from "../lib/quizSurvey";

export default function QuizPreSurveyPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Likert states: 1–5
  const [priorExperience, setPriorExperience] = useState<number | null>(null);
  const [trustRely, setTrustRely] = useState<number | null>(null);
  const [trustGeneral, setTrustGeneral] = useState<number | null>(null);
  const [trustCountOn, setTrustCountOn] = useState<number | null>(null);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const res = await getMe();
        if (cancel) return;

        const u = res.user;
        // If already completed, send to quiz
        if (u.quiz_pre_survey_completed) {
          router.replace("/quiz");
          return;
        }
        setUser(u);
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

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading…</div>
      </div>
    );
  }

  if (!user) return null;

  function isComplete() {
    return (
      priorExperience !== null &&
      trustRely !== null &&
      trustGeneral !== null &&
      trustCountOn !== null
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!isComplete()) {
      setError("Please answer all questions before continuing.");
      return;
    }

    setSaving(true);
    try {
      await saveQuizPreSurvey({
        prior_experience: priorExperience!,
        trust_rely: trustRely!,
        trust_general: trustGeneral!,
        trust_count_on: trustCountOn!,
      });
      router.replace("/quiz");
    } catch (e) {
      console.error(e);
      setError("Failed to save your responses.");
    } finally {
      setSaving(false);
    }
  }

  function renderLikertRow(
    id: string,
    label: string,
    value: number | null,
    onChange: (v: number) => void
  ) {
    return (
      <div className="space-y-2 rounded-lg border border-gray-200 bg-white p-4">
        {/* Question text */}
        <p className="text-sm font-medium text-gray-900">{label}</p>

        {/* Scale description */}
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>1 = Strongly disagree</span>
          <span>5 = Strongly agree</span>
        </div>

        {/* Likert scale row */}
        <div className="mt-2 flex justify-between gap-2">
          {[1, 2, 3, 4, 5].map((n) => {
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
                  id={`${id}-${n}`}
                  type="radio"
                  name={id}
                  value={n}
                  checked={checked}
                  onChange={() => onChange(n)}
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

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">
              Pre-Quiz Survey
            </h1>
            <p className="text-sm text-gray-600">
              Before you start the quiz, please answer a few quick questions
              about your prior AI experience and trust. This will only be asked
              once.
            </p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/profile")}
              className="text-sm px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
            >
              Profile
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

          {/* Q1 – prior experience */}
          {renderLikertRow(
            "prior_experience",
            "I have experience using AI chatbots (e.g., ChatGPT).",
            priorExperience,
            setPriorExperience
          )}

          {/* Q2 – trust items */}
          <div className="space-y-4 pt-4 border-t border-gray-200">
            {renderLikertRow(
              "trust_rely",
              "I could rely on an AI chatbot for assistance while problem-solving.",
              trustRely,
              setTrustRely
            )}
            {renderLikertRow(
              "trust_general",
              "I could trust an AI chatbot for assistance.",
              trustGeneral,
              setTrustGeneral
            )}
            {renderLikertRow(
              "trust_count_on",
              "In general, I could count on an AI chatbot for assistance while problem-solving.",
              trustCountOn,
              setTrustCountOn
            )}
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg px-4 py-2 bg-blue-600 text-white text-sm font-medium disabled:opacity-60"
            >
              {saving ? "Saving…" : "Begin Quiz"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
