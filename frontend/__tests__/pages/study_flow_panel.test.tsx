import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import StudyFlowPanel from "../../pages/study_flow_panel";
import { getMe, logout } from "../../lib/auth";
import { getStudyConfig, updateStudyConfig, type StudyConfig } from "../../lib/study";

const mockReplace = jest.fn();
const mockPush = jest.fn();

jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush, query: {} }),
}));

jest.mock("../../lib/auth", () => ({
  getMe: jest.fn(),
  logout: jest.fn(),
}));

jest.mock("../../lib/study", () => ({
  getStudyConfig: jest.fn(),
  updateStudyConfig: jest.fn(),
}));

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockGetStudyConfig = getStudyConfig as jest.Mock;
const mockUpdateStudyConfig = updateStudyConfig as jest.Mock;

const adminUser = { id: "a1", email: "admin@example.com", is_admin: true };

function makeConfig(overrides: Partial<StudyConfig> = {}): StudyConfig {
  return {
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
    ...overrides,
  };
}

function setFor(quizLabel: string) {
  return screen.getByLabelText(`Question set for ${quizLabel}`) as HTMLSelectElement;
}

describe("StudyFlowPanel — question sets", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockGetStudyConfig.mockReset();
    mockUpdateStudyConfig.mockReset();

    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetStudyConfig.mockResolvedValue(makeConfig());
  });

  it("redirects a non-admin away", async () => {
    mockGetMe.mockResolvedValue({ user: { ...adminUser, is_admin: false } });

    render(<StudyFlowPanel />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(mockGetStudyConfig).not.toHaveBeenCalled();
  });

  it("renders one set selector per quiz", async () => {
    render(<StudyFlowPanel />);

    expect(await screen.findByText("Question sets")).toBeInTheDocument();
    expect(setFor("Base Quiz")).toBeInTheDocument();
    expect(setFor("Follow-up Questions Quiz")).toBeInTheDocument();
    expect(setFor("Dual Agent Quiz")).toBeInTheDocument();
    expect(setFor("Cited Links Quiz")).toBeInTheDocument();
  });

  it("shows the stored mapping", async () => {
    mockGetStudyConfig.mockResolvedValue(
      makeConfig({ quiz_set_map: { base: "a", followup: "b" } }),
    );

    render(<StudyFlowPanel />);

    await waitFor(() => expect(setFor("Base Quiz").value).toBe("a"));
    expect(setFor("Follow-up Questions Quiz").value).toBe("b");
    // Unmapped quizzes read as the whole pool.
    expect(setFor("Dual Agent Quiz").value).toBe("");
  });

  it("saves the map the admin builds", async () => {
    mockUpdateStudyConfig.mockResolvedValue(
      makeConfig({ quiz_set_map: { base: "a" }, version: 4 }),
    );

    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");

    fireEvent.change(setFor("Base Quiz"), { target: { value: "a" } });
    fireEvent.click(screen.getByRole("button", { name: "Save flow" }));

    await waitFor(() =>
      expect(mockUpdateStudyConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          quiz_set_mode: "preset",
          quiz_set_map: { base: "a" },
        }),
      ),
    );
  });

  it("clearing a select removes the quiz from the map", async () => {
    mockGetStudyConfig.mockResolvedValue(
      makeConfig({ quiz_set_map: { base: "a", followup: "b" } }),
    );
    mockUpdateStudyConfig.mockResolvedValue(makeConfig());

    render(<StudyFlowPanel />);
    await waitFor(() => expect(setFor("Base Quiz").value).toBe("a"));

    fireEvent.change(setFor("Base Quiz"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save flow" }));

    await waitFor(() =>
      expect(mockUpdateStudyConfig).toHaveBeenCalledWith(
        expect.objectContaining({ quiz_set_map: { followup: "b" } }),
      ),
    );
  });

  it("warns and blocks saving when two quizzes share a set", async () => {
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");

    fireEvent.change(setFor("Base Quiz"), { target: { value: "a" } });
    fireEvent.change(setFor("Dual Agent Quiz"), { target: { value: "a" } });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Set A is\s+used by more than one quiz/,
    );
    expect(screen.getByRole("button", { name: "Save flow" })).toBeDisabled();
    expect(mockUpdateStudyConfig).not.toHaveBeenCalled();
  });

  it("notes which quizzes still draw from the whole pool", async () => {
    mockGetStudyConfig.mockResolvedValue(
      makeConfig({ quiz_set_map: { base: "a", followup: "b", double: "c" } }),
    );

    render(<StudyFlowPanel />);

    expect(
      await screen.findByText(/1 quiz still draw from the whole pool/),
    ).toBeInTheDocument();
  });

  it("hides the per-quiz selects in random mode", async () => {
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");

    fireEvent.click(screen.getByRole("radio", { name: /Random per participant/ }));

    await waitFor(() =>
      expect(
        screen.queryByLabelText("Question set for Base Quiz"),
      ).not.toBeInTheDocument(),
    );
  });

  it("saves the random mode selection", async () => {
    mockUpdateStudyConfig.mockResolvedValue(makeConfig({ quiz_set_mode: "random" }));

    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");

    fireEvent.click(screen.getByRole("radio", { name: /Random per participant/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save flow" }));

    await waitFor(() =>
      expect(mockUpdateStudyConfig).toHaveBeenCalledWith(
        expect.objectContaining({ quiz_set_mode: "random" }),
      ),
    );
  });

  it("shows balanced random selected when returned by the default config", async () => {
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
    const save = screen.getByRole("button", { name: "Save flow" });
    expect(save).not.toBeDisabled();
    fireEvent.click(save);
    await waitFor(() => expect(mockUpdateStudyConfig).toHaveBeenCalledWith(
      expect.objectContaining({ quiz_set_mode: "balanced_random" }),
    ));
    expect(mockUpdateStudyConfig.mock.calls[0][0]).not.toHaveProperty("quiz_set_map");
  });

  it("Save stays disabled until something changes", async () => {
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");

    expect(screen.getByRole("button", { name: "Save flow" })).toBeDisabled();

    fireEvent.change(setFor("Base Quiz"), { target: { value: "d" } });

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save flow" })).not.toBeDisabled(),
    );
  });

  it("surfaces a save failure", async () => {
    mockUpdateStudyConfig.mockRejectedValue(new Error("Unknown set(s): z"));

    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");

    fireEvent.change(setFor("Base Quiz"), { target: { value: "a" } });
    fireEvent.click(screen.getByRole("button", { name: "Save flow" }));

    expect(await screen.findByText("Unknown set(s): z")).toBeInTheDocument();
  });

  it("logs out", async () => {
    render(<StudyFlowPanel />);
    await screen.findByText("Question sets");

    fireEvent.click(screen.getByRole("button", { name: "Logout" }));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
