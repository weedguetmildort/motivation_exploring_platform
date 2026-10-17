import React, { useEffect, useState } from "react";
import Link from "next/link";
import QuestionBox, { Choice } from "../components/QuestionBox";
import ChatBox from "../components/ChatBox";
import { getMe, logout, type User } from "../lib/auth";
import { useRouter } from "next/router";
import { apiFetch } from "../lib/fetcher";
import PageHeader from "../components/PageHeader";

export default function Playground() {
  const router = useRouter();
  const [active, setActive] = useState("followup");

  const [question, setQuestion] = useState<string>("");
  const [subtitle, setSubtitle] = useState<string>("");
  const [choices, setChoices] = useState<Choice[]>([]);
  const [selected, setSelected] = useState<string | null>(null);

  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);


  useEffect(() => {
    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (!cancel) {
          if (!res.user.is_admin) {
            // Non-admin → block access and redirect
            router.replace("/dashboard");
            return;
          }
          setUser(res.user);
        }
      } catch {
        // Not logged in → send to login
        if (!cancel) router.replace("/login");
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
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  const hasQuestions = questions.length > 0;
  const atFirst = currentIndex === 0;
  const atLast = currentIndex === questions.length - 1;

  return (
    <div data-quiz-theme={active} className="min-h-screen bg-gray-50">
      <PageHeader
        title="Playground"
        subtitle="Sandbox to see how the different quiz styles look"
        onDashboard={() => router.push("/dashboard")}
        onLogout={onLogout}
      />

      <div className="page-container">
        <section className="rounded-xl bg-white p-4 shadow-sm border">
          <h2 className="text-lg 2xl:text-xl font-medium mb-3">Case Selection</h2>
          <div className="space-y-4 max-w-3xl 2xl:max-w-none mx-auto">
            <div className="flex flex-wrap justify-center gap-3 mt-8">
              {(["base", "followup", "double", "links"] as const).map((id) => (
                <div key={id} data-quiz-theme={id}>
                  <button
                    onClick={() => setActive(id)}
                    aria-pressed={active === id}
                    className={`px-6 py-3 rounded-xl font-semibold transition-all duration-300 shadow-md ${
                      active === id
                        ? "bg-accent-600 text-white shadow-lg scale-105"
                        : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                    }`}
                  >
                    {{ base: "Base Case", followup: "Follow-up Question Case", double: "Double Agent Case", links: "Embedded Links Case" }[id]}
                  </button>
                </div>
              ))}
            </div>
            <div className="p-6 bg-white rounded-xl shadow-inner">
              {active === "base" && (
                <p className="text-lg text-gray-800">
                  This should be the <strong>Base Case</strong> content. Chat
                  works, but no follow-up suggestions are shown.
                </p>
              )}
              {active === "followup" && (
                <p className="text-lg text-gray-800">
                  This is <strong>Follow-up Question Case</strong> content. Chat
                  works and FollowUpQuestionBox renders under the last answer.
                </p>
              )}
              {active === "double" && (
                <p className="text-lg text-gray-800">
                  This is <strong>Double Agent Case</strong> content. Two bots
                  independently respond to the user’s question below. Each bot
                  uses the same model but acts as a separate entity.
                </p>
              )}
              {active === "links" && (
                <p className="text-lg text-gray-800">
                  This is the <strong>Embedded Links Case</strong>. The assistant
                  searches the web and responds with inline citation links embedded
                  directly in the text.
                </p>
              )}
            </div>
          </div>
        </section>

        <div className="grid gap-6 grid-cols-1 md:grid-cols-[1fr_1.618fr] pt-6 pb-6">
          {/* Left column */}
          <div className="flex flex-col gap-6">
            <section className="rounded-xl border bg-white shadow-sm">
              {loadingQuestions && (
                <div className="p-4 text-sm text-gray-500">Loading questions…</div>
              )}

              {questionsError && (
                <div className="p-4 text-sm text-red-600">{questionsError}</div>
              )}

              {!loadingQuestions && !questionsError && !hasQuestions && (
                <div className="p-4 text-sm text-gray-500">
                  No questions available. Add some in the admin panel.
                </div>
              )}

              {hasQuestions && (
                <>
                  <div className="p-4">
                    <h2 className="text-xl 2xl:text-2xl font-semibold text-gray-900">{question}</h2>
                  </div>

                  {subtitle && (
                    <div className="px-4 pb-4">
                      <p className="text-lg 2xl:text-xl text-gray-600">{subtitle}</p>
                    </div>
                  )}

                  <hr className="border-gray-200" />

                  <div className="p-4 space-y-3">
                    <QuestionBox
                      choices={choices}
                      value={selected}
                      onChange={setSelected}
                      className="max-w-3xl 2xl:max-w-none mx-auto"
                    />
                    <div className="text-sm text-gray-600">
                      Selected:{" "}
                      <span className="font-medium">{selected ?? "(none)"}</span>
                    </div>
                  </div>
                </>
              )}
            </section>
          </div>

          {/* Right column (Chat) */}
          <div className="h-[55vh] md:h-auto md:min-h-[500px] overflow-hidden">
            <ChatBox
              key={active}
              quizId={active}
            />
          </div>
        </div>

        <div className="flex justify-between max-w-md mx-auto">
          <button
            className="rounded-xl px-4 py-2 font-medium bg-accent-600 text-white disabled:opacity-60"
            onClick={() => setCurrentIndex((idx) => (idx > 0 ? idx - 1 : idx))}
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
            className="rounded-xl px-4 py-2 font-medium bg-accent-600 text-white disabled:opacity-60"
            onClick={() =>
              setCurrentIndex((idx) =>
                idx < questions.length - 1 ? idx + 1 : idx,
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
