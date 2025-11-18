import React, { useEffect, useState } from "react";
import Link from "next/link";
import QuestionBox from "../components/QuestionBox";
import AnswerBox, { Choice } from "../components/AnswerBox";
import ChatBox from "../components/ChatBox";
import { getMe, type User } from "../lib/auth";
import FollowUpQuestionBox from "../components/FollowUpQuestionBox";

export default function Playground() {
  const [active, setActive] = useState("followup");
  const [question, setQuestion] = useState("Conditional Probability");
  const [subtitle, setSubtitle] = useState(
    "You have two cards: one is red/red, the other is red/blue. A card is drawn and shows red. What is the probability the other side is also red?"
  );
  const [choices, setChoices] = useState<Choice[]>([
    { id: "a", label: "A) 1/4" },
    { id: "b", label: "B) 1/3" },
    { id: "c", label: "C) 1/2" },
    { id: "d", label: "D) 2/3" },
  ]);
  const [selected, setSelected] = useState<string | null>(null);

  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  //track chat AI message + follow-up selection
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
        if (!cancel) setUser(res.user);
      } catch {
        if (!cancel) window.location.href = "/login";
      } finally {
        if (!cancel) setChecking(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, []);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading…</div>
      </div>
    );
  }
  if (!user) return null;

  const isProd = process.env.NODE_ENV === "production";

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Playground</h1>
          <Link href="/dashboard" className="text-sm text-blue-600 underline">
            Back to dashboard
          </Link>
        </header>

        {!isProd && (
          <section className="rounded-xl bg-white p-4 shadow-sm border">
            <h2 className="text-lg font-medium mb-3">Case Selection</h2>
            <div className="space-y-4 max-w-3xl mx-auto">
              <p>*Should only be visible during development*</p>
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
              </div>
              <div className="p-6 bg-white rounded-xl shadow-inner">
                {active === "base" ? (
                  <p className="text-lg text-gray-800">
                    This should be the <strong>Base Case</strong> content. Chat works, but no follow-up suggestions are shown.
                  </p>
                ) : (
                  <p className="text-lg text-gray-800">
                    This is <strong>Follow-up Question Case</strong> content. Chat works and FollowUpQuestionBox renders under the last answer.
                  </p>
                )}
              </div>
            </div>
          </section>
        )}

        <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
          {/* Left column */}
          <div className="grid gap-6 lg:grid-rows-[1fr_1fr] lg:h-full">

            <section className="rounded-xl bg-white p-4 shadow-sm border overflow-y-auto">
              <h2 className="text-lg font-medium mb-3">Question</h2>
              <div className="space-y-4">
                <QuestionBox
                  question={question}
                  subtitle={subtitle || undefined}
                  className="max-w-3xl mx-auto"
                />
              </div>
            </section>

            <section className="rounded-xl bg-white p-4 shadow-sm border overflow-y-auto">
              <h2 className="text-lg font-medium mb-3">Options</h2>
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
            </section>

          </div>

          {/* Right column (Chat) */}
            <ChatBox 
              onAssistantMessage={setLastAiMessage}
              externalQuestion={followupToSend}
              enableFollowups={active === "followup"}
            />
        </div>
      </div>
    </div>
  );
}
