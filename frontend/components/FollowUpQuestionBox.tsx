import React, { useEffect, useState } from "react";
import { sendFollowupChat } from "../lib/chat";

export type FollowUpQuestionBoxProps = {
  lastAiMessage: string | null;
  onOptionClick: (question: string) => void;
};

export default function FollowUpQuestionBox({
  lastAiMessage,
  onOptionClick,
}: FollowUpQuestionBoxProps) {
  const [options, setOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!lastAiMessage || lastAiMessage.trim().length === 0) {
      setOptions([]);
      setLoading(false);
      setError(null);
      return;
    }

    async function fetchOptions() {
      setLoading(true);
      setError(null);
      try {
        const questions = await sendFollowupChat(lastAiMessage!);
        setOptions(questions);
      } catch (e) {
        console.error("Error generating follow-up question(s):", e);
        setError("Could not load follow-up questions.");
        setOptions([]);
      } finally {
        setLoading(false);
      }
    }
    fetchOptions();
  }, [lastAiMessage]);

  if (!lastAiMessage || lastAiMessage.trim().length === 0) {
    return (
      <div className="mt-4 border-t border-gray-200 pt-3">
        <div className="mb-2 text-sm font-semibold text-gray-900">
          Follow-up Questions
        </div>
        <div className="text-xs text-gray-500">
          Ask a question in the chat and wait for the AI to respond to see
          suggested follow-up questions here.
        </div>
      </div>
    );
  }

  return (
    <div className="mt-4 border-t border-gray-200 pt-3">
      <div className="mb-2 text-sm font-semibold text-gray-900">
        Follow-up Questions
      </div>
      {loading && (
        <div className="text-xs text-gray-500">Generating options...</div>
      )}
      {error && (
        <div className="text-xs text-red-600 mb-2">{error}</div>
      )}
      {!loading && !error && options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {options.map((q, idx) => (
            <button
              key={idx}
              type="button"
              className="text-xs px-3 py-1 rounded-full border border-gray-300 bg-white hover:bg-gray-100 transition"
              onClick={() => onOptionClick(q)}
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
