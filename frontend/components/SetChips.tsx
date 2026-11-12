// A/B/C/D toggle chips. Empty selection = "no restriction" (all questions).
export const ALL_SETS = ["a", "b", "c", "d"] as const;
export type SetId = (typeof ALL_SETS)[number];

// Toggle a set letter in/out of the current selection, kept sorted & stable.
export function toggleSet(current: SetId[], s: SetId): SetId[] {
  return current.includes(s)
    ? current.filter((x) => x !== s)
    : ALL_SETS.filter((x) => x === s || current.includes(x));
}

export default function SetChips({
  value,
  onChange,
  label,
}: {
  value: SetId[];
  onChange: (next: SetId[]) => void;
  label: string;
}) {
  return (
    <span
      role="group"
      aria-label={label}
      className="inline-flex flex-wrap items-center gap-1"
    >
      {ALL_SETS.map((s) => {
        const on = value.includes(s);
        return (
          <button
            key={s}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(toggleSet(value, s))}
            className={`rounded px-1.5 py-0.5 text-xs font-medium border transition ${
              on
                ? "bg-indigo-600 text-white border-indigo-600"
                : "bg-white text-gray-500 border-gray-300 hover:bg-gray-50"
            }`}
          >
            {s.toUpperCase()}
          </button>
        );
      })}
      {value.length === 0 && (
        <span className="text-xs text-gray-400">all</span>
      )}
    </span>
  );
}
