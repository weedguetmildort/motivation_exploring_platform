// frontend/pages/quiz/[quiz_id].tsx
import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import QuestionBox from "../../components/QuestionBox";
import AnswerBox, { Choice } from "../../components/AnswerBox";
import { getMe, logout, type User } from "../../lib/auth";
import {
  getQuizState,
  submitQuizAnswer,
  type QuizStateResponse,
} from "../../lib/quiz";
import ChatBox from "../../components/ChatBox";

type SurveyStage = "pre_quiz" | "post_base" | "post_variant" | "complete";
type QuizId = "base" | "variant";

type ExtendedUser = User & {
  survey_stage?: SurveyStage | null;
  survey_pre_base_completed?: boolean;
  quiz_base_completed?: boolean;
  survey_post_base_completed?: boolean;
  quiz_variant_completed?: boolean;
  survey_post_variant_completed?: boolean;
};

function isQuizId(value: string): value is QuizId {
  return value === "base" || value === "variant";
}

function canAccessQuiz(quizId: QuizId, user: ExtendedUser): boolean {
  //Bypass checks if user is an admin. Useful for testing
  if(user.is_admin) {
    return true;
  }
  if (quizId === "base") {
    return (
      Boolean(user.survey_pre_base_completed) &&
      !Boolean(user.quiz_base_completed)
    );
  }

  if (quizId === "variant") {
    return (
      Boolean(user.survey_post_base_completed) &&
      !Boolean(user.quiz_variant_completed)
    );
  }

  return false;
}

function getBlockedQuizRedirect(quizId: QuizId, user: ExtendedUser): string {
  if (quizId === "base") {
    if (!user.survey_pre_base_completed) return "/survey";
    if (user.quiz_base_completed && !user.survey_post_base_completed)
      return "/survey";
    if (user.survey_post_base_completed && !user.quiz_variant_completed) {
      return "/quiz/variant";
    }
    return "/dashboard";
  }

  if (quizId === "variant") {
    if (!user.survey_post_base_completed) return "/survey";
    if (user.quiz_variant_completed && !user.survey_post_variant_completed) {
      return "/survey";
    }
    return "/dashboard";
  }

  return "/dashboard";
}

export default function QuizPage() {
  const router = useRouter();
  const quizId =
    typeof router.query.quiz_id === "string"
      ? router.query.quiz_id
      : Array.isArray(router.query.quiz_id)
        ? router.query.quiz_id[0]
        : null;

  const [user, setUser] = useState<ExtendedUser | null>(null);
  const [checking, setChecking] = useState(true);

  const [quizState, setQuizState] = useState<QuizStateResponse | null>(null);
  const [selectedChoice, setSelectedChoice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [hasAskedChat, setHasAskedChat] = useState(false);
  const [externalQuestion, setExternalQuestion] = useState<string | null>(null);

  useEffect(() => {
    if (!router.isReady) return;
    if (!quizId) return;

    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (cancel) return;

        const u = res.user as ExtendedUser;

        if (!isQuizId(quizId)) {
          router.replace("/dashboard");
          return;
        }

        if (!canAccessQuiz(quizId, u)) {
          router.replace(getBlockedQuizRedirect(quizId, u));
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
  }, [router, router.isReady, quizId]);

  useEffect(() => {
    if (!user) return;
    if (!router.isReady) return;
    if (!quizId) return;
    if (!isQuizId(quizId)) return;

    let cancel = false;

    (async () => {
      try {
        const state = await getQuizState(quizId);
        if (!cancel) {
          setQuizState(state);
          setSelectedChoice(null);
        }
      } catch (e) {
        console.error(e);
        if (!cancel) setError("Failed to load quiz.");
      }
    })();

    return () => {
      cancel = true;
    };
  }, [user, router.isReady, quizId]);

  const current = quizState?.current_question ?? null;
  const attempt = quizState?.attempt;
  const conversationId = quizState?.conversation_id ?? null;
  const quizCompleted = attempt?.status === "completed";

  useEffect(() => {
    if (!current) return;
    setSelectedChoice(null);
    setHasAskedChat(false);
    setExternalQuestion(null);
  }, [current?.id]);

  useEffect(() => {
    if (!router.isReady) return;
    if (!quizCompleted) return;
    if (!quizId) return;
    if (!user) return;

    router.replace("/survey");
  }, [router.isReady, quizCompleted, quizId, user, router]);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading quiz…</div>
      </div>
    );
  }

  if (!user) return null;

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  function onAskAssistantAboutQuestion() {
    if (!current) return;

    const prompt = current.subtitle
      ? `${current.stem}\n\n${current.subtitle}`
      : current.stem;

    setExternalQuestion(prompt);
    setHasAskedChat(true);
  }

  async function onSubmit() {
    if (
      !quizId ||
      !isQuizId(quizId) ||
      !current ||
      !selectedChoice ||
      submitting
    ) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const state = await submitQuizAnswer(quizId, current.id, selectedChoice);
      setQuizState(state);
      setSelectedChoice(null);
    } catch (e) {
      console.error(e);
      setError("Failed to submit answer.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">
              Quiz {quizId}
            </h1>
            <p className="text-sm text-gray-600">
              Answer each question once. Your progress is saved automatically.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/dashboard")}
              className="text-sm px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
            >
              Back to Dashboard
            </button>
            <button
              onClick={onLogout}
              className="text-sm px-3 py-1 rounded-lg bg-gray-100 hover:bg-gray-200 transition"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto p-6 min-h-0">
        {attempt && (
          <div className="mb-4 text-sm text-gray-600">
            {attempt.answered_count} of {attempt.total_questions} answered
            {quizCompleted && (
              <span className="ml-2 font-semibold text-green-700">
                (Quiz completed)
              </span>
            )}
          </div>
        )}

        {error && (
          <div className="mb-3 text-sm text-red-600" role="alert">
            {error}
          </div>
        )}

        {quizCompleted && (
          <div className="bg-white rounded-xl p-6 shadow-sm border">
            <h2 className="text-lg font-semibold mb-2">You’re all done!</h2>
            <p className="text-sm text-gray-600">
              Redirecting you to the next survey…
            </p>
          </div>
        )}

        {!quizCompleted && (
          <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr] pt-2 px-0 pb-6 min-h-0 lg:h-[calc(100vh-180px)]">
            <div className="grid gap-6 lg:grid-rows-[1fr_1fr] min-h-0 h-full">
              <section className="rounded-xl bg-white p-4 shadow-sm border overflow-y-auto min-h-0">
                <h2 className="text-lg font-medium mb-3">Question</h2>

                {!quizState && (
                  <div className="text-sm text-gray-500">Loading quiz…</div>
                )}

                {quizState && !current && (
                  <div className="text-sm text-gray-500">
                    No current question available.
                  </div>
                )}

                {quizState && current && (
                  <div className="space-y-4">
                    <QuestionBox
                      question={current.stem}
                      subtitle={current.subtitle || undefined}
                      className="max-w-3xl mx-auto"
                    />
                  </div>
                )}
              </section>

              <section className="rounded-xl bg-white p-4 shadow-sm border overflow-y-auto min-h-0">
                <h2 className="text-lg font-medium mb-3">Options</h2>

                {!quizState || !current ? (
                  <div className="text-sm text-gray-500">
                    Options will appear once a question is available.
                  </div>
                ) : (
                  <div className="relative">
                    <div
                      className={`space-y-4 transition ${
                        !hasAskedChat
                          ? "pointer-events-none opacity-40 blur-[1px]"
                          : ""
                      }`}
                    >
                      <AnswerBox
                        choices={current.choices as Choice[]}
                        value={selectedChoice}
                        onChange={setSelectedChoice}
                        className="max-w-3xl mx-auto"
                      />
                      <div className="flex items-center justify-between text-sm text-gray-600">
                        <div>
                          Selected:{" "}
                          <span className="font-medium">
                            {selectedChoice ?? "(none)"}
                          </span>
                        </div>
                        <button
                          onClick={onSubmit}
                          disabled={!selectedChoice || submitting}
                          className="rounded-lg px-4 py-2 bg-blue-600 text-white text-sm font-medium disabled:opacity-60"
                        >
                          {submitting ? "Submitting…" : "Submit answer"}
                        </button>
                      </div>
                    </div>

                    {!hasAskedChat && (
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="rounded-xl bg-white/90 backdrop-blur shadow-md border px-6 py-4 text-center max-w-sm">
                          <p className="text-sm text-gray-800 mb-3">
                            Before choosing an answer, send this question to the
                            assistant and read the explanation.
                          </p>
                          <button
                            type="button"
                            onClick={onAskAssistantAboutQuestion}
                            className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition"
                          >
                            Ask the assistant about this question
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </section>
            </div>

            <div className="min-h-0 h-[calc(100vh-180px)] overflow-hidden">

              {quizId && (
                <ChatBox
                  quizId={quizId}
                  conversationId={conversationId}
                  externalQuestion={externalQuestion}
                  enableFollowups={false}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
