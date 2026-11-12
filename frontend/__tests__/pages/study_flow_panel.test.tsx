import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import StudyFlowPanel from "../../pages/study_flow_panel";
import { getMe, logout } from "../../lib/auth";
import { getStudyConfig, updateStudyConfig, type StudyConfig } from "../../lib/study";
import { apiFetch } from "../../lib/fetcher";

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockRouter = { replace: mockReplace, push: mockPush, query: {} as Record<string, string> };

jest.mock("next/router", () => ({
  useRouter: () => mockRouter,
}));

jest.mock("../../lib/auth", () => ({
  getMe: jest.fn(),
  logout: jest.fn(),
  invalidateMeCache: jest.fn(),
}));

jest.mock("../../lib/study", () => ({
  getStudyConfig: jest.fn(),
  updateStudyConfig: jest.fn(),
}));

// The New participants section talks to the users API directly.
jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockGetStudyConfig = getStudyConfig as jest.Mock;
const mockUpdateStudyConfig = updateStudyConfig as jest.Mock;
const mockApiFetch = apiFetch as jest.Mock;

const adminUser = { id: "a1", email: "admin@example.com", is_admin: true };
const plenty = { a: 20, b: 20, c: 20, d: 20, unassigned: 0, total: 80 };

function makeConfig(overrides: Partial<StudyConfig> = {}): StudyConfig {
  return {
    study_id: "study-1",
    mode: "all_variants",
    variant_order: ["followup", "double", "links"],
    counterbalance: true,
    version: 3,
    known_variants: ["followup", "double", "links"],
    variant_labels: {
      followup: "Follow-up Questions",
      double: "Dual Agent",
      links: "Cited Links",
    },
    preview: [["followup", "double", "links"]],
    quiz_set_mode: "preset",
    quiz_set_map: {},
    known_sets: ["a", "b", "c", "d"],
    known_quiz_ids: ["base", "followup", "double", "links"],
    quiz_labels: {
      base: "Base Quiz",
      followup: "Follow-up Questions Quiz",
      double: "Dual Agent Quiz",
      links: "Cited Links Quiz",
    },
    questions_per_quiz: 5,
    question_counts: plenty,
    default_question_sets: null,
    supply_problems: [],
    enrolled_with_unstarted_quizzes: 0,
    ...overrides,
  };
}

function setFor(quizLabel: string) {
  return screen.getByLabelText(`Question set for ${quizLabel}`) as HTMLSelectElement;
}
const saveButton = (study = "Study 1") => screen.getByRole("button", { name: `Save ${study} settings` });
const allOnC = () => ["Base Quiz", "Follow-up Questions Quiz", "Dual Agent Quiz", "Cited Links Quiz"]
  .forEach((quiz) => fireEvent.change(setFor(quiz), { target: { value: "c" } }));

beforeEach(() => {
  mockReplace.mockClear();
  mockPush.mockClear();
  mockGetMe.mockReset();
  mockLogout.mockReset();
  mockGetStudyConfig.mockReset();
  mockUpdateStudyConfig.mockReset();
  mockApiFetch.mockReset();
  mockRouter.query = {};
  sessionStorage.clear();
  window.history.replaceState({}, "", "/study_flow_panel");

  mockGetMe.mockResolvedValue({ user: adminUser });
  mockGetStudyConfig.mockImplementation((study: string) => Promise.resolve(makeConfig({ study_id: study })));
  mockApiFetch.mockImplementation((url: string) => Promise.resolve(
    url.endsWith("quiz-default-sets") ? { sets: null } : { next: "followup", source: "rotation" }));
});

describe("StudyFlowPanel — which study is being edited", () => {
  it("redirects a non-admin away", async () => {
    mockGetMe.mockResolvedValue({ user: { ...adminUser, is_admin: false } });
    render(<StudyFlowPanel />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(mockGetStudyConfig).not.toHaveBeenCalled();
  });

  it("names the study in the title, the tabs and the Save button", async () => {
    render(<StudyFlowPanel />);
    expect(await screen.findByRole("heading", { name: "Study Flow · Study 1" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Study 1" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Study 2" })).toHaveAttribute("aria-selected", "false");
    expect(saveButton()).toBeInTheDocument();
    expect(mockGetStudyConfig).toHaveBeenCalledWith("study-1");
  });

  it("opens the study named in the URL or the admin workspace", async () => {
    sessionStorage.setItem("mep.selectedStudy", "study-2");
    render(<StudyFlowPanel />);
    expect(await screen.findByRole("heading", { name: "Study Flow · Study 2" })).toBeInTheDocument();
    expect(mockGetStudyConfig).toHaveBeenCalledWith("study-2");
  });

  it("switching tabs loads and saves the other study's settings", async () => {
    mockUpdateStudyConfig.mockImplementation((_patch, study) => Promise.resolve(makeConfig({ study_id: study })));
    render(<StudyFlowPanel />);
    await screen.findByRole("heading", { name: "Study Flow · Study 1" });
    fireEvent.click(screen.getByRole("tab", { name: "Study 2" }));
    expect(await screen.findByRole("heading", { name: "Study Flow · Study 2" })).toBeInTheDocument();
    await waitFor(() => expect(mockGetStudyConfig).toHaveBeenLastCalledWith("study-2"));
    fireEvent.change(await screen.findByLabelText("Question set for Base Quiz"), { target: { value: "a" } });
    fireEvent.click(saveButton("Study 2"));
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalledWith(expect.anything(), "study-2"));
  });

  it("asks before discarding unsaved changes when switching study", async () => {
    const confirm = jest.spyOn(window, "confirm").mockReturnValue(false);
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    fireEvent.change(setFor("Base Quiz"), { target: { value: "a" } });
    fireEvent.click(screen.getByRole("tab", { name: "Study 2" }));
    expect(confirm).toHaveBeenCalledWith("Discard your unsaved changes to Study 1?");
    expect(screen.getByRole("tab", { name: "Study 1" })).toHaveAttribute("aria-selected", "true");
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("tab", { name: "Study 2" }));
    expect(await screen.findByRole("heading", { name: "Study Flow · Study 2" })).toBeInTheDocument();
    confirm.mockRestore();
  });

  it("shows the study's fixed quiz structure instead of a mode switch", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ mode: "single_variant" }));
    render(<StudyFlowPanel />);
    expect(await screen.findByText(/Quiz structure: the base quiz plus one assigned variant/)).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Every variant/ })).not.toBeInTheDocument();
  });

  it("labels each study's own default question-set mode", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ default_quiz_set_mode: "preset" }));
    render(<StudyFlowPanel />);
    expect(await screen.findByText("Preset (default for Study 1)")).toBeInTheDocument();
    expect(screen.getByText("Balanced random")).toBeInTheDocument();
    expect(screen.getByText("Random per participant")).toBeInTheDocument();
  });

  it("surfaces a settings load failure", async () => {
    mockGetStudyConfig.mockRejectedValue(new Error("Admin only"));
    render(<StudyFlowPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Admin only");
  });
});

describe("StudyFlowPanel — surveys and saving", () => {
  it("saves one final variant survey and exposes its independent switch", async () => {
    mockUpdateStudyConfig.mockResolvedValue(makeConfig({ variant_survey_mode: "end_only" }));
    render(<StudyFlowPanel />);
    await screen.findByRole("button", { name: "Disable all" });
    fireEvent.change(screen.getByLabelText("Variant survey schedule"), { target: { value: "end_only" } });
    expect(screen.queryByLabelText("Enable post_double")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Enable post_variant"));
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalledWith(expect.objectContaining({
      variant_survey_mode: "end_only", survey_stages: expect.objectContaining({ post_variant: expect.objectContaining({ enabled: false }) }),
    }), "study-1"));
  });

  it("saves all survey switches and admin names for future enrollments", async () => {
    render(<StudyFlowPanel />);
    mockUpdateStudyConfig.mockResolvedValue(makeConfig());
    fireEvent.click(await screen.findByRole("button", { name: "Disable all" }));
    fireEvent.change(screen.getByLabelText("Admin name for post_double"), { target: { value: "Verification after dual agents" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalled());
    const stages = mockUpdateStudyConfig.mock.calls[0][0].survey_stages;
    expect(Object.values(stages).every((s: any) => s.enabled === false)).toBe(true);
    expect(stages.post_double.name).toBe("Verification after dual agents");
  });

  it("Save stays disabled until something changes", async () => {
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    expect(saveButton()).toBeDisabled();
    fireEvent.change(setFor("Base Quiz"), { target: { value: "d" } });
    await waitFor(() => expect(saveButton()).not.toBeDisabled());
  });

  it("surfaces a save failure", async () => {
    mockUpdateStudyConfig.mockRejectedValue(new Error("Unknown set(s): z"));
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    fireEvent.change(setFor("Base Quiz"), { target: { value: "a" } });
    fireEvent.click(saveButton());
    expect(await screen.findByText("Unknown set(s): z")).toBeInTheDocument();
  });

  it("does not send the fixed quiz structure", async () => {
    mockUpdateStudyConfig.mockResolvedValue(makeConfig());
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    fireEvent.change(setFor("Base Quiz"), { target: { value: "a" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalled());
    expect(mockUpdateStudyConfig.mock.calls[0][0]).not.toHaveProperty("mode");
  });

  it("logs out", async () => {
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    fireEvent.click(screen.getByRole("button", { name: "Logout" }));
    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});

describe("StudyFlowPanel — question sets", () => {
  it("renders one set selector per quiz, with each set's question count", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ question_counts: { ...plenty, c: 19 } }));
    render(<StudyFlowPanel />);
    expect(await screen.findByText("Question sets")).toBeInTheDocument();
    for (const quiz of ["Base Quiz", "Follow-up Questions Quiz", "Dual Agent Quiz", "Cited Links Quiz"]) {
      expect(setFor(quiz)).toBeInTheDocument();
    }
    expect(within(setFor("Base Quiz")).getByRole("option", { name: "Set C (19 questions)" })).toBeInTheDocument();
    expect(screen.getByText("Set C 19")).toBeInTheDocument();
  });

  it("shows the stored mapping", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ quiz_set_map: { base: "a", followup: "b" } }));
    render(<StudyFlowPanel />);
    await waitFor(() => expect(setFor("Base Quiz").value).toBe("a"));
    expect(setFor("Follow-up Questions Quiz").value).toBe("b");
    expect(setFor("Dual Agent Quiz").value).toBe("");
  });

  it("saves the map the admin builds", async () => {
    mockUpdateStudyConfig.mockResolvedValue(makeConfig({ quiz_set_map: { base: "a" }, version: 4 }));
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    fireEvent.change(setFor("Base Quiz"), { target: { value: "a" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalledWith(
      expect.objectContaining({ quiz_set_mode: "preset", quiz_set_map: { base: "a" } }), "study-1"));
  });

  it("clearing a select removes the quiz from the map", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ quiz_set_map: { base: "a", followup: "b" } }));
    mockUpdateStudyConfig.mockResolvedValue(makeConfig());
    render(<StudyFlowPanel />);
    await waitFor(() => expect(setFor("Base Quiz").value).toBe("a"));
    fireEvent.change(setFor("Base Quiz"), { target: { value: "" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalledWith(
      expect.objectContaining({ quiz_set_map: { followup: "b" } }), "study-1"));
  });

  it("allows every quiz to share set C when it holds enough questions", async () => {
    mockUpdateStudyConfig.mockResolvedValue(makeConfig());
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    allOnC();
    expect(screen.getByText(/Enough questions: every participant gets 20 different questions\. Set C is shared by more than one quiz, without repeats\./)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalledWith(expect.objectContaining({
      quiz_set_map: { base: "c", followup: "c", double: "c", links: "c" } }), "study-1"));
  });

  it("blocks saving a shared set that would run short, with the count", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ question_counts: { ...plenty, c: 19 } }));
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    allOnC();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Not enough questions for these settings");
    expect(alert).toHaveTextContent("Set C has 19 questions, but 4 quizzes × 5 questions need 20 different ones.");
    expect(saveButton()).toBeDisabled();
  });

  it("re-checks live when the quiz size changes", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ quiz_set_map: { base: "c", followup: "c", double: "c", links: "c" } }));
    render(<StudyFlowPanel />);
    await screen.findByText(/Enough questions/);
    fireEvent.change(screen.getByLabelText("Questions per quiz"), { target: { value: "6" } });
    expect(await screen.findByRole("alert")).toHaveTextContent("4 quizzes × 6 questions need 24 different ones.");
    expect(saveButton()).toBeDisabled();
  });

  it("warns about saved settings the bank no longer fits without blocking other edits", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ quiz_set_map: { base: "c", followup: "c", double: "c", links: "c" },
      question_counts: { ...plenty, c: 19 } }));
    mockUpdateStudyConfig.mockResolvedValue(makeConfig());
    render(<StudyFlowPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The saved settings no longer fit the question bank");
    fireEvent.click(screen.getByRole("button", { name: "Disable all" }));
    expect(saveButton()).not.toBeDisabled();
  });

  it("notes which quizzes draw from the whole bank", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ quiz_set_map: { base: "a", followup: "b", double: "c" } }));
    render(<StudyFlowPanel />);
    expect(await screen.findByText(/Cited Links Quiz draws from the whole bank\./)).toBeInTheDocument();
  });

  it("random modes need a full quiz in every set", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ question_counts: { ...plenty, d: 3 } }));
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    fireEvent.click(screen.getByRole("radio", { name: /Random per participant/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Set D has 3 questions; every set needs at least 5");
    expect(screen.queryByLabelText("Question set for Base Quiz")).not.toBeInTheDocument();
  });

  it("saves the random mode selection", async () => {
    mockUpdateStudyConfig.mockResolvedValue(makeConfig({ quiz_set_mode: "random" }));
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    fireEvent.click(screen.getByRole("radio", { name: /Random per participant/ }));
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalledWith(
      expect.objectContaining({ quiz_set_mode: "random" }), "study-1"));
  });

  it("shows balanced random selected when returned by the config", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ quiz_set_mode: "balanced_random" }));
    render(<StudyFlowPanel />);
    expect(await screen.findByRole("radio", { name: /Balanced random/ })).toBeChecked();
    expect(screen.queryByLabelText("Question set for Base Quiz")).not.toBeInTheDocument();
    expect(screen.getByText(/Balance applies to assigned participants/)).toBeInTheDocument();
  });

  it("saves balanced random without submitting an unused preset map", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ quiz_set_map: { base: "a", double: "a" } }));
    mockUpdateStudyConfig.mockResolvedValue(makeConfig({ quiz_set_mode: "balanced_random" }));
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    fireEvent.click(screen.getByRole("radio", { name: /Balanced random/ }));
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalledWith(
      expect.objectContaining({ quiz_set_mode: "balanced_random" }), "study-1"));
    expect(mockUpdateStudyConfig.mock.calls[0][0]).not.toHaveProperty("quiz_set_map");
  });

  it("checks quizzes without a set against Study 1's default question sets", async () => {
    mockApiFetch.mockImplementation((url: string) => Promise.resolve(
      url.endsWith("quiz-default-sets") ? { sets: ["a"] } : { next: "followup", source: "rotation" }));
    mockGetStudyConfig.mockResolvedValue(makeConfig({ question_counts: { ...plenty, a: 19 } }));
    render(<StudyFlowPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Default question sets A has 19 questions");
  });
});

describe("StudyFlowPanel — enrolled participants", () => {
  it("offers to apply the sets to enrolled participants, unticked by default", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ enrolled_with_unstarted_quizzes: 37 }));
    render(<StudyFlowPanel />);
    const box = await screen.findByRole("checkbox", { name: /Also apply the question sets to 37 enrolled participants' unstarted quizzes/ });
    expect(box).not.toBeChecked();
    expect(box).toBeEnabled();
  });

  it("disables the box when nobody has an unstarted quiz", async () => {
    render(<StudyFlowPanel />);
    expect(await screen.findByRole("checkbox", { name: /Also apply the question sets to 0 enrolled participants/ })).toBeDisabled();
  });

  it("applies on save and reports how many participants changed", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ enrolled_with_unstarted_quizzes: 2 }));
    mockUpdateStudyConfig.mockResolvedValue(makeConfig({ quiz_set_map: { base: "c", followup: "c", double: "c", links: "c" }, applied_participants: 2 }));
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    allOnC();
    fireEvent.click(screen.getByRole("checkbox", { name: /Also apply/ }));
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalledWith(expect.objectContaining({ apply_to_enrolled: true }), "study-1"));
    expect(await screen.findByText(/Question sets updated for 2 participants\./)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Also apply/ })).not.toBeChecked();
  });

  it("applying is not sent unless ticked", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ enrolled_with_unstarted_quizzes: 2 }));
    mockUpdateStudyConfig.mockResolvedValue(makeConfig());
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    fireEvent.change(setFor("Base Quiz"), { target: { value: "a" } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalled());
    expect(mockUpdateStudyConfig.mock.calls[0][0]).not.toHaveProperty("apply_to_enrolled");
  });

  it("ticking the box alone allows saving the current settings to enrolled participants", async () => {
    mockGetStudyConfig.mockResolvedValue(makeConfig({ enrolled_with_unstarted_quizzes: 1 }));
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");
    expect(saveButton()).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /Also apply/ }));
    expect(saveButton()).toBeEnabled();
  });
});

describe("StudyFlowPanel — new participants", () => {
  it("shows and pins the next sign-up for the study being edited", async () => {
    mockApiFetch.mockImplementation((url: string, init?: { method?: string; body?: string }) => {
      if (url.endsWith("next-assignment") && init?.method === "PUT") {
        return Promise.resolve({ next: JSON.parse(init.body!).variant, source: "override" });
      }
      return Promise.resolve(url.endsWith("quiz-default-sets") ? { sets: null } : { next: "followup", source: "rotation" });
    });
    sessionStorage.setItem("mep.selectedStudy", "study-2");
    render(<StudyFlowPanel />);
    const group = within(await screen.findByRole("group", { name: "Next sign-up" }));
    expect(await group.findByText("(rotation)")).toBeInTheDocument();
    fireEvent.click(group.getByRole("button", { name: "Set Links" }));
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/studies/study-2/users/next-assignment",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ variant: "links" }) })));
    expect(await group.findByText("(override)")).toBeInTheDocument();
  });

  it("offers default question sets for Study 1 only", async () => {
    render(<StudyFlowPanel />);
    expect(await screen.findByRole("group", { name: "Default question sets" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Study 2" }));
    await screen.findByRole("heading", { name: "Study Flow · Study 2" });
    await screen.findByText("Question sets");
    expect(screen.queryByRole("group", { name: "Default question sets" })).not.toBeInTheDocument();
  });

  it("saves default question sets straight away and re-checks the supply", async () => {
    mockApiFetch.mockImplementation((url: string, init?: { method?: string; body?: string }) => {
      if (url.endsWith("quiz-default-sets")) {
        return Promise.resolve(init?.method === "PUT" ? { sets: JSON.parse(init.body!).sets } : { sets: null });
      }
      return Promise.resolve({ next: "followup", source: "rotation" });
    });
    mockGetStudyConfig.mockResolvedValue(makeConfig({ question_counts: { ...plenty, b: 4 } }));
    render(<StudyFlowPanel />);
    const group = within(await screen.findByRole("group", { name: "Default question sets" }));
    fireEvent.click(group.getByRole("button", { name: "B" }));
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/studies/study-1/users/quiz-default-sets",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ sets: ["b"] }) })));
    expect(await screen.findByRole("alert")).toHaveTextContent("Default question sets B has 4 questions");
  });
});
