type MentionSuggestionsProps = {
  visible: boolean;
  agents: string[];
  selectedIndex: number;
  onSelect: (agent: string) => void;
};

export default function MentionSuggestions({
  visible,
  agents,
  selectedIndex,
  onSelect,
}: MentionSuggestionsProps) {
  if (!visible || agents.length === 0) {
    return null;
  }

  return (
    <div className="absolute bottom-full mb-2 left-0 bg-white border rounded-lg shadow-lg z-50 w-48">
      <div className="py-1">
        {agents.map((agent, index) => (
          <button
            key={agent}
            onClick={() => onSelect(agent)}
            className={`w-full text-left px-4 py-2 cursor-pointer ${
              index === selectedIndex
                ? "bg-blue-500 text-white"
                : "hover:bg-gray-100"
            }`}
          >
            @{agent}
          </button>
        ))}
      </div>
    </div>
  );
}
