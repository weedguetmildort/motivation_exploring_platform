import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SurveyPage from "../../pages/survey";
import { getMe, logout, invalidateMeCache } from "../../lib/auth";
import { getSurveyState, submitSurvey } from "../../lib/surveys";
import { getNextStep } from "../../lib/study";

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

// Which survey is current, and where the participant goes next, are decided by
// the backend (GET /study/next) rather than derived from completion flags.
jest.mock("../../lib/study", () => ({
  getNextStep: jest.fn(),
}));

jest.mock("../../components/ProgressBar", () => () => <div data-testid="progress-bar" />);

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockInvalidateMeCache = invalidateMeCache as jest.Mock;
const mockGetSurveyState = getSurveyState as jest.Mock;
const mockSubmitSurvey = submitSurvey as jest.Mock;
const mockGetNextStep = getNextStep as jest.Mock;

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

/** A /study/next response whose current step is the survey at `stage`. */
function nextIsSurvey(stage: string, label = "Survey 1") {
  return {
    next_step: {
      id: `survey:${stage}`,
      kind: "survey",
      key: stage,
      label,
      route: `/survey?stage=${stage}`,
      variant: null,
      completed: false,
    },
    next_route: `/survey?stage=${stage}`,
    completed_count: 0,
    total_steps: FLOW_ORDER.length,
    finished: false,
  };
}

/** A /study/next response pointing at something that is not a survey. */
function nextIsRoute(route: string) {
  return {
    next_step: {
      id: "quiz:base", kind: "quiz", key: "base",
      label: "Quiz Part 1", route, variant: null, completed: false,
    },
    next_route: route,
    completed_count: 1,
    total_steps: FLOW_ORDER.length,
    finished: false,
  };
}

/** Survey state in the shape the API actually returns (status under attempt). */
function surveyState(items: any[], answers: any[] = [], status = "in_progress") {
  return {
    attempt: { stage: "pre_quiz", status, answered_count: answers.length, total_items: items.length },
    items,
    answers,
  };
}

const baseUser = {
  id: "1",
  email: "user@example.com",
  is_admin: false,
  demographics_completed: true,
  assigned_var: "followup",
  step_order: FLOW_ORDER,
  completed_steps: [] as string[],
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
    mockGetNextStep.mockReset();
    mockQuery = {};
    mockGetNextStep.mockResolvedValue(nextIsSurvey("pre_quiz"));
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

  it("redirects when the current step is not a survey", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockGetNextStep.mockResolvedValue(nextIsRoute("/quiz/base"));

    render(<SurveyPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/quiz/base"));
    expect(mockGetSurveyState).not.toHaveBeenCalled();
  });

  it("redirects a stale ?stage= link to the survey actually owed", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "post_variant" };
    mockGetNextStep.mockResolvedValue(nextIsSurvey("post_followup", "Survey 3"));

    render(<SurveyPage />);

    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith("/survey?stage=post_followup"),
    );
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

    expect(await screen.findByText("Survey 1")).toBeInTheDocument();
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
      await screen.findByText(/No survey items found for this survey/),
    ).toBeInTheDocument();
  });

  it("shows a load error when fetching the survey fails", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockRejectedValue(new Error("network error"));

    render(<SurveyPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to load this survey.");
  });

  it("redirects automatically when the survey is already completed", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockResolvedValue(surveyState([likertItem], [], "completed"));
    mockGetNextStep
      .mockResolvedValueOnce(nextIsSurvey("pre_quiz"))
      .mockResolvedValue(nextIsRoute("/quiz/base"));

    render(<SurveyPage />);

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
    fireEvent.click(screen.getByRole("button", { name: "Begin Quiz Part 1" }));

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
    // First call resolves the current step; the call after submitting returns
    // where the participant goes next.
    mockGetNextStep
      .mockReset()
      .mockResolvedValueOnce(nextIsSurvey("pre_quiz"))
      .mockResolvedValue(nextIsRoute("/quiz/base"));

    render(<SurveyPage />);

    await screen.findByText(likertItem.prompt);

    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[2]);

    fireEvent.click(screen.getByRole("button", { name: "Begin Quiz Part 1" }));

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

    fireEvent.click(screen.getByRole("button", { name: "Begin Quiz Part 1" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to save your responses.");
  });

  it("serves a per-variant survey under its own response stage", async () => {
    // The questions come from the post_base bank, but answers are stored under
    // this stage's own response document (survey_responses is unique per stage).
    mockGetMe.mockResolvedValue({
      user: { ...baseUser, completed_steps: FLOW_ORDER.slice(0, 4) },
    });
    mockQuery = { stage: "post_followup" };
    mockGetNextStep.mockResolvedValue(nextIsSurvey("post_followup", "Survey 3"));
    mockGetSurveyState.mockResolvedValue(surveyState([likertItem]));
    mockSubmitSurvey.mockResolvedValue({ ok: true });

    render(<SurveyPage />);

    await screen.findByText(likertItem.prompt);
    // Read under the per-variant stage, not post_base.
    expect(mockGetSurveyState).toHaveBeenCalledWith("post_followup");

    fireEvent.click(screen.getByLabelText?.("3") ?? screen.getAllByRole("radio")[2]);
    fireEvent.click(screen.getByRole("button", { name: /Continue|Finish/ }));

    await waitFor(() =>
      expect(mockSubmitSurvey).toHaveBeenCalledWith("post_followup", expect.any(Array)),
    );
  });

  it("numbers each survey by its position in the participant's flow", async () => {
    mockGetMe.mockResolvedValue({
      user: { ...baseUser, completed_steps: FLOW_ORDER.slice(0, 4) },
    });
    mockQuery = { stage: "post_followup" };
    mockGetNextStep.mockResolvedValue(nextIsSurvey("post_followup", "Survey 3"));
    mockGetSurveyState.mockResolvedValue(surveyState([likertItem]));

    render(<SurveyPage />);

    // post_followup is the 5th step of 9, and the 3rd survey.
    expect(await screen.findByText("Survey 3")).toBeInTheDocument();
    expect(screen.getByText("Step 5 of 9")).toBeInTheDocument();
  });

  it("sends a finished participant to the dashboard", async () => {
    mockGetMe.mockResolvedValue({
      user: { ...baseUser, completed_steps: FLOW_ORDER },
    });
    mockGetNextStep.mockResolvedValue({
      next_step: null,
      next_route: "/dashboard",
      completed_count: FLOW_ORDER.length,
      total_steps: FLOW_ORDER.length,
      finished: true,
    });

    render(<SurveyPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
  });

  it("falls back to the dashboard when the next-step lookup fails", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockGetNextStep.mockRejectedValue(new Error("network"));

    render(<SurveyPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
  });

  it("treats empty-array values as unanswered and other value types as answered", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    const reqA = { ...likertItem, id: "reqA", required: true };
    const reqB = { ...likertItem, id: "reqB", required: true };
    mockGetSurveyState.mockResolvedValue({
      stage: "pre_quiz",
      status: "in_progress",
      items: [reqA, reqB],
      // reqA seeded with an empty array (unanswered branch),
      // reqB seeded with a boolean (the non-string/number/array fall-through).
      answers: [
        { item_id: "reqA", value: [] },
        { item_id: "reqB", value: true },
      ],
    });

    render(<SurveyPage />);

    // Wait for the items to load (submit button appears only then).
    const submit = await screen.findByRole("button", { name: "Begin Quiz Part 1" });
    // reqA is still unanswered → submitting surfaces the validation error.
    fireEvent.click(submit);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Please answer all required questions before continuing.",
    );
  });

  it("routes to whatever /study/next returns after submitting", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockQuery = { stage: "pre_quiz" };
    mockGetSurveyState.mockResolvedValue(surveyState([likertItem]));
    mockSubmitSurvey.mockResolvedValue({ ok: true });
    mockGetNextStep
      .mockResolvedValueOnce(nextIsSurvey("pre_quiz"))
      .mockResolvedValue(nextIsRoute("/quiz/base"));

    render(<SurveyPage />);

    await screen.findByText(likertItem.prompt);
    fireEvent.click(screen.getAllByRole("radio")[2]);
    fireEvent.click(screen.getByRole("button", { name: /Continue|Finish|Begin/ }));

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/quiz/base"));
    expect(mockInvalidateMeCache).toHaveBeenCalled();
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
    await screen.findByText("Survey 1");

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
    await screen.findByText("Survey 1");

    fireEvent.click(screen.getByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
