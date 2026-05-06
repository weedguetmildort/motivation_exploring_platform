// frontend/components/ProgressBar.tsx
import type { User } from "../lib/auth";

/**
 * Step identifiers matching the actual user-visible study flow.
 * Demographics is excluded — always completed before these pages.
 *
 * Flow: Pre-Quiz Survey → Base Quiz → Post-Base Survey → Variant Quiz → Final Survey
 */
export type StepId =
  | "survey_pre"
  | "quiz_base"
  | "survey_post_base"
  | "quiz_variant"
  | "survey_final";

type Step = {
  id: StepId;
  label: string;
  abbr: string;
  completed: boolean;
};

type ProgressBarProps = {
  user: User;
  /** Explicitly mark which step the user is currently on. */
  activeStep?: StepId;
};

function buildSteps(user: User): Step[] {
  const variantAbbr = (() => {
    const v = user.assigned_var;
    if (v === "followup") return "Follow-Up";
    if (v === "double") return "Dual";
    if (v === "links") return "Links";
    return "Variant";
  })();

  return [
    { id: "survey_pre",       label: "Pre-Quiz Survey",     abbr: "Survey",      completed: !!user.survey_pre_base_completed },
    { id: "quiz_base",        label: "Base Quiz",           abbr: "Base Quiz",   completed: !!user.quiz_base_completed },
    { id: "survey_post_base", label: "Mid Survey",          abbr: "Survey",      completed: !!user.survey_post_base_completed },
    { id: "quiz_variant",     label: `${variantAbbr} Quiz`, abbr: variantAbbr,   completed: !!user.quiz_variant_completed },
    { id: "survey_final",     label: "Final Survey",        abbr: "Survey",      completed: !!user.survey_post_variant_completed },
  ];
}

export default function ProgressBar({ user, activeStep }: ProgressBarProps) {
  const steps = buildSteps(user);
  const completedCount = steps.filter((s) => s.completed).length;

  return (
    <div className="w-full rounded-xl border bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-700">Study Progress</h3>
        <span className="text-xs text-gray-500">
          {completedCount} of {steps.length} completed
        </span>
      </div>

      <div className="flex items-center">
        {steps.map((step, i) => {
          const isCompleted = step.completed;
          const isCurrent = activeStep ? step.id === activeStep : false;

          return (
            <div key={step.id} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center">
                <div
                  className={[
                    "flex items-center justify-center rounded-full transition-colors",
                    "h-7 w-7 sm:h-8 sm:w-8 border-2 text-xs sm:text-sm font-semibold",
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
                    <span>{i + 1}</span>
                  )}
                </div>

                <span
                  className={[
                    "mt-1.5 text-center leading-tight whitespace-nowrap",
                    "text-[0.6rem] sm:text-xs",
                    isCurrent
                      ? "text-accent-600 font-bold"
                      : isCompleted
                        ? "text-accent-600 font-medium"
                        : "text-gray-400",
                  ].join(" ")}
                >
                  <span className="hidden sm:inline">{step.label}</span>
                  <span className="sm:hidden">{step.abbr}</span>
                </span>
              </div>

              {i < steps.length - 1 && (
                <div
                  className={[
                    "h-[2px] flex-1 mx-1 sm:mx-2",
                    isCompleted ? "bg-accent-600" : "bg-gray-200",
                  ].join(" ")}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
