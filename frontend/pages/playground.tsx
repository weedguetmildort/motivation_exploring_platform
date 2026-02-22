import React, { useEffect, useState } from "react";
import Link from "next/link";
import QuestionBox from "../components/QuestionBox";
import AnswerBox, { Choice } from "../components/AnswerBox";
import ChatBox from "../components/ChatBox";
import { getMe, logout, type User } from "../lib/auth";
import FollowUpQuestionBox from "../components/FollowUpQuestionBox";
import { useRouter } from "next/router";
import { apiFetch } from "../lib/fetcher";

export default function Playground() {
  const router = useRouter();
  const [active, setActive] = useState("followup");

  const [question, setQuestion] = useState<string>("");
  const [subtitle, setSubtitle] = useState<string>("");
  const [choices, setChoices] = useState<Choice[]>([]);
  const [selected, setSelected] = useState<string | null>(null);

  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  // Track chat AI message + follow-up selection
  const [lastAiMessage, setLastAiMessage] = useState<string | null>(null);
  const [selectedFollowup, setSelectedFollowup] = useState<string | null>(null);
  const [followupToSend, setFollowupToSend] = useState<string | null>(null);

  function handleFollowupClick(question: string) {
    setSelectedFollowup(question);
    setFollowupToSend(question);
    console.log("Follow-up option clicked:", question);
  }

  useEffect(() => {
    if (lastAiMessage) {
      setFollowupToSend(null);
    }
  }, [lastAiMessage]);

  useEffect(() => {
    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (!cancel) {
          if (!res.user.is_admin) {
            // Non-admin → block access and redirect
            window.location.href = "/dashboard";
            return;
          }
          setUser(res.user);
        }
      } catch {
        // Not logged in → send to login
        if (!cancel) window.location.href = "/login";
      } finally {
        if (!cancel) setChecking(false);
      }
    })();

    return () => {
      cancel = true;
    };
  }, []);

  type QuestionDoc = {
    id: string;
    stem: string;
    subtitle?: string | null;
    choices: { id: string; label: string }[];
  };

  const [questions, setQuestions] = useState<QuestionDoc[]>([]);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [questionsError, setQuestionsError] = useState<string | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);

  // Load questions once we know the user (and they’re admin)
  useEffect(() => {
    if (!user) return;

    let cancel = false;

    async function loadQuestions() {
      setLoadingQuestions(true);
      setQuestionsError(null);
      try {
        // Use the same path style that works in admin (with trailing slash)
        const data = await apiFetch<QuestionDoc[]>("/api/questions/");
        if (!cancel) {
          setQuestions(data);
          setCurrentIndex(0);
        }
      } catch (e) {
        console.error("Failed to load questions for playground:", e);
        if (!cancel) setQuestionsError("Failed to load questions.");
      } finally {
        if (!cancel) setLoadingQuestions(false);
      }
    }

    loadQuestions();

    return () => {
      cancel = true;
    };
  }, [user]);

  useEffect(() => {
    if (!questions.length) return;
    const q = questions[currentIndex];
    setQuestion(q.stem);
    setSubtitle(q.subtitle || "");
    setChoices(q.choices as Choice[]);
    setSelected(null); // reset selection when changing question
  }, [questions, currentIndex]);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading…</div>
      </div>
    );
  }
  if (!user) return null;

  async function onLogout() {
    try { await logout(); } finally { router.replace("/login"); }
  }

  const hasQuestions = questions.length > 0;
  const atFirst = currentIndex === 0;
  const atLast = currentIndex === questions.length - 1;

  return (
    <div className="min-h-screen bg-gray-50">

      <header className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Playground</h1>
            <p className="text-sm text-gray-600">Sandbox to see how the different quiz styles look</p>
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

      <div className="max-w-6xl mx-auto p-6">
        
          <section className="rounded-xl bg-white p-4 shadow-sm border">
            <h2 className="text-lg font-medium mb-3">Case Selection</h2>
            <div className="space-y-4 max-w-3xl mx-auto">
              <div className="flex justify-center gap-4 mt-8">
                <button
                  onClick={() => setActive("base")}
                  aria-pressed={active === "base"}
                  className={`px-6 py-3 rounded-xl font-semibold transition-all duration-300 shadow-md ${
                    active === "base"
                      ? "bg-blue-600 text-white shadow-lg scale-105"
                      : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                  }`}
                >
                  Base Case
                </button>
                <button
                  onClick={() => setActive("followup")}
                  aria-pressed={active === "followup"}
                  className={`px-6 py-3 rounded-xl font-semibold transition-all duration-300 shadow-md ${
                    active === "followup"
                      ? "bg-blue-600 text-white shadow-lg scale-105"
                      : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                  }`}
                >
                  Follow-up Question Case
                </button>
                <button
                  onClick={() => setActive("double")}
                  aria-pressed={active === "double"}
                  className={`px-6 py-3 rounded-xl font-semibold transition-all duration-300 shadow-md ${
                    active === "double"
                      ? "bg-blue-600 text-white shadow-lg scale-105"
                      : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                  }`}
                >
                  Double Agent Case
                </button>
              </div>
              <div className="p-6 bg-white rounded-xl shadow-inner">
                {active === "base" && (
                  <p className="text-lg text-gray-800">
                    This should be the <strong>Base Case</strong> content. Chat works, but no follow-up suggestions are shown.
                  </p>
                )}
                {active === "followup" && (
                  <p className="text-lg text-gray-800">
                    This is <strong>Follow-up Question Case</strong> content. Chat works and FollowUpQuestionBox renders under the last answer.
                  </p>
                )}
                {active === "double" && (
                  <p className="text-lg text-gray-800">
                    This is <strong>Double Agent Case</strong> content. Two bots independently respond to the user’s question below. Each bot uses the same model but acts as a separate entity.
                  </p>
                )}
              </div>
            </div>
          </section>
        

        <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr] pt-6 px-0 pb-6">
          {/* Left column */}
          <div className="grid gap-6 lg:grid-rows-[1fr_1fr] lg:h-full">

            <section className="rounded-xl bg-white p-4 shadow-sm border overflow-y-auto">
              <h2 className="text-lg font-medium mb-3">Question</h2>

              {loadingQuestions && (
                <div className="text-sm text-gray-500">Loading questions…</div>
              )}

              {questionsError && (
                <div className="text-sm text-red-600">{questionsError}</div>
              )}

              {!loadingQuestions && !questionsError && !hasQuestions && (
                <div className="text-sm text-gray-500">
                  No questions available. Add some in the admin panel.
                </div>
              )}

              {hasQuestions && (
                <div className="space-y-4">
                  <QuestionBox
                    question={question}
                    subtitle={subtitle || undefined}
                    className="max-w-3xl mx-auto"
                  />
                </div>
              )}
            </section>

            <section className="rounded-xl bg-white p-4 shadow-sm border overflow-y-auto">
              <h2 className="text-lg font-medium mb-3">Options</h2>
              
              {!hasQuestions ? (
                <div className="text-sm text-gray-500">
                  Options will appear once there is at least one question.
                </div>
              ) : (
                <div className="space-y-4">
                  <AnswerBox
                    choices={choices}
                    value={selected}
                    onChange={setSelected}
                    className="max-w-3xl mx-auto"
                  />
                  <div className="text-sm text-gray-600">
                    Selected:{" "}
                    <span className="font-medium">{selected ?? "(none)"}</span>
                  </div>
                </div>
              )}

            </section>

          </div>

          {/* Right column (Chat) */}
          <ChatBox
            onAssistantMessage={setLastAiMessage}
            externalQuestion={followupToSend}
            enableFollowups={active === "followup"}
            doubleAgent={active === "double"}
          />
        </div>

        <div className="flex justify-between max-w-md mx-auto">
          <button
            className="rounded-xl px-4 py-2 font-medium bg-blue-600 text-white disabled:opacity-60"
            onClick={() =>
              setCurrentIndex((idx) => (idx > 0 ? idx - 1 : idx))
            }
            disabled={!hasQuestions || atFirst}
          >
            Previous
          </button>
          <span className="text-sm text-gray-600 self-center">
            {hasQuestions
              ? `Question ${currentIndex + 1} of ${questions.length}`
              : "No questions"}
          </span>
          <button
            className="rounded-xl px-4 py-2 font-medium bg-blue-600 text-white disabled:opacity-60"
            onClick={() =>
              setCurrentIndex((idx) =>
                idx < questions.length - 1 ? idx + 1 : idx
              )
            }
            disabled={!hasQuestions || atLast}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
