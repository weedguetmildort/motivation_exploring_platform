// frontend/components/ProgressBar.tsx
import { useState } from "react";
import { buildStudySteps, type StudyStepId, type StudyStep } from "../lib/studySteps";
import type { User } from "../lib/auth";

// Re-exported so existing imports of `StepId` from this file keep working.
export type { StudyStepId as StepId };

type ProgressBarProps = {
  user: User;
  /** Explicitly mark which step the user is currently on. */
  activeStep?: StudyStepId;
  /** Show a minimize/maximize toggle in the card header. */
  collapsible?: boolean;
  /** Force horizontal layout at sm+ (instead of going vertical again at lg+). */
  horizontal?: boolean;
};

function StepCircle({ step, index, isCurrent, isCompleted }: {
  step: StudyStep; index: number; isCurrent: boolean; isCompleted: boolean;
}) {
  return (
    <div
      className={[
        "flex shrink-0 items-center justify-center rounded-full border-2 transition-colors font-semibold",
        "h-8 w-8 text-xs",
        isCurrent
          ? "border-accent-600 bg-white text-accent-600 ring-[3px] ring-accent-600/25"
          : isCompleted
            ? "border-accent-600 bg-accent-600 text-white"
            : "border-gray-300 bg-white text-gray-400",
      ].join(" ")}
    >
      {isCompleted && !isCurrent ? (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <span>{index + 1}</span>
      )}
    </div>
  );
}

export default function ProgressBar({ user, activeStep, collapsible, horizontal }: ProgressBarProps) {
  const steps = buildStudySteps(user);
  const completedCount = steps.filter((s) => s.completed).length;
  const [open, setOpen] = useState(true);

  return (
    <div className="w-full rounded-xl border bg-white shadow-sm">
      {/* Card header — always visible */}
      <div className={`flex items-center justify-between px-4 py-3 ${open ? "border-b border-gray-100" : ""}`}>
        <h3 className="text-sm font-semibold text-gray-700">Study Progress</h3>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">{completedCount} of {steps.length} completed</span>
          {collapsible && (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-white px-2.5 py-1 text-xs font-medium text-gray-600 shadow-sm hover:bg-gray-50 hover:text-gray-900 transition active:scale-95"
              aria-label={open ? "Collapse progress" : "Expand progress"}
            >
              {open ? (
                <>
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
                  </svg>
                  Minimize
                </>
              ) : (
                <>
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                  Expand
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {open && (
        <div className="px-4 pb-4 pt-3">
          {/* Vertical: < sm always; lg+ only when not forced horizontal */}
          <div className={`flex flex-col ${horizontal ? "sm:hidden" : "sm:hidden lg:flex"}`}>
            {steps.map((step, i) => {
              const isCompleted = step.completed;
              const isCurrent = activeStep ? step.id === activeStep : false;
              return (
                <div key={step.id}>
                  <div className="flex items-center gap-3">
                    <StepCircle step={step} index={i} isCurrent={isCurrent} isCompleted={isCompleted} />
                    <span className={[
                      "text-sm leading-tight",
                      isCurrent ? "text-accent-600 font-semibold"
                        : isCompleted ? "text-accent-600 font-medium"
                        : "text-gray-400",
                    ].join(" ")}>
                      {step.label}
                    </span>
                  </div>
                  {i < steps.length - 1 && (
                    <div className={[
                      "ml-[15px] w-[2px] h-5 my-0.5",
                      isCompleted ? "bg-accent-600" : "bg-gray-200",
                    ].join(" ")} />
                  )}
                </div>
              );
            })}
          </div>

          {/* Horizontal: sm–lg normally; sm+ when forced horizontal */}
          <div className={`hidden sm:flex items-center ${horizontal ? "" : "lg:hidden"}`}>
            {steps.map((step, i) => {
              const isCompleted = step.completed;
              const isCurrent = activeStep ? step.id === activeStep : false;
              return (
                <div key={step.id} className="flex items-center flex-1 last:flex-none">
                  <div className="flex flex-col items-center">
                    <StepCircle step={step} index={i} isCurrent={isCurrent} isCompleted={isCompleted} />
                    <span className={[
                      "mt-1.5 text-center leading-tight whitespace-nowrap text-[0.6rem]",
                      isCurrent ? "text-accent-600 font-bold"
                        : isCompleted ? "text-accent-600 font-medium"
                        : "text-gray-400",
                    ].join(" ")}>
                      {step.label}
                    </span>
                  </div>
                  {i < steps.length - 1 && (
                    <div className={[
                      "h-[2px] flex-1 mx-1 mb-5",
                      isCompleted ? "bg-accent-600" : "bg-gray-200",
                    ].join(" ")} />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
