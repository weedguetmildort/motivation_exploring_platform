import React from "react";

export type Choice = {
  id: string;
  label: string;
  // Optional helper text displayed under label
  description?: string;
  // If true, choice is disabled
  disabled?: boolean;
};

export type AnswerBoxProps = {
  choices: Choice[];
  value?: string | null; // controlled selected id
  defaultValue?: string | null; // uncontrolled initial selection
  onChange?: (selectedId: string) => void;
  orientation?: "vertical" | "horizontal";
  className?: string;
  // aria label for group
  ariaLabel?: string;
};

export default function AnswerBox({
  choices,
  value,
  defaultValue = null,
  onChange,
  orientation = "vertical",
  className = "",
  ariaLabel = "Answer choices",
}: AnswerBoxProps) {
  const [internal, setInternal] = React.useState<string | null>(defaultValue);
  const selected = value !== undefined ? value : internal;

  function handleSelect(id: string) {
    if (onChange) onChange(id);
    if (value === undefined) setInternal(id);
  }

  const isHorizontal = orientation === "horizontal";

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={`${className}`}
    >
      <div className={isHorizontal ? "flex flex-wrap gap-3" : "space-y-3"}>
        {choices.map((c) => {
          const active = selected === c.id;
          return (
            <label key={c.id} className={`block`}>
              <input
                type="radio"
                name="answerbox"
                value={c.id}
                className="peer sr-only"
                disabled={c.disabled}
                checked={selected === c.id}
                onChange={() => handleSelect(c.id)}
              />
              <div
                className={`cursor-pointer rounded-xl border px-4 py-3 transition-colors select-none
                ${c.disabled ? "opacity-60 cursor-not-allowed" : "hover:border-blue-400"}
                ${active ? "border-blue-600 bg-blue-50" : "border-gray-200 bg-white"}
              `}
              >
                <div className="font-medium text-gray-900">{c.label}</div>
                {c.description && (
                  <div className="text-sm text-gray-600 mt-0.5">{c.description}</div>
                )}
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}
