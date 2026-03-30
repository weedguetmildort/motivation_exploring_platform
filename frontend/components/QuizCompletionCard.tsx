import { type QuizResultsResponse, type QuizResultItem } from "../lib/quiz";

interface Props {
  isAdmin: boolean;
  quizResults: QuizResultsResponse | null;
  onDashboard: () => void;
  onNextStep: () => void;
  onReset?: () => void;
}

export default function QuizCompletionCard({
  isAdmin,
  quizResults,
  onDashboard,
  onNextStep,
  onReset,
}: Props) {
  return (
    <div className="rounded-xl bg-white p-6 shadow-sm border">
      <h2 className="text-lg font-semibold mb-2">
        Quiz completed{isAdmin ? " (admin view)" : ""}
      </h2>

      {quizResults && (
        <div className="mb-4">
          {isAdmin && (
            <p className="text-sm font-medium text-gray-800 mb-2">
              {quizResults.correct_count} of {quizResults.total_questions} correct
            </p>
          )}
          <ul className="space-y-1">
            {quizResults.items.map((item: QuizResultItem) => (
              <li key={item.question_id} className="text-sm text-gray-700">
                {isAdmin ? (
                  <>
                    <span className={`font-medium ${item.is_correct ? "text-green-600" : "text-red-600"}`}>
                      Question {item.question_number}
                    </span>
                    {": "}
                    answered: {item.user_choice_id.toUpperCase()}. {item.user_choice_label}
                    {!item.is_correct && (
                      <>, correct answer: {item.correct_choice_id.toUpperCase()}. {item.correct_choice_label}</>
                    )}
                  </>
                ) : (
                  <span className="text-gray-600">Question {item.question_number}: {item.stem}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={onDashboard}
          className="px-4 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 text-sm"
        >
          Back to Dashboard
        </button>
        <button
          onClick={onNextStep}
          className="px-4 py-2 rounded-lg bg-green-600 text-white text-sm hover:bg-green-700"
        >
          Continue to Next Step
        </button>
        {isAdmin && onReset && (
          <button
            onClick={onReset}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700"
          >
            Reset &amp; Retake
          </button>
        )}
      </div>
    </div>
  );
}
