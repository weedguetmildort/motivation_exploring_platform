// frontend/components/ChatHeader.tsx
import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { getQuizTheme } from "../lib/quizTheme";

type ChatHeaderProps = {
  quizId: string;
  questionCollapsed?: boolean;
  onToggleQuestion?: () => void;
};

export default function ChatHeader({
  quizId,
  questionCollapsed,
  onToggleQuestion,
}: ChatHeaderProps) {
  const theme = getQuizTheme(quizId);
  const [showInfo, setShowInfo] = useState(false);
  const [popoverPos, setPopoverPos] = useState<{ top: number; left: number } | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!showInfo) {
      setPopoverPos(null);
      return;
    }

    const raf = requestAnimationFrame(() => {
      if (!buttonRef.current || !popoverRef.current) return;
      const btn = buttonRef.current.getBoundingClientRect();
      const pop = popoverRef.current.getBoundingClientRect();
      const margin = 8;

      let left = btn.left;
      if (left + pop.width > window.innerWidth - margin) {
        left = window.innerWidth - margin - pop.width;
      }
      left = Math.max(margin, left);

      let top = btn.bottom + 8;
      if (top + pop.height > window.innerHeight - margin) {
        top = btn.top - pop.height - 8;
      }

      setPopoverPos({ top, left });
    });

    return () => cancelAnimationFrame(raf);
  }, [showInfo]);

  useEffect(() => {
    if (!showInfo) return;
    function handleClickOutside(e: MouseEvent) {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(e.target as Node)
      ) {
        setShowInfo(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showInfo]);

  return (
    <div className="px-4 py-3 border-b sticky top-0 bg-white/90 backdrop-blur rounded-t-2xl flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-600">
          <svg
            className="h-5 w-5 text-white"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        </div>

        <h2 className="text-xl font-semibold text-gray-900 2xl:text-2xl">
          AI Assistant
          {theme.id !== "base" && (
            <span className="font-normal text-gray-500">
              {" "}&middot; {theme.subtitle}
            </span>
          )}
        </h2>

        <div className="relative">
          <button
            ref={buttonRef}
            type="button"
            onClick={() => setShowInfo((v) => !v)}
            className="flex h-5 w-5 items-center justify-center rounded-full border border-gray-300 text-xs font-bold text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition"
            aria-label="About this assistant type"
          >
            ?
          </button>

          {showInfo && createPortal(
            <div
              ref={popoverRef}
              data-quiz-theme={quizId}
              style={
                popoverPos
                  ? { position: "fixed", top: popoverPos.top, left: popoverPos.left }
                  : { position: "fixed", visibility: "hidden", top: 0, left: 0 }
              }
              className="z-50 w-72 max-w-[calc(100vw-1rem)] rounded-xl border bg-white p-4 shadow-lg"
            >
              <div className="flex items-center gap-2 mb-2">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-600">
                  <svg
                    className="h-3.5 w-3.5 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
                </div>
                <span className="font-semibold text-gray-900">{theme.subtitle}</span>
              </div>
              <p className="text-sm text-gray-600 leading-relaxed">
                {theme.description}
              </p>
              <p className="mt-3 text-xs text-gray-400 leading-relaxed border-t border-gray-100 pt-2">
                AI can make mistakes. Always verify important information and use your own judgment when answering.
              </p>
            </div>,
            document.body
          )}
        </div>
      </div>

      {onToggleQuestion && (
        <button
          type="button"
          className="md:hidden inline-flex items-center gap-1 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-600 shadow-sm transition hover:bg-gray-50 hover:text-gray-900 active:scale-95"
          onClick={onToggleQuestion}
          aria-label={questionCollapsed ? "Minimize question" : "Maximize question"}
        >
          {questionCollapsed ? (
            <>
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
              Minimize
            </>
          ) : (
            <>
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
              </svg>
              Maximize
            </>
          )}
        </button>
      )}
    </div>
  );
}
