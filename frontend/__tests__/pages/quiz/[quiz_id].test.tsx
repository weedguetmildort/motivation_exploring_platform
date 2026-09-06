import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import QuizPage from "../../../pages/quiz/[quiz_id]";
import { getMe, invalidateMeCache, logout, type User } from "../../../lib/auth";
import {
  getQuizState,
  submitQuizAnswer,
  resetQuiz,
  getQuizResults,
  type QuizStateResponse,
  type QuizResultsResponse,
} from "../../../lib/quiz";
import { createReport } from "../../../lib/reports";
import { getNextStep } from "../../../lib/study";

const mockReplace = jest.fn();
const mockPush = jest.fn();
let currentQuery: Record<string, any> = { quiz_id: "base" };
let currentIsReady = true;

jest.mock("next/router", () => ({
  useRouter: () => ({
    query: currentQuery,
    isReady: currentIsReady,
    replace: mockReplace,
    push: mockPush,
  }),
}));

jest.mock("../../../lib/auth", () => ({
  getMe: jest.fn(),
  invalidateMeCache: jest.fn(),
  logout: jest.fn(),
}));

jest.mock("../../../lib/quiz", () => ({
  getQuizState: jest.fn(),
  submitQuizAnswer: jest.fn(),
  resetQuiz: jest.fn(),
  getQuizResults: jest.fn(),
}));

jest.mock("../../../lib/reports", () => ({
  createReport: jest.fn(),
}));

// Routing is delegated to the backend (GET /study/next); the page no longer
// derives it from the user's completion flags.
jest.mock("../../../lib/study", () => ({
  getNextStep: jest.fn(),
}));

let lastChatBoxProps: any = null;
jest.mock("../../../components/ChatBox", () => (props: any) => {
  lastChatBoxProps = props;
  return (
    <div data-testid="chat-box">
      <button onClick={() => props.onHistoryLoaded?.()}>trigger-history-loaded</button>
      <button onClick={() => props.onLoadingChange?.(true)}>trigger-loading-on</button>
      <button onClick={() => props.onLoadingChange?.(false)}>trigger-loading-off</button>
      <button onClick={() => props.onToggleQuestion?.()}>trigger-toggle-question</button>
    </div>
  );
});

const mockGetMe = getMe as jest.Mock;
const mockInvalidateMeCache = invalidateMeCache as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockGetQuizState = getQuizState as jest.Mock;
const mockSubmitQuizAnswer = submitQuizAnswer as jest.Mock;
const mockResetQuiz = resetQuiz as jest.Mock;
const mockGetQuizResults = getQuizResults as jest.Mock;
const mockCreateReport = createReport as jest.Mock;
const mockGetNextStep = getNextStep as jest.Mock;

/** A /study/next response whose current step is `quizId`. */
function nextIsQuiz(quizId: string) {
  return {
    next_step: {
      id: `quiz:${quizId}`,
      kind: "quiz",
      key: quizId,
      label: "Quiz Part 1",
      route: `/quiz/${quizId}`,
      variant: quizId === "base" ? null : quizId,
      completed: false,
    },
    next_route: `/quiz/${quizId}`,
    completed_count: 1,
    total_steps: 9,
    finished: false,
  };
}

/** A /study/next response pointing somewhere other than a quiz. */
function nextIsRoute(route: string) {
  return {
    next_step: {
      id: "survey:post_base", kind: "survey", key: "post_base",
      label: "Survey 2", route, variant: null, completed: false,
    },
    next_route: route,
    completed_count: 2,
    total_steps: 9,
    finished: false,
  };
}

const FLOW_ORDER = [
  "survey:pre_quiz",
  "quiz:base",
  "survey:post_base",
  "quiz:followup",
  "survey:post_followup",
  "quiz:double",
  "survey:post_double",
  "quiz:links",
  "survey:post_links",
];

function baseUser(overrides: Partial<User> = {}): User {
  return {
    id: "1",
    email: "user@example.com",
    is_admin: false,
    assigned_var: "followup",
    step_order: FLOW_ORDER,
    completed_steps: ["survey:pre_quiz"],
    survey_pre_base_completed: true,
    quiz_base_completed: false,
    survey_post_base_completed: false,
    quiz_variant_completed: false,
    survey_post_variant_completed: false,
    ...overrides,
  };
}

const adminUser: User = {
  id: "admin1",
  email: "admin@example.com",
  is_admin: true,
  assigned_var: null,
};

const quizStateQ1: QuizStateResponse = {
  conversation_id: "conv1",
  attempt: {
    quiz_id: "base",
    status: "in_progress",
    total_questions: 3,
    answered_count: 0,
    incorrect_question_ids: [],
  },
  current_question: {
    id: "q1",
    stem: "What is 2+2?",
    subtitle: "Basic arithmetic",
    choices: [
      { id: "a", label: "3" },
      { id: "b", label: "4" },
    ],
  },
};

const quizStateQ2: QuizStateResponse = {
  conversation_id: "conv1",
  attempt: {
    quiz_id: "base",
    status: "in_progress",
    total_questions: 3,
    answered_count: 1,
    incorrect_question_ids: [],
  },
  current_question: {
    id: "q2",
    stem: "What is 3+3?",
    choices: [
      { id: "a", label: "5" },
      { id: "b", label: "6" },
    ],
  },
};

const quizStateCompleted: QuizStateResponse = {
  conversation_id: "conv1",
  attempt: {
    quiz_id: "base",
    status: "completed",
    total_questions: 3,
    answered_count: 3,
    incorrect_question_ids: ["q2"],
  },
  current_question: null,
};

const quizStateNoCurrent: QuizStateResponse = {
  conversation_id: "conv1",
  attempt: {
    quiz_id: "base",
    status: "in_progress",
    total_questions: 3,
    answered_count: 0,
    incorrect_question_ids: [],
  },
  current_question: null,
};

const quizResults: QuizResultsResponse = {
  quiz_id: "base",
  total_questions: 3,
  correct_count: 2,
  items: [
    {
      question_number: 1,
      question_id: "q1",
      stem: "What is 2+2?",
      user_choice_id: "a",
      user_choice_label: "Answer A",
      correct_choice_id: "a",
      correct_choice_label: "Answer A",
      is_correct: true,
    },
    {
      question_number: 2,
      question_id: "q2",
      stem: "What is 3+3?",
      user_choice_id: "b",
      user_choice_label: "Answer B",
      correct_choice_id: "c",
      correct_choice_label: "Answer C",
      is_correct: false,
    },
  ],
};

function setRoute(quizId: string | null, isReady = true) {
  currentQuery = quizId === null ? {} : { quiz_id: quizId };
  currentIsReady = isReady;
}

describe("QuizPage ([quiz_id])", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockInvalidateMeCache.mockReset();
    mockLogout.mockReset();
    mockGetQuizState.mockReset();
    mockSubmitQuizAnswer.mockReset();
    mockResetQuiz.mockReset();
    mockGetQuizResults.mockReset();
    mockCreateReport.mockReset();
    mockGetNextStep.mockReset();
    lastChatBoxProps = null;
    mockGetNextStep.mockResolvedValue(nextIsQuiz("base"));

    setRoute("base");
    mockGetQuizState.mockResolvedValue(quizStateQ1);
    mockGetQuizResults.mockResolvedValue(quizResults);
    mockResetQuiz.mockResolvedValue({ ok: true });
  });

  it("shows a loading state while the router is not ready", () => {
    setRoute("base", false);
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<QuizPage />);

    expect(screen.getByText("Loading quiz…")).toBeInTheDocument();
    expect(mockGetMe).not.toHaveBeenCalled();
  });

  it("shows a loading state while the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<QuizPage />);

    expect(screen.getByText("Loading quiz…")).toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<QuizPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("sends a participant wherever /study/next points when this is not their current step", async () => {
    setRoute("links");
    mockGetMe.mockResolvedValue({ user: baseUser() });
    mockGetNextStep.mockResolvedValue(nextIsRoute("/survey?stage=post_base"));

    render(<QuizPage />);

    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith("/survey?stage=post_base"),
    );
  });

  it("admits a participant to the quiz that is their current step", async () => {
    setRoute("followup");
    mockGetMe.mockResolvedValue({ user: baseUser() });
    mockGetNextStep.mockResolvedValue(nextIsQuiz("followup"));

    render(<QuizPage />);

    await waitFor(() => expect(mockGetQuizState).toHaveBeenCalledWith("followup"));
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("does not consult the flow for admins, who may open any quiz", async () => {
    setRoute("links");
    mockGetMe.mockResolvedValue({ user: adminUser });

    render(<QuizPage />);

    await waitFor(() => expect(mockGetQuizState).toHaveBeenCalledWith("links"));
    expect(mockGetNextStep).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("renders the base quiz for an admin user with the correct header and subtitle", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<QuizPage />);

    expect(await screen.findByText("Quiz Part 1")).toBeInTheDocument();
    expect(screen.getByText("Step 2 of 5")).toBeInTheDocument();
    expect(
      screen.getByText("Answer each of the questions using the help of the AI assistant."),
    ).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("labels a variant quiz by its position in the participant's own flow", async () => {
    // followup is the 4th step overall and the 2nd quiz, of a 9-step flow.
    setRoute("followup");
    mockGetMe.mockResolvedValue({
      user: baseUser({
        completed_steps: ["survey:pre_quiz", "quiz:base", "survey:post_base"],
      }),
    });
    mockGetNextStep.mockResolvedValue(nextIsQuiz("followup"));

    render(<QuizPage />);

    expect(await screen.findByText("Quiz Part 2")).toBeInTheDocument();
    expect(screen.getByText("Step 4 of 9")).toBeInTheDocument();
  });

  it("numbers the later variant quizzes past the old two-quiz ceiling", async () => {
    setRoute("links");
    mockGetMe.mockResolvedValue({
      user: baseUser({ completed_steps: FLOW_ORDER.slice(0, 7) }),
    });
    mockGetNextStep.mockResolvedValue(nextIsQuiz("links"));

    render(<QuizPage />);

    expect(await screen.findByText("Quiz Part 4")).toBeInTheDocument();
    expect(screen.getByText("Step 8 of 9")).toBeInTheDocument();
  });

  it("loads and displays the current question with its choices and progress", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<QuizPage />);

    expect(await screen.findByText("Question 1 — What is 2+2?")).toBeInTheDocument();
    expect(screen.getByText("Basic arithmetic")).toBeInTheDocument();
    expect(screen.getByText("1 of 3")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Ask the assistant about this question")).toBeInTheDocument();
    expect(screen.getByText("(none)")).toBeInTheDocument();
    expect(lastChatBoxProps.answerIncorrectly).toBe(false);
    expect(lastChatBoxProps.questionId).toBe("q1");
  });

  it("shows an error message when loading the quiz state fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetQuizState.mockRejectedValue(new Error("network error"));
    render(<QuizPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to load quiz.");
  });

  it("shows a message when there is no current question", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetQuizState.mockResolvedValue(quizStateNoCurrent);
    render(<QuizPage />);

    expect(await screen.findByText("No current question available.")).toBeInTheDocument();
  });

  it("passes answerIncorrectly=true to ChatBox when the current question was previously missed", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetQuizState.mockResolvedValue({
      ...quizStateQ1,
      attempt: { ...quizStateQ1.attempt, incorrect_question_ids: ["q1"] },
    });
    render(<QuizPage />);

    await screen.findByText("Question 1 — What is 2+2?");
    expect(lastChatBoxProps.answerIncorrectly).toBe(true);
  });

  it("reveals the question and enables answer selection after asking the assistant", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<QuizPage />);

    await screen.findByText("Question 1 — What is 2+2?");

    fireEvent.click(screen.getByText("Ask the assistant about this question"));

    expect(screen.queryByText("Ask the assistant about this question")).not.toBeInTheDocument();
    expect(lastChatBoxProps.externalQuestion).toContain("What is 2+2?");
    expect(lastChatBoxProps.externalQuestion).toContain("Basic arithmetic");
    expect(lastChatBoxProps.externalQuestion).toContain("A. 3");
    expect(lastChatBoxProps.externalQuestion).toContain("B. 4");

    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[1]);

    expect(screen.getByText("B")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit answer" })).not.toBeDisabled();
  });

  it("opens the report form, submits it, and shows a success message", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockCreateReport.mockResolvedValue({ id: "r1" });
    render(<QuizPage />);

    await screen.findByText("Question 1 — What is 2+2?");

    fireEvent.click(screen.getByText("Report an issue"));

    const select = screen.getByDisplayValue("Other");
    fireEvent.change(select, { target: { value: "unclear_question" } });

    const textarea = screen.getByPlaceholderText("Describe the issue…");
    fireEvent.change(textarea, { target: { value: "This question is confusing." } });

    fireEvent.click(screen.getByRole("button", { name: "Submit report" }));

    await waitFor(() =>
      expect(mockCreateReport).toHaveBeenCalledWith({
        category: "unclear_question",
        description: "This question is confusing.",
        quiz_id: "base",
        question_id: "q1",
      })
    );

    expect(await screen.findByText("Report submitted — thank you!")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Describe the issue…")).not.toBeInTheDocument();
  });

  it("shows an error message when report submission fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockCreateReport.mockRejectedValue(new Error("server error"));
    render(<QuizPage />);

    await screen.findByText("Question 1 — What is 2+2?");

    fireEvent.click(screen.getByText("Report an issue"));
    fireEvent.change(screen.getByPlaceholderText("Describe the issue…"), {
      target: { value: "Broken choice" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit report" }));

    expect(
      await screen.findByText("Failed to submit report. Please try again.")
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Describe the issue…")).toBeInTheDocument();
  });

  it("disables the submit report button until a description is entered", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<QuizPage />);

    await screen.findByText("Question 1 — What is 2+2?");
    fireEvent.click(screen.getByText("Report an issue"));

    expect(screen.getByRole("button", { name: "Submit report" })).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("Describe the issue…"), {
      target: { value: "Broken choice" },
    });

    expect(screen.getByRole("button", { name: "Submit report" })).not.toBeDisabled();
  });

  it("closes the report form when Cancel is clicked without submitting", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<QuizPage />);

    await screen.findByText("Question 1 — What is 2+2?");
    fireEvent.click(screen.getByText("Report an issue"));
    expect(screen.getByPlaceholderText("Describe the issue…")).toBeInTheDocument();

    const cancelButtons = screen.getAllByRole("button", { name: "Cancel" });
    fireEvent.click(cancelButtons[cancelButtons.length - 1]);

    expect(screen.queryByPlaceholderText("Describe the issue…")).not.toBeInTheDocument();
    expect(mockCreateReport).not.toHaveBeenCalled();
  });

  it("submits the selected answer and advances to the next question", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockSubmitQuizAnswer.mockResolvedValue(quizStateQ2);
    render(<QuizPage />);

    await screen.findByText("Question 1 — What is 2+2?");
    fireEvent.click(screen.getByText("Ask the assistant about this question"));

    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[1]);

    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }));

    await waitFor(() => expect(mockSubmitQuizAnswer).toHaveBeenCalledWith("base", "q1", "b"));

    expect(await screen.findByText("Question 2 — What is 3+3?")).toBeInTheDocument();
    expect(screen.getByText("2 of 3")).toBeInTheDocument();
    expect(screen.getByText("(none)")).toBeInTheDocument();
    expect(screen.getByText("Ask the assistant about this question")).toBeInTheDocument();
  });

  it("shows an error message when submitting an answer fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockSubmitQuizAnswer.mockRejectedValue(new Error("server error"));
    render(<QuizPage />);

    await screen.findByText("Question 1 — What is 2+2?");
    fireEvent.click(screen.getByText("Ask the assistant about this question"));

    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[0]);

    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to submit answer.");
  });

  it("disables the submit button while the chat is loading", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<QuizPage />);

    await screen.findByText("Question 1 — What is 2+2?");
    fireEvent.click(screen.getByText("Ask the assistant about this question"));

    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[0]);

    const submitButton = screen.getByRole("button", { name: "Submit answer" });
    expect(submitButton).not.toBeDisabled();

    fireEvent.click(screen.getByText("trigger-loading-on"));
    expect(submitButton).toBeDisabled();

    fireEvent.click(screen.getByText("trigger-loading-off"));
    expect(submitButton).not.toBeDisabled();
  });

  it("toggles the question section's collapsed class via the chat box", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<QuizPage />);

    await screen.findByText("Question 1 — What is 2+2?");
    const questionSection = screen.getByRole("radiogroup").parentElement!.parentElement!;
    expect(questionSection.className).not.toContain("hidden");

    fireEvent.click(screen.getByText("trigger-toggle-question"));
    expect(questionSection.className).toContain("hidden md:block");

    fireEvent.click(screen.getByText("trigger-toggle-question"));
    expect(questionSection.className).not.toContain("hidden");
  });

  it("renders the quiz completion card with admin details when the attempt is completed", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetQuizState.mockResolvedValue(quizStateCompleted);
    render(<QuizPage />);

    expect(await screen.findByText("Quiz completed (admin view)")).toBeInTheDocument();
    expect(screen.getByText("(Done)")).toBeInTheDocument();
    expect(await screen.findByText("2 of 3 correct")).toBeInTheDocument();
    expect(screen.getByText(/Question 1/)).toBeInTheDocument();
    expect(screen.getByText(/answered: A\. Answer A/)).toBeInTheDocument();
    expect(screen.getByText(/correct answer: C\. Answer C/)).toBeInTheDocument();
  });

  it("renders the quiz completion card without admin details for non-admin users", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser() });
    mockGetQuizState.mockResolvedValue(quizStateCompleted);
    render(<QuizPage />);

    expect(await screen.findByText("Quiz completed")).toBeInTheDocument();
    expect(screen.queryByText("Quiz completed (admin view)")).not.toBeInTheDocument();
    expect(screen.queryByText("2 of 3 correct")).not.toBeInTheDocument();
    expect(await screen.findByText("Question 1: What is 2+2?")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Reset/ })).not.toBeInTheDocument();
  });

  it("resets and retakes the quiz when an admin clicks Reset & Retake", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetQuizState
      .mockResolvedValueOnce(quizStateCompleted)
      .mockResolvedValueOnce(quizStateQ1);
    render(<QuizPage />);

    await screen.findByText("Quiz completed (admin view)");

    fireEvent.click(screen.getByRole("button", { name: /Reset/ }));

    await waitFor(() => expect(mockResetQuiz).toHaveBeenCalledWith("base"));
    expect(mockInvalidateMeCache).toHaveBeenCalled();
    expect(await screen.findByText("Question 1 — What is 2+2?")).toBeInTheDocument();
    expect(screen.queryByText("Quiz completed (admin view)")).not.toBeInTheDocument();
  });

  it("routes to whatever /study/next returns after finishing a quiz", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser() });
    mockGetQuizState.mockResolvedValue(quizStateCompleted);
    mockGetNextStep
      .mockResolvedValueOnce(nextIsQuiz("base"))
      .mockResolvedValue(nextIsRoute("/survey?stage=post_base"));

    render(<QuizPage />);

    const next = await screen.findByText("Continue to Next Step");
    fireEvent.click(next);

    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith("/survey?stage=post_base"),
    );
    expect(mockInvalidateMeCache).toHaveBeenCalled();
  });

  it("sends a finished participant to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser() });
    mockGetQuizState.mockResolvedValue(quizStateCompleted);
    mockGetNextStep
      .mockResolvedValueOnce(nextIsQuiz("base"))
      .mockResolvedValue({
        next_step: null, next_route: "/dashboard",
        completed_count: 9, total_steps: 9, finished: true,
      });

    render(<QuizPage />);

    fireEvent.click(await screen.findByText("Continue to Next Step"));

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
  });

  it("falls back to the dashboard when the next-step lookup fails", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser() });
    mockGetQuizState.mockResolvedValue(quizStateCompleted);
    mockGetNextStep
      .mockResolvedValueOnce(nextIsQuiz("base"))
      .mockRejectedValue(new Error("network"));

    render(<QuizPage />);

    fireEvent.click(await screen.findByText("Continue to Next Step"));

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
  });

  it("navigates to the dashboard when the header Dashboard button is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<QuizPage />);

    await screen.findByText("Quiz Part 1");
    fireEvent.click(screen.getByText("Dashboard"));

    expect(mockReplace).toHaveBeenCalledWith("/dashboard");
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockLogout.mockResolvedValue(undefined);
    render(<QuizPage />);

    await screen.findByText("Quiz Part 1");
    fireEvent.click(screen.getByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
