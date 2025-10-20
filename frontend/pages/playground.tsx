import React, { useState } from "react";
import Link from "next/link";
import QuestionBox from "../components/QuestionBox";
import AnswerBox, { Choice } from "../components/AnswerBox";

export default function Playground() {
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

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Components Playground</h1>
          <Link href="/" className="text-blue-600 hover:underline">Home</Link>
        </header>

        <section className="rounded-xl bg-white p-4 shadow-sm border">
          <h2 className="text-lg font-medium mb-3">QuestionBox Controls</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="block text-sm text-gray-600 mb-1">Question</span>
              <input
                type="text"
                className="w-full rounded-md border px-3 py-2"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Enter question text"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="block text-sm text-gray-600 mb-1">Subtitle (optional)</span>
              <textarea
                className="w-full rounded-md border px-3 py-2"
                value={subtitle}
                onChange={(e) => setSubtitle(e.target.value)}
                rows={3}
                placeholder="Add an optional subtitle"
              />
            </label>
          </div>
        </section>

        <section>
          <QuestionBox question={question} subtitle={subtitle || undefined} className="max-w-3xl mx-auto" />
        </section>

        <section className="rounded-xl bg-white p-4 shadow-sm border">
          <h2 className="text-lg font-medium mb-3">AnswerBox</h2>
          <div className="space-y-4">
            <AnswerBox
              choices={choices}
              value={selected}
              onChange={setSelected}
              className="max-w-3xl"
            />
            <div className="text-sm text-gray-600">
              Selected: <span className="font-medium">{selected ?? "(none)"}</span>
            </div>
          </div>
        </section>

        <section className="rounded-xl bg-white p-4 shadow-sm border">
          <h2 className="text-lg font-medium mb-3">Edit Choices</h2>
          <div className="space-y-3">
            {choices.map((c, idx) => (
              <div key={c.id} className="flex gap-2 items-center">
                <input
                  type="text"
                  className="flex-1 rounded-md border px-3 py-2"
                  value={c.label}
                  onChange={(e) => {
                    const next = [...choices];
                    next[idx] = { ...c, label: e.target.value };
                    setChoices(next);
                  }}
                />
                <button
                  className="px-3 py-2 rounded-md border text-sm"
                  onClick={() => {
                    const next = choices.filter((x) => x.id !== c.id);
                    setChoices(next);
                    if (selected === c.id) setSelected(null);
                  }}
                >
                  Remove
                </button>
              </div>
            ))}
            <button
              className="px-3 py-2 rounded-md border text-sm"
              onClick={() => {
                const id = Math.random().toString(36).slice(2, 7);
                setChoices((prev) => [...prev, { id, label: `Option ${prev.length + 1}` }]);
              }}
            >
              Add Choice
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
