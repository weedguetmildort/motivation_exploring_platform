// frontend/pages/quiz/[quiz_id].tsx
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/router";
import AnswerBox, { Choice } from "../../components/AnswerBox";
import { getMe, logout, type User } from "../../lib/auth";
import {
  getQuizState,
  submitQuizAnswer,
  resetQuiz,
  getQuizResults,
  type QuizStateResponse,
  type QuizResultsResponse,
} from "../../lib/quiz";
import ChatBox from "../../components/ChatBox";
import QuizCompletionCard from "../../components/QuizCompletionCard";

type SurveyStage = "pre_quiz" | "post_base" | "post_variant" | "complete";

const VARIANT_QUIZ_IDS = ["followup", "links", "double"] as const;
type VariantQuizId = (typeof VARIANT_QUIZ_IDS)[number];
type QuizId = "base" | VariantQuizId;

type ExtendedUser = User & {
  assigned_var?: VariantQuizId | string | null;
  survey_stage?: SurveyStage | null;
  survey_pre_base_completed?: boolean;
  quiz_base_completed?: boolean;
  survey_post_base_completed?: boolean;
  quiz_variant_completed?: boolean;
  survey_post_variant_completed?: boolean;
};

function isVariantQuizId(value: string): value is VariantQuizId {
  return (VARIANT_QUIZ_IDS as readonly string[]).includes(value);
}

function isValidQuizId(value: string, user?: ExtendedUser | null): boolean {
  if (user?.is_admin) return true;
  return value === "base" || isVariantQuizId(value);
}

function isUsersAssignedVariant(
  quizId: string,
  user?: ExtendedUser | null,
): boolean {
  return Boolean(user?.assigned_var && quizId === user.assigned_var);
}

function canAccessQuiz(quizId: QuizId, user: ExtendedUser): boolean {
  if (user.is_admin) {
    return true;
  }

  if (quizId === "base") {
    return !!user.survey_pre_base_completed && !user.quiz_base_completed;
  }

  return (
    isUsersAssignedVariant(quizId, user) &&
    !!user.survey_post_base_completed &&
    !user.quiz_variant_completed
  );
}

function getBlockedQuizRedirect(quizId: QuizId, user: ExtendedUser): string {
  const assignedVariantPath = user.assigned_var
    ? `/quiz/${user.assigned_var}`
    : "/dashboard";

  if (quizId === "base") {
    if (!user.survey_pre_base_completed) return "/survey";

    if (!user.survey_post_base_completed) {
      return "/survey";
    }

    if (!user.quiz_variant_completed) {
      return assignedVariantPath;
    }

    if (user.quiz_variant_completed && !user.survey_post_variant_completed) {
      return "/survey";
    }

    return "/dashboard";
  }

  if (!user.survey_post_base_completed) return "/survey";

  if (user.quiz_variant_completed && !user.survey_post_variant_completed) {
    return "/survey";
  }

  return "/dashboard";
}

export default function QuizPage() {
  const router = useRouter();
  const rawQuizId = [router.query.quiz_id].flat()[0] ?? null;

  const [user, setUser] = useState<ExtendedUser | null>(null);
  const [checking, setChecking] = useState(true);

  const [quizState, setQuizState] = useState<QuizStateResponse | null>(null);
  const [selectedChoice, setSelectedChoice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [quizResults, setQuizResults] = useState<QuizResultsResponse | null>(null);
  const [hasAskedChat, setHasAskedChat] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [externalQuestion, setExternalQuestion] = useState<string | null>(null);
  const [firstChatResponded, setFirstChatResponded] = useState(false);
  const [questionCollapsed, setQuestionCollapsed] = useState(false);
  const lastResetQuestionId = useRef<string | undefined>(undefined);

  const quizId =
    rawQuizId && (rawQuizId === "base" || isVariantQuizId(rawQuizId))
      ? (rawQuizId as QuizId)
      : null;

  useEffect(() => {
    if (!router.isReady) return;
    if (!rawQuizId) return;

    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (cancel) return;

        const u = res.user as ExtendedUser;

        if (!isValidQuizId(rawQuizId, u)) {
          router.replace("/dashboard");
          return;
        }

        if (!u.is_admin) {
          if (rawQuizId !== "base" && !isUsersAssignedVariant(rawQuizId, u)) {
            router.replace("/dashboard");
            return;
          }
        }

        if (!quizId) {
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
  }, [router, router.isReady, rawQuizId, quizId]);

  useEffect(() => {
    if (!user) return;
    if (!router.isReady) return;
    if (!quizId) return;

    // Reset stale state immediately so quizCompleted doesn't briefly read as
    // true from a previous quiz while the new state loads.
    setQuizState(null);
    setQuizResults(null);
    lastResetQuestionId.current = undefined;

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
    // Skip if this is the same question re-appearing after a quizState null reset
    if (lastResetQuestionId.current === current.id) return;
    lastResetQuestionId.current = current.id;
    setSelectedChoice(null);
    setHasAskedChat(false);
    setChatLoading(false);
    setExternalQuestion(null);
    setFirstChatResponded(false);
    setQuestionCollapsed(false);
  }, [current?.id]);

  async function redirectAfterCompletion() {
    if (!quizId) return;
    try {
      const res = await getMe();
      const refreshedUser = res.user as ExtendedUser;

      if (quizId === "base") {
        if (!refreshedUser.survey_post_base_completed) {
          router.replace("/survey?stage=post_base");
          return;
        }

        if (!refreshedUser.quiz_variant_completed) {
          router.replace(
            refreshedUser.assigned_var
              ? `/quiz/${refreshedUser.assigned_var}`
              : "/dashboard",
          );
          return;
        }

        if (
          refreshedUser.quiz_variant_completed &&
          !refreshedUser.survey_post_variant_completed
        ) {
          router.replace("/survey");
          return;
        }

        router.replace("/dashboard");
        return;
      }

      // Variant quiz completed
      if (!refreshedUser.survey_post_variant_completed) {
        router.replace("/survey?stage=post_variant");
        return;
      }

      router.replace("/dashboard");
    } catch (e) {
      console.error(e);
      router.replace("/survey");
    }
  }

  useEffect(() => {
    if (!quizCompleted || !user || !quizId) return;
    let cancel = false;
    getQuizResults(quizId).then((r) => { if (!cancel) setQuizResults(r); }).catch(() => {});
    return () => { cancel = true; };
  }, [quizCompleted, user, quizId]);

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

    const choicesText = current.choices
      .map((c) => `${c.id.toUpperCase()}. ${c.label}`)
      .join("\n");

    const parts = [current.stem];
    if (current.subtitle) parts.push(current.subtitle);
    parts.push(`Answer choices:\n${choicesText}`);

    setExternalQuestion(parts.join("\n\n"));
    setHasAskedChat(true);
  }

  async function onSubmit() {
    if (!quizId || !current || !selectedChoice || submitting) {
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
    <div className="flex flex-col h-[100dvh] [@media(max-height:700px)]:h-auto bg-gray-50">
      <header className="shrink-0 bg-white border-b px-4 py-3 sm:px-6 sm:py-4">
        <div className="site-header-inner">
          <div>
            <h1 className="page-title">
              Quiz {quizId ?? rawQuizId}
              {attempt && (
                <span className="ml-3 text-base 2xl:text-lg font-normal text-gray-500">
                  {attempt.answered_count} of {attempt.total_questions} answered
                  {quizCompleted && (
                    <span className="ml-2 font-semibold text-green-700">(Completed)</span>
                  )}
                </span>
              )}
            </h1>
            {!quizCompleted && (
              <p className="page-subtitle">
                Answer each question once. Your progress is saved automatically.
              </p>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => router.replace("/dashboard")}
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

      <div className="flex-1 min-h-0 md:overflow-auto [@media(max-height:700px)]:flex-none">
        <div className="max-w-6xl 2xl:max-w-screen-2xl mx-auto px-3 py-2 md:px-6 md:py-6 h-full md:h-auto [@media(max-height:700px)]:h-auto">
          <div className="flex flex-col gap-2 md:gap-4 h-full md:h-auto [@media(max-height:700px)]:h-auto">
            {error && (
              <div className="text-sm text-red-600" role="alert">
                {error}
              </div>
            )}

            {quizCompleted ? (
              <div className="overflow-auto flex-1 min-h-0 md:flex-none">
              <QuizCompletionCard
                isAdmin={user.is_admin}
                quizResults={quizResults}
                onDashboard={() => router.replace("/dashboard")}
                onNextStep={redirectAfterCompletion}
                onReset={user.is_admin ? async () => {
                  if (!quizId) return;
                  await resetQuiz(quizId);
                  const state = await getQuizState(quizId);
                  setQuizState(state);
                  setSelectedChoice(null);
                  setQuizResults(null);
                } : undefined}
              />
              </div>
            ) : (
              <div className="flex-1 min-h-0 md:flex-none [@media(max-height:700px)]:flex-none flex flex-col md:grid min-w-0 md:grid-cols-[1fr_1.618fr] gap-3 md:gap-6">
                <div className="shrink-0 flex flex-col gap-3 md:gap-6">
                  <section className="rounded-xl border bg-white shadow-sm">
                    {!quizState && (
                      <div className="p-4 text-sm text-gray-500">Loading quiz…</div>
                    )}

                    {quizState && !current && (
                      <div className="p-4 text-sm text-gray-500">
                        No current question available.
                      </div>
                    )}

                    {quizState && current && (
                      <>
                        <div className="p-4">
                          <h2 className="text-xl 2xl:text-2xl font-semibold text-gray-900">
                            Question {(attempt?.answered_count ?? 0) + 1} — {current.stem}
                          </h2>
                        </div>

                        {current.subtitle && (
                            <div className="px-4 pb-4">
                              <p className="text-lg 2xl:text-xl text-gray-600">{current.subtitle}</p>
                            </div>
                          )}

                          <hr className="border-gray-200" />

                          <div className={`relative p-4${questionCollapsed ? " hidden md:block" : ""}`}>
                            <div
                              className={`space-y-3 transition ${
                                !hasAskedChat
                                  ? "pointer-events-none opacity-40 blur-[1px]"
                                  : ""
                              }`}
                            >
                              <AnswerBox
                                choices={current.choices as Choice[]}
                                value={selectedChoice}
                                onChange={setSelectedChoice}
                                className="max-w-3xl 2xl:max-w-none mx-auto"
                              />

                              <div className="flex items-center justify-between text-sm text-gray-600 pt-1">
                                <div>
                                  Selected:{" "}
                                  <span className="font-medium">
                                    {selectedChoice?.toUpperCase() ?? "(none)"}
                                  </span>
                                </div>

                                <button
                                  onClick={onSubmit}
                                  disabled={
                                    !selectedChoice || submitting || chatLoading
                                  }
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
                                    Before choosing an answer, send this question to
                                    the assistant and read the explanation.
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
                      </>
                    )}
                  </section>
                </div>

                <div className="flex-1 min-h-0 md:flex-none [@media(max-height:700px)]:flex-none [@media(max-height:700px)]:min-h-[420px] min-w-0 md:self-start md:sticky md:top-0 md:h-[min(calc(100vh-9rem),80vw)]">
                  {quizId && (
                    <div className="h-full min-w-0 rounded-2xl overflow-hidden">
                      <ChatBox
                        quizId={quizId}
                        conversationId={conversationId}
                        externalQuestion={externalQuestion}
                        onLoadingChange={setChatLoading}
                        onHistoryLoaded={() => setHasAskedChat(true)}
                        disableCancel={!firstChatResponded}
                        onAssistantMessage={() => setFirstChatResponded(true)}
                        questionCollapsed={questionCollapsed}
                        onToggleQuestion={() => setQuestionCollapsed((c: boolean) => !c)}
                      />
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
