import { render, screen, fireEvent } from "@testing-library/react";
import QuizCompletionCard from "../../components/QuizCompletionCard";
import type { QuizResultsResponse } from "../../lib/quiz";

const results: QuizResultsResponse = {
  quiz_id: "base",
  total_questions: 2,
  correct_count: 1,
  items: [
    {
      question_number: 1,
      question_id: "q1",
      stem: "What is 2+2?",
      user_choice_id: "a",
      user_choice_label: "4",
      correct_choice_id: "a",
      correct_choice_label: "4",
      is_correct: true,
    },
    {
      question_number: 2,
      question_id: "q2",
      stem: "What is the capital of France?",
      user_choice_id: "b",
      user_choice_label: "London",
      correct_choice_id: "c",
      correct_choice_label: "Paris",
      is_correct: false,
    },
  ],
};

describe("QuizCompletionCard", () => {
  it("renders the basic title for non-admins without showing the score summary", () => {
    render(
      <QuizCompletionCard isAdmin={false} quizResults={results} onDashboard={jest.fn()} onNextStep={jest.fn()} />
    );

    expect(screen.getByText("Quiz completed")).toBeInTheDocument();
    expect(screen.queryByText(/of 2 correct/)).not.toBeInTheDocument();
    expect(screen.getByText(/What is 2\+2\?/)).toBeInTheDocument();
  });

  it("shows the admin title, score summary and per-question detail for admins", () => {
    render(
      <QuizCompletionCard isAdmin={true} quizResults={results} onDashboard={jest.fn()} onNextStep={jest.fn()} />
    );

    expect(screen.getByText("Quiz completed (admin view)")).toBeInTheDocument();
    expect(screen.getByText("1 of 2 correct")).toBeInTheDocument();
    expect(screen.getByText(/correct answer: C\. Paris/)).toBeInTheDocument();
  });

  it("does not render the results section when quizResults is null", () => {
    render(<QuizCompletionCard isAdmin={false} quizResults={null} onDashboard={jest.fn()} onNextStep={jest.fn()} />);
    expect(screen.queryByText(/Question 1/)).not.toBeInTheDocument();
  });

  it("calls onDashboard and onNextStep when their buttons are clicked", () => {
    const onDashboard = jest.fn();
    const onNextStep = jest.fn();
    render(
      <QuizCompletionCard isAdmin={false} quizResults={null} onDashboard={onDashboard} onNextStep={onNextStep} />
    );

    fireEvent.click(screen.getByText("Back to Dashboard"));
    fireEvent.click(screen.getByText("Continue to Next Step"));
    expect(onDashboard).toHaveBeenCalled();
    expect(onNextStep).toHaveBeenCalled();
  });

  it("shows the Reset & Retake button only for admins with onReset provided", () => {
    const onReset = jest.fn();
    const { rerender } = render(
      <QuizCompletionCard isAdmin={true} quizResults={null} onDashboard={jest.fn()} onNextStep={jest.fn()} onReset={onReset} />
    );
    fireEvent.click(screen.getByText("Reset & Retake"));
    expect(onReset).toHaveBeenCalled();

    rerender(
      <QuizCompletionCard isAdmin={false} quizResults={null} onDashboard={jest.fn()} onNextStep={jest.fn()} onReset={onReset} />
    );
    expect(screen.queryByText("Reset & Retake")).not.toBeInTheDocument();
  });
});
