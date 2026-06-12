import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SurveyPage from "../../pages/survey";
import { getMe, logout, invalidateMeCache } from "../../lib/auth";
import { getSurveyState, submitSurvey } from "../../lib/surveys";

const mockReplace = jest.fn();
const mockPush = jest.fn();
let mockQuery: Record<string, string> = {};
jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush, query: mockQuery }),
}));

jest.mock("../../lib/auth", () => ({
  getMe: jest.fn(),
  logout: jest.fn(),
  invalidateMeCache: jest.fn(),
}));

jest.mock("../../lib/surveys", () => ({
  getSurveyState: jest.fn(),
  submitSurvey: jest.fn(),
}));

jest.mock("../../components/ProgressBar", () => () => <div data-testid="progress-bar" />);

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockInvalidateMeCache = invalidateMeCache as jest.Mock;
const mockGetSurveyState = getSurveyState as jest.Mock;
const mockSubmitSurvey = submitSurvey as jest.Mock;

const baseUser = {
  id: "1",
  email: "user@example.com",
  is_admin: false,
  demographics_completed: true,
  assigned_var: "followup",
  survey_pre_base_completed: false,
  quiz_base_completed: false,
  survey_post_base_completed: false,
  quiz_variant_completed: false,
  survey_post_variant_completed: false,
};

const likertItem = {
  id: "item1",
  stage: "pre_quiz",
  prompt: "I feel motivated to learn.",
  type: "likert" as const,
  required: true,
  scale_min: 1,
  scale_max: 5,
  scale_left_label: "Strongly disagree",
  scale_right_label: "Strongly agree",
};

const textItem = {
  id: "item2",
  stage: "pre_quiz",
  prompt: "Any other comments?",
  type: "text" as const,
  required: false,
};

describe("SurveyPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockInvalidateMeCache.mockReset();
    mockGetSurveyState.mockReset();
    mockSubmitSurvey.mockReset();
    mockQuery = {};
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<SurveyPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<SurveyPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("redirects when there is no active survey stage to show", async () => {
    mockGetMe.mockResolvedValue({
      user: { ...baseUser, survey_pre_base_completed: true, quiz_base_completed: false },
    });
    render(<SurveyPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/quiz/base"));
    expect(mockGetSurveyState).not.toHaveBeenCalled();
  });

  it("loads and renders likert survey items for the pre-quiz stage", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockResolvedValue({
      stage: "pre_quiz",
      status: "not_started",
      items: [likertItem],
      answers: [],
    });

    render(<SurveyPage />);

    expect(await screen.findByText("Pre-Quiz Survey")).toBeInTheDocument();
    expect(await screen.findByText(likertItem.prompt)).toBeInTheDocument();
    expect(mockGetSurveyState).toHaveBeenCalledWith("pre_quiz");

    expect(screen.getAllByRole("radio")).toHaveLength(5);
    expect(screen.getByText("Strongly disagree")).toBeInTheDocument();
    expect(screen.getByText("Strongly agree")).toBeInTheDocument();
  });

  it("renders an unsupported-type message for non-likert items", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockResolvedValue({
      stage: "pre_quiz",
      status: "not_started",
      items: [textItem],
      answers: [],
    });

    render(<SurveyPage />);

    expect(await screen.findByText(textItem.prompt)).toBeInTheDocument();
    expect(screen.getByText(/Unsupported question type:/)).toBeInTheDocument();
    expect(screen.getByText("text")).toBeInTheDocument();
  });

  it("shows the empty message when there are no survey items", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockResolvedValue({
      stage: "pre_quiz",
      status: "not_started",
      items: [],
      answers: [],
    });

    render(<SurveyPage />);

    expect(
      await screen.findByText(/No survey items found for the pre-quiz survey/),
    ).toBeInTheDocument();
  });

  it("shows a load error when fetching the survey fails", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockRejectedValue(new Error("network error"));

    render(<SurveyPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to load the pre-quiz survey.");
  });

  it("redirects automatically when the survey is already completed", async () => {
    mockGetMe
      .mockResolvedValueOnce({ user: baseUser })
      .mockResolvedValueOnce({ user: { ...baseUser, survey_pre_base_completed: true } });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockResolvedValue({
      stage: "pre_quiz",
      status: "completed",
      items: [likertItem],
      answers: [],
    });

    render(<SurveyPage />);

    await waitFor(() => expect(mockInvalidateMeCache).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/quiz/base"));
  });

  it("shows a validation error when required questions are unanswered", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockResolvedValue({
      stage: "pre_quiz",
      status: "not_started",
      items: [likertItem],
      answers: [],
    });

    render(<SurveyPage />);

    await screen.findByText(likertItem.prompt);
    fireEvent.click(screen.getByRole("button", { name: "Begin Base Quiz" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Please answer all required questions before continuing.",
    );
    expect(mockSubmitSurvey).not.toHaveBeenCalled();
  });

  it("submits answers and redirects on success", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockResolvedValue({
      stage: "pre_quiz",
      status: "not_started",
      items: [likertItem],
      answers: [],
    });
    mockSubmitSurvey.mockResolvedValue({ ok: true });

    render(<SurveyPage />);

    await screen.findByText(likertItem.prompt);

    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[2]);

    fireEvent.click(screen.getByRole("button", { name: "Begin Base Quiz" }));

    await waitFor(() =>
      expect(mockSubmitSurvey).toHaveBeenCalledWith("pre_quiz", [{ item_id: "item1", value: 3 }]),
    );
    await waitFor(() => expect(mockInvalidateMeCache).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/quiz/base"));
  });

  it("shows an error message when submitting fails", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockResolvedValue({
      stage: "pre_quiz",
      status: "not_started",
      items: [likertItem],
      answers: [],
    });
    mockSubmitSurvey.mockRejectedValue(new Error("network error"));

    render(<SurveyPage />);

    await screen.findByText(likertItem.prompt);

    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[0]);

    fireEvent.click(screen.getByRole("button", { name: "Begin Base Quiz" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to save your responses.");
  });

  it("loads post-base questions but reads/writes response state under post-variant", async () => {
    const completedUser = {
      ...baseUser,
      survey_pre_base_completed: true,
      quiz_base_completed: true,
      survey_post_base_completed: true,
      quiz_variant_completed: true,
    };
    mockGetMe.mockResolvedValue({ user: completedUser });
    mockQuery = { stage: "post_variant" };

    mockGetSurveyState.mockImplementation((s: string) => {
      if (s === "post_base") {
        return Promise.resolve({
          stage: "post_base",
          status: "not_started",
          items: [likertItem],
          answers: [],
        });
      }
      return Promise.resolve({
        stage: "post_variant",
        status: "not_started",
        items: [],
        answers: [{ item_id: "item1", value: 4 }],
      });
    });
    mockSubmitSurvey.mockResolvedValue({ ok: true });

    render(<SurveyPage />);

    expect(await screen.findByText(likertItem.prompt)).toBeInTheDocument();
    expect(mockGetSurveyState).toHaveBeenCalledWith("post_base");
    expect(mockGetSurveyState).toHaveBeenCalledWith("post_variant");

    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios[3].checked).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Finish" }));

    await waitFor(() =>
      expect(mockSubmitSurvey).toHaveBeenCalledWith("post_variant", [{ item_id: "item1", value: 4 }]),
    );
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
  });

  it("navigates to the dashboard when the Dashboard button is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockResolvedValue({
      stage: "pre_quiz",
      status: "not_started",
      items: [],
      answers: [],
    });

    render(<SurveyPage />);
    await screen.findByText("Pre-Quiz Survey");

    fireEvent.click(screen.getByText("Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockLogout.mockResolvedValue(undefined);
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockResolvedValue({
      stage: "pre_quiz",
      status: "not_started",
      items: [],
      answers: [],
    });

    render(<SurveyPage />);
    await screen.findByText("Pre-Quiz Survey");

    fireEvent.click(screen.getByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
