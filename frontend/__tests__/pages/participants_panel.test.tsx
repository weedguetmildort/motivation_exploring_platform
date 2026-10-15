import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import ParticipantsPanelPage from "../../pages/participants_panel";
import { getMe, logout } from "../../lib/auth";
import { apiFetch } from "../../lib/fetcher";

const mockReplace = jest.fn();
const mockPush    = jest.fn();
jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
}));

jest.mock("../../lib/auth", () => ({
  getMe:  jest.fn(),
  logout: jest.fn(),
}));

jest.mock("../../lib/fetcher", () => ({
  apiFetch: jest.fn(),
}));

const mockGetMe   = getMe   as jest.Mock;
const mockLogout  = logout  as jest.Mock;
const mockApiFetch = apiFetch as jest.Mock;

const adminUser = { id: "1", email: "admin@example.com", is_admin: true };

// Scope a query to a single participant's card. Variant labels (Follow-up etc.)
// also appear in the "Cases by condition" summary, so bare getByText would be
// ambiguous — scope to the card that contains the participant's name.
function participantCard(name: string) {
  const card = screen.getByText(name).closest("div.rounded-lg") as HTMLElement;
  return within(card);
}

const now = new Date().toISOString();
const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();
const tenDaysAgo   = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString();

const activeParticipant = {
  id: "p1",
  email: "active@test.edu",
  first_name: "Alice",
  last_name: "Smith",
  assigned_var: "links",
  survey_stage: "post_base",
  demographics_completed: true,
  survey_pre_base_completed: true,
  quiz_base_completed: false,
  survey_post_base_completed: false,
  quiz_variant_completed: false,
  survey_post_variant_completed: false,
  last_active_at: threeDaysAgo,
  consent_declined_at: null,
  quiz_sets: null,
  followup_study_granted: false,
  created_at: "2025-01-01T00:00:00.000Z",
};

const completeParticipant = {
  id: "p2",
  email: "done@test.edu",
  first_name: "Bob",
  last_name: "Jones",
  assigned_var: "followup",
  survey_stage: "complete",
  demographics_completed: true,
  survey_pre_base_completed: true,
  quiz_base_completed: true,
  survey_post_base_completed: true,
  quiz_variant_completed: true,
  survey_post_variant_completed: true,
  last_active_at: threeDaysAgo,
  consent_declined_at: null,
  quiz_sets: null,
  followup_study_granted: false,
  created_at: "2025-01-02T00:00:00.000Z",
};

const declinedParticipant = {
  id: "p3",
  email: "declined@test.edu",
  first_name: "Carol",
  last_name: "White",
  assigned_var: "double",
  survey_stage: "pre_quiz",
  demographics_completed: false,
  survey_pre_base_completed: false,
  quiz_base_completed: false,
  survey_post_base_completed: false,
  quiz_variant_completed: false,
  survey_post_variant_completed: false,
  last_active_at: null,
  consent_declined_at: "2025-01-03T00:00:00.000Z",
  quiz_sets: null,
  followup_study_granted: false,
  created_at: "2025-01-03T00:00:00.000Z",
};

const inactiveParticipant = {
  ...activeParticipant,
  id: "p4",
  email: "stale@test.edu",
  first_name: "Dave",
  last_name: "Stale",
  last_active_at: tenDaysAgo,
  survey_stage: "post_base",
};

describe("ParticipantsPanelPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockApiFetch.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<ParticipantsPanelPage />);
    expect(screen.getByText("Loading participants panel…")).toBeInTheDocument();
  });

  it("redirects to /login when not authenticated", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<ParticipantsPanelPage />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("redirects non-admin users to /dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "2", email: "user@test.edu", is_admin: false } });
    render(<ParticipantsPanelPage />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
  });

  it("renders the panel and loads participants for an admin", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([activeParticipant]);
    render(<ParticipantsPanelPage />);

    expect(await screen.findByText("Participants Panel")).toBeInTheDocument();
    expect(await screen.findByText("Alice Smith")).toBeInTheDocument();
    expect(screen.getByText("active@test.edu")).toBeInTheDocument();
    expect(participantCard("Alice Smith").getByText("Links")).toBeInTheDocument();
  });

  it("shows a loading indicator while fetching participants", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockReturnValue(new Promise(() => {}));
    render(<ParticipantsPanelPage />);

    await screen.findByText("Participants Panel");
    expect(await screen.findByText("Loading…")).toBeInTheDocument();
  });

  it("shows an error message when loading participants fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockRejectedValue(new Error("network error"));
    render(<ParticipantsPanelPage />);

    expect(await screen.findByText("Failed to load participants.")).toBeInTheDocument();
  });

  it("shows an empty message when no participants exist", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<ParticipantsPanelPage />);

    await screen.findByText("Participants Panel");
    expect(await screen.findByText("No participants in this tab.")).toBeInTheDocument();
  });

  it("shows variant badges for followup, double, and links variants", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([activeParticipant, completeParticipant, declinedParticipant]);
    render(<ParticipantsPanelPage />);

    await screen.findByText("Alice Smith");
    expect(participantCard("Alice Smith").getByText("Links")).toBeInTheDocument();
    expect(participantCard("Bob Jones").getByText("Follow-up")).toBeInTheDocument();
    expect(participantCard("Carol White").getByText("Dual-Agent")).toBeInTheDocument();
  });

  it("shows Complete and Declined badges on the appropriate cards", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([completeParticipant, declinedParticipant]);
    render(<ParticipantsPanelPage />);

    await screen.findByText("Bob Jones");
    expect(screen.getByText("Complete")).toBeInTheDocument();
    expect(screen.getByText("Declined")).toBeInTheDocument();
  });

  it("shows stage progress checkmarks for completed steps", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([activeParticipant]);
    render(<ParticipantsPanelPage />);

    await screen.findByText("Alice Smith");
    expect(screen.getByText(/✓.*Demo/)).toBeInTheDocument();
    expect(screen.getByText(/✓.*Pre-Survey/)).toBeInTheDocument();
    expect(screen.getByText("Quiz Base")).toBeInTheDocument();
  });

  it("shows joined date when created_at is set", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([activeParticipant]);
    render(<ParticipantsPanelPage />);

    await screen.findByText("Alice Smith");
    expect(screen.getByText(/Joined/)).toBeInTheDocument();
  });

  it("shows 'Never' for a participant with no last_active_at", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([declinedParticipant]);
    render(<ParticipantsPanelPage />);

    await screen.findByText("Carol White");
    expect(screen.getByText("Never")).toBeInTheDocument();
  });

  describe("tab filtering", () => {
    const allParticipants = [activeParticipant, completeParticipant, declinedParticipant, inactiveParticipant];

    beforeEach(() => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch.mockResolvedValue(allParticipants);
    });

    it("shows all participants on the All tab", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Alice Smith");
      expect(screen.getByText("Bob Jones")).toBeInTheDocument();
      expect(screen.getByText("Carol White")).toBeInTheDocument();
    });

    it("filters to recently active, non-complete participants on Active tab", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Alice Smith");

      fireEvent.click(screen.getByRole("button", { name: /Active/ }));

      expect(screen.getByText("Alice Smith")).toBeInTheDocument();
      expect(screen.queryByText("Bob Jones")).not.toBeInTheDocument();
      expect(screen.queryByText("Carol White")).not.toBeInTheDocument();
      expect(screen.queryByText("stale@test.edu")).not.toBeInTheDocument();
    });

    it("filters to complete participants on the Complete tab", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Alice Smith");

      fireEvent.click(screen.getByRole("button", { name: /Complete/ }));

      expect(screen.queryByText("Alice Smith")).not.toBeInTheDocument();
      expect(screen.getByText("Bob Jones")).toBeInTheDocument();
    });

    it("filters to declined participants on the Declined tab", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Alice Smith");

      fireEvent.click(screen.getByRole("button", { name: /Declined/ }));

      expect(screen.queryByText("Alice Smith")).not.toBeInTheDocument();
      expect(screen.getByText("Carol White")).toBeInTheDocument();
    });

    it("shows an empty message when the filtered tab has no results", async () => {
      mockApiFetch.mockResolvedValue([activeParticipant]);
      render(<ParticipantsPanelPage />);
      await screen.findByText("Alice Smith");

      fireEvent.click(screen.getByRole("button", { name: /Declined/ }));

      expect(await screen.findByText("No participants in this tab.")).toBeInTheDocument();
    });
  });

  it("navigates to the dashboard when the Dashboard button is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<ParticipantsPanelPage />);

    fireEvent.click(await screen.findByText("Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("logs out and redirects to /login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockLogout.mockResolvedValue(undefined);
    mockApiFetch.mockResolvedValue([]);
    render(<ParticipantsPanelPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  describe("cases by condition", () => {
    // Roster with distinct per-condition tallies:
    //   followup: 2 enrolled, 1 complete
    //   double:   1 enrolled (+1 declined, excluded), 0 complete
    //   links:    1 enrolled, 0 complete
    const followupComplete = { ...completeParticipant, id: "f1", assigned_var: "followup", survey_stage: "complete" };
    const followupActive   = { ...activeParticipant,   id: "f2", assigned_var: "followup", survey_stage: "post_base" };
    const doubleActive     = { ...activeParticipant,   id: "d1", assigned_var: "double" };
    const doubleDeclined   = { ...declinedParticipant, id: "d2", assigned_var: "double" };
    const linksActive      = { ...activeParticipant,   id: "l1", assigned_var: "links" };

    function conditionRow(label: string) {
      const card = screen.getByRole("group", { name: "Cases by condition" });
      const row = within(card).getByText(label).closest("div") as HTMLElement;
      return within(row);
    }

    beforeEach(() => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch.mockResolvedValue([
        followupComplete, followupActive, doubleActive, doubleDeclined, linksActive,
      ]);
    });

    it("shows enrolled and complete counts per study condition", async () => {
      render(<ParticipantsPanelPage />);
      // Wait for the roster to load before reading counts — the card renders
      // immediately with zeros and only fills in once /api/users resolves.
      await screen.findByText("Bob Jones");

      expect(conditionRow("Follow-up").getByText("2 enrolled")).toBeInTheDocument();
      expect(conditionRow("Follow-up").getByText("1 complete")).toBeInTheDocument();

      expect(conditionRow("Links").getByText("1 enrolled")).toBeInTheDocument();
      expect(conditionRow("Links").getByText("0 complete")).toBeInTheDocument();
    });

    it("excludes a participant who declined consent from the enrolled count", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Bob Jones");

      // Dual-Agent has one active + one declined → 1 enrolled, not 2.
      expect(conditionRow("Dual-Agent").getByText("1 enrolled")).toBeInTheDocument();
      expect(conditionRow("Dual-Agent").getByText("0 complete")).toBeInTheDocument();
    });

    it("shows every condition even when the tab filter hides participant cards", async () => {
      render(<ParticipantsPanelPage />);
      // Load the roster first (on the default "all" tab) before filtering.
      await screen.findByText("Bob Jones");

      // Switch to the Declined tab (only the declined double participant shows).
      fireEvent.click(screen.getByRole("button", { name: /Declined/ }));

      // Case counts are computed from the full roster, not the filtered view.
      expect(conditionRow("Follow-up").getByText("2 enrolled")).toBeInTheDocument();
      expect(conditionRow("Links").getByText("1 enrolled")).toBeInTheDocument();
    });
  });

  describe("next sign-up assignment", () => {
    // Route apiFetch by URL: the roster for /api/users, the indicator for
    // /api/users/next-assignment (PUT echoes back the resulting state).
    function mockUsersApi(
      participants: unknown[],
      initialNext: { next: string; source: string },
    ) {
      mockApiFetch.mockImplementation((url: string, init?: any) => {
        if (url.includes("next-assignment")) {
          if (init?.method === "PUT") {
            const body = JSON.parse(init.body);
            return Promise.resolve(
              body.variant
                ? { next: body.variant, source: "override" }
                : { next: "followup", source: "rotation" },
            );
          }
          return Promise.resolve(initialNext);
        }
        return Promise.resolve(participants);
      });
    }

    function nextGroup() {
      return within(screen.getByRole("group", { name: "Next sign-up" }));
    }

    it("shows the current next-assignment indicator", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockUsersApi([activeParticipant], { next: "followup", source: "rotation" });
      render(<ParticipantsPanelPage />);

      await screen.findByText("Participants Panel");
      expect(await nextGroup().findByText("(rotation)")).toBeInTheDocument();
      expect(nextGroup().getByText("Follow-up")).toBeInTheDocument();
    });

    it("pins the next case when a condition button is clicked", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockUsersApi([activeParticipant], { next: "followup", source: "rotation" });
      render(<ParticipantsPanelPage />);

      await screen.findByText("Participants Panel");
      await nextGroup().findByText("(rotation)");

      fireEvent.click(nextGroup().getByRole("button", { name: "Set Links" }));

      await waitFor(() =>
        expect(mockApiFetch).toHaveBeenCalledWith(
          "/api/users/next-assignment",
          expect.objectContaining({
            method: "PUT",
            body: JSON.stringify({ variant: "links" }),
          }),
        ),
      );
      // The indicator reflects the pinned override returned by the PUT.
      expect(await nextGroup().findByText("(override)")).toBeInTheDocument();
      expect(nextGroup().getByText("Links")).toBeInTheDocument();
    });

    it("clears the override with Reset to rotation", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockUsersApi([activeParticipant], { next: "double", source: "override" });
      render(<ParticipantsPanelPage />);

      await screen.findByText("Participants Panel");
      await nextGroup().findByText("(override)");

      fireEvent.click(nextGroup().getByRole("button", { name: "Reset to rotation" }));

      await waitFor(() =>
        expect(mockApiFetch).toHaveBeenCalledWith(
          "/api/users/next-assignment",
          expect.objectContaining({
            method: "PUT",
            body: JSON.stringify({ variant: null }),
          }),
        ),
      );
      expect(await nextGroup().findByText("(rotation)")).toBeInTheDocument();
    });
  });

  describe("quiz set restriction", () => {
    // Route apiFetch by URL across the roster, next-assignment, the global
    // default-sets config, and per-participant PATCH.
    function mockSetsApi(participants: any[], defaultSets: string[] | null) {
      mockApiFetch.mockImplementation((url: string, init?: any) => {
        if (url.includes("quiz-default-sets")) {
          if (init?.method === "PUT") {
            return Promise.resolve({ sets: JSON.parse(init.body).sets });
          }
          return Promise.resolve({ sets: defaultSets });
        }
        if (url.includes("/quiz-sets")) {
          // PATCH /api/users/{id}/quiz-sets
          const id = url.split("/")[3];
          const p = participants.find((x) => x.id === id);
          return Promise.resolve({ ...p, quiz_sets: JSON.parse(init.body).quiz_sets });
        }
        if (url.includes("next-assignment")) {
          return Promise.resolve({ next: "followup", source: "rotation" });
        }
        return Promise.resolve(participants);
      });
    }

    it("reflects the configured default question sets", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockSetsApi([activeParticipant], ["a"]);
      render(<ParticipantsPanelPage />);
      await screen.findByText("Participants Panel");

      const group = within(screen.getByRole("group", { name: "Default question sets" }));
      await waitFor(() =>
        expect(group.getByRole("button", { name: "A" })).toHaveAttribute("aria-pressed", "true"),
      );
      expect(group.getByRole("button", { name: "B" })).toHaveAttribute("aria-pressed", "false");
    });

    it("PUTs the new default sets when a chip is toggled", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockSetsApi([activeParticipant], []);
      render(<ParticipantsPanelPage />);
      await screen.findByText("Participants Panel");

      const group = within(screen.getByRole("group", { name: "Default question sets" }));
      fireEvent.click(group.getByRole("button", { name: "B" }));

      await waitFor(() =>
        expect(mockApiFetch).toHaveBeenCalledWith(
          "/api/users/quiz-default-sets",
          expect.objectContaining({ method: "PUT", body: JSON.stringify({ sets: ["b"] }) }),
        ),
      );
    });

    it("PATCHes a participant's question sets when edited", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      const p = { ...activeParticipant, quiz_sets: ["a"] };
      mockSetsApi([p], []);
      render(<ParticipantsPanelPage />);
      await screen.findByText("Alice Smith");

      const group = within(
        screen.getByRole("group", { name: `Question sets for ${p.email}` }),
      );
      // Starts at A; toggling B should send both.
      fireEvent.click(group.getByRole("button", { name: "B" }));

      await waitFor(() =>
        expect(mockApiFetch).toHaveBeenCalledWith(
          `/api/users/${p.id}/quiz-sets`,
          expect.objectContaining({
            method: "PATCH",
            body: JSON.stringify({ quiz_sets: ["a", "b"] }),
          }),
        ),
      );
    });
  });

  describe("follow-up study grant", () => {
    function mockFollowupApi(participants: any[]) {
      mockApiFetch.mockImplementation((url: string, init?: any) => {
        if (url.includes("/followup-study")) {
          const id = url.split("/")[3]; // PATCH /api/users/{id}/followup-study
          const p = participants.find((x) => x.id === id);
          return Promise.resolve({ ...p, followup_study_granted: JSON.parse(init.body).granted });
        }
        if (url.includes("next-assignment")) return Promise.resolve({ next: "followup", source: "rotation" });
        if (url.includes("quiz-default-sets")) return Promise.resolve({ sets: null });
        return Promise.resolve(participants);
      });
    }

    it("grants access via the per-participant toggle", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockFollowupApi([activeParticipant]); // starts ungranted
      render(<ParticipantsPanelPage />);
      await screen.findByText("Alice Smith");

      const label = `Toggle follow-up study access for ${activeParticipant.email}`;
      expect(screen.getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "false");

      fireEvent.click(screen.getByRole("button", { name: label }));

      await waitFor(() =>
        expect(mockApiFetch).toHaveBeenCalledWith(
          `/api/users/${activeParticipant.id}/followup-study`,
          expect.objectContaining({ method: "PATCH", body: JSON.stringify({ granted: true }) }),
        ),
      );
      await waitFor(() =>
        expect(screen.getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "true"),
      );
    });

    it("revokes access when toggling an already-granted participant", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      const granted = { ...activeParticipant, followup_study_granted: true };
      mockFollowupApi([granted]);
      render(<ParticipantsPanelPage />);
      await screen.findByText("Alice Smith");

      const label = `Toggle follow-up study access for ${granted.email}`;
      expect(screen.getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "true");

      fireEvent.click(screen.getByRole("button", { name: label }));

      await waitFor(() =>
        expect(mockApiFetch).toHaveBeenCalledWith(
          `/api/users/${granted.id}/followup-study`,
          expect.objectContaining({ method: "PATCH", body: JSON.stringify({ granted: false }) }),
        ),
      );
    });
  });

  describe("cases by question set", () => {
    // Sets overlap, so these fixtures deliberately double-count:
    //   A: setA + setAB enrolled (setAB complete)      -> 2 enrolled, 1 complete
    //   B: setAB only                                  -> 1 enrolled, 1 complete
    //   C: setCDeclined only, and it declined consent  -> 0 enrolled, 0 complete
    //   D: nobody                                      -> 0 enrolled, 0 complete
    //   No restriction: setNull + setEmpty             -> 2 enrolled, 0 complete
    const setA         = { ...activeParticipant,   id: "s1", quiz_sets: ["a"] };
    const setAB        = { ...completeParticipant, id: "s2", quiz_sets: ["a", "b"] };
    const setCDeclined = { ...declinedParticipant, id: "s3", quiz_sets: ["c"] };
    const setNull      = { ...activeParticipant,   id: "s4", quiz_sets: null };
    const setEmpty     = { ...activeParticipant,   id: "s5", quiz_sets: [] };

    function setRow(label: string) {
      const card = screen.getByRole("group", { name: "Cases by question set" });
      const row = within(card).getByText(label).closest("div") as HTMLElement;
      return within(row);
    }

    // Route apiFetch by URL so per-participant PATCHes echo the new sets back.
    function mockRoster(participants: any[]) {
      mockApiFetch.mockImplementation((url: string, init?: any) => {
        if (url.includes("quiz-default-sets")) return Promise.resolve({ sets: null });
        if (url.includes("next-assignment")) return Promise.resolve({ next: "followup", source: "rotation" });
        if (url.includes("/quiz-sets")) {
          const id = url.split("/")[3];
          const p = participants.find((x) => x.id === id);
          return Promise.resolve({ ...p, quiz_sets: JSON.parse(init.body).quiz_sets });
        }
        return Promise.resolve(participants);
      });
    }

    beforeEach(() => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockRoster([setA, setAB, setCDeclined, setNull, setEmpty]);
    });

    it("shows enrolled and complete counts per question set", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Bob Jones");

      expect(setRow("A").getByText("2 enrolled")).toBeInTheDocument();
      expect(setRow("A").getByText("1 complete")).toBeInTheDocument();

      expect(setRow("B").getByText("1 enrolled")).toBeInTheDocument();
      expect(setRow("B").getByText("1 complete")).toBeInTheDocument();
    });

    it("counts a participant restricted to two sets under each of them", async () => {
      mockRoster([setAB]);
      render(<ParticipantsPanelPage />);
      await screen.findByText("Bob Jones");

      // The single participant appears under both A and B — the rows overlap
      // rather than partitioning the roster.
      expect(setRow("A").getByText("1 enrolled")).toBeInTheDocument();
      expect(setRow("B").getByText("1 enrolled")).toBeInTheDocument();
      expect(setRow("C").getByText("0 enrolled")).toBeInTheDocument();
      expect(setRow("No restriction").getByText("0 enrolled")).toBeInTheDocument();
    });

    it("puts unrestricted participants in their own bucket, not in every set", async () => {
      mockRoster([setNull, setEmpty]);
      render(<ParticipantsPanelPage />);
      await screen.findByText("Participants Panel");
      await waitFor(() =>
        expect(setRow("No restriction").getByText("2 enrolled")).toBeInTheDocument(),
      );

      // Both a null and an empty quiz_sets mean "draws from everything", and
      // neither inflates the individual set rows.
      for (const s of ["A", "B", "C", "D"]) {
        expect(setRow(s).getByText("0 enrolled")).toBeInTheDocument();
      }
    });

    it("excludes a participant who declined consent from the set's enrolled count", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Bob Jones");

      // Set C's only participant declined -> not a usable case.
      expect(setRow("C").getByText("0 enrolled")).toBeInTheDocument();
      expect(setRow("C").getByText("0 complete")).toBeInTheDocument();
    });

    it("shows a set with no participants as zero", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Bob Jones");

      expect(setRow("D").getByText("0 enrolled")).toBeInTheDocument();
      expect(setRow("D").getByText("0 complete")).toBeInTheDocument();
    });

    it("renders every set at zero for an empty roster", async () => {
      mockRoster([]);
      render(<ParticipantsPanelPage />);
      await screen.findByText("Participants Panel");

      for (const s of ["A", "B", "C", "D", "No restriction"]) {
        expect(setRow(s).getByText("0 enrolled")).toBeInTheDocument();
      }
    });

    it("recounts after a participant's sets are edited inline", async () => {
      mockRoster([setA]);
      render(<ParticipantsPanelPage />);
      await screen.findByText("Alice Smith");
      expect(setRow("A").getByText("1 enrolled")).toBeInTheDocument();
      expect(setRow("B").getByText("0 enrolled")).toBeInTheDocument();

      const chips = within(
        screen.getByRole("group", { name: `Question sets for ${setA.email}` }),
      );
      fireEvent.click(chips.getByRole("button", { name: "B" }));

      // The PATCH response (a + b) feeds straight back into the counts.
      await waitFor(() => expect(setRow("B").getByText("1 enrolled")).toBeInTheDocument());
      expect(setRow("A").getByText("1 enrolled")).toBeInTheDocument();
    });

    it("still counts every set when the tab filter hides participant cards", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Bob Jones");

      fireEvent.click(screen.getByRole("button", { name: /Declined/ }));

      expect(setRow("A").getByText("2 enrolled")).toBeInTheDocument();
      expect(setRow("No restriction").getByText("2 enrolled")).toBeInTheDocument();
    });
  });

  describe("join date filter", () => {
    // Build a join date that lands on the given local calendar day whatever
    // timezone the suite runs in — local noon is far from either boundary.
    function joinedOn(y: number, m: number, d: number): string {
      return new Date(y, m - 1, d, 12, 0, 0).toISOString();
    }

    const janFirst  = { ...activeParticipant,   id: "j1", first_name: "Early",  last_name: "Bird",  created_at: joinedOn(2025, 1, 1) };
    const janTenth  = { ...activeParticipant,   id: "j2", first_name: "Middle", last_name: "Child", created_at: joinedOn(2025, 1, 10) };
    const janTwenty = { ...completeParticipant, id: "j3", first_name: "Late",   last_name: "Comer", created_at: joinedOn(2025, 1, 20) };
    const undated   = { ...activeParticipant,   id: "j4", first_name: "No",     last_name: "Date",  created_at: null };

    const roster = [janFirst, janTenth, janTwenty];

    function setRange(from: string, to: string) {
      if (from) fireEvent.change(screen.getByLabelText("From"), { target: { value: from } });
      if (to)   fireEvent.change(screen.getByLabelText("To"),   { target: { value: to } });
    }

    beforeEach(() => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch.mockResolvedValue(roster);
    });

    it("keeps every participant when no range is set", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Early Bird");

      expect(screen.getByText("Middle Child")).toBeInTheDocument();
      expect(screen.getByText("Late Comer")).toBeInTheDocument();
      expect(screen.queryByText(/Showing \d+ of \d+/)).not.toBeInTheDocument();
    });

    it("filters out participants who joined before the From date", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Early Bird");

      setRange("2025-01-10", "");

      await waitFor(() => expect(screen.queryByText("Early Bird")).not.toBeInTheDocument());
      expect(screen.getByText("Middle Child")).toBeInTheDocument();
      expect(screen.getByText("Late Comer")).toBeInTheDocument();
    });

    it("filters out participants who joined after the To date", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Early Bird");

      setRange("", "2025-01-10");

      await waitFor(() => expect(screen.queryByText("Late Comer")).not.toBeInTheDocument());
      expect(screen.getByText("Early Bird")).toBeInTheDocument();
      expect(screen.getByText("Middle Child")).toBeInTheDocument();
    });

    it("keeps only participants inside a closed range", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Early Bird");

      setRange("2025-01-05", "2025-01-15");

      await waitFor(() => expect(screen.queryByText("Early Bird")).not.toBeInTheDocument());
      expect(screen.queryByText("Late Comer")).not.toBeInTheDocument();
      expect(screen.getByText("Middle Child")).toBeInTheDocument();
    });

    it("includes participants who joined exactly on either boundary day", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Early Bird");

      // Both bounds are inclusive: the participants defining the edges stay.
      setRange("2025-01-01", "2025-01-20");

      await waitFor(() => expect(screen.getByText("Early Bird")).toBeInTheDocument());
      expect(screen.getByText("Middle Child")).toBeInTheDocument();
      expect(screen.getByText("Late Comer")).toBeInTheDocument();
    });

    it("reports how many of the roster the range is showing", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Early Bird");

      setRange("2025-01-05", "");

      expect(await screen.findByText("Showing 2 of 3")).toBeInTheDocument();
    });

    it("rescopes the tab counts to the range", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Early Bird");
      expect(screen.getByRole("button", { name: "All (3)" })).toBeInTheDocument();

      setRange("2025-01-15", "");

      await waitFor(() =>
        expect(screen.getByRole("button", { name: "All (1)" })).toBeInTheDocument(),
      );
      // Only the complete participant (Jan 20) survives the range.
      expect(screen.getByRole("button", { name: "Complete (1)" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Active (0)" })).toBeInTheDocument();
    });

    it("rescopes the condition and question-set counts to the range", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Early Bird");

      const conditionGroup = () => within(screen.getByRole("group", { name: "Cases by condition" }));
      const setGroup = () => within(screen.getByRole("group", { name: "Cases by question set" }));
      const rowFor = (group: ReturnType<typeof within>, label: string) =>
        within(group.getByText(label).closest("div") as HTMLElement);

      // Jan 1 and Jan 10 are both "links"; Jan 20 is "followup". All three are
      // unrestricted, so they sit in the No restriction bucket.
      expect(rowFor(conditionGroup(), "Links").getByText("2 enrolled")).toBeInTheDocument();
      expect(rowFor(setGroup(), "No restriction").getByText("3 enrolled")).toBeInTheDocument();

      setRange("2025-01-15", "");

      await waitFor(() =>
        expect(rowFor(conditionGroup(), "Links").getByText("0 enrolled")).toBeInTheDocument(),
      );
      expect(rowFor(conditionGroup(), "Follow-up").getByText("1 enrolled")).toBeInTheDocument();
      expect(rowFor(setGroup(), "No restriction").getByText("1 enrolled")).toBeInTheDocument();
    });

    it("restores the full roster when the range is cleared", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Early Bird");

      setRange("2025-01-15", "");
      await waitFor(() => expect(screen.queryByText("Early Bird")).not.toBeInTheDocument());

      fireEvent.click(screen.getByRole("button", { name: "Clear" }));

      await waitFor(() => expect(screen.getByText("Early Bird")).toBeInTheDocument());
      expect(screen.getByText("Middle Child")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
    });

    it("hides participants with no join date and says how many", async () => {
      mockApiFetch.mockResolvedValue([...roster, undated]);
      render(<ParticipantsPanelPage />);
      await screen.findByText("No Date");

      setRange("2025-01-01", "2025-01-20");

      await waitFor(() => expect(screen.queryByText("No Date")).not.toBeInTheDocument());
      expect(
        screen.getByText("1 participant hidden — no join date recorded."),
      ).toBeInTheDocument();
    });

    it("treats an unparseable join date the same as a missing one", async () => {
      const malformed = {
        ...activeParticipant, id: "j5", first_name: "Bad", last_name: "Date", created_at: "not-a-date",
      };
      mockApiFetch.mockResolvedValue([...roster, malformed]);
      render(<ParticipantsPanelPage />);
      await screen.findByText("Bad Date");

      setRange("2025-01-01", "2025-01-20");

      await waitFor(() => expect(screen.queryByText("Bad Date")).not.toBeInTheDocument());
      expect(
        screen.getByText("1 participant hidden — no join date recorded."),
      ).toBeInTheDocument();
    });

    it("keeps undated participants visible while no range is set", async () => {
      mockApiFetch.mockResolvedValue([...roster, undated]);
      render(<ParticipantsPanelPage />);

      expect(await screen.findByText("No Date")).toBeInTheDocument();
      expect(screen.queryByText(/no join date recorded/)).not.toBeInTheDocument();
    });

    it("composes with the tab filter", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Early Bird");

      setRange("2025-01-05", "");
      await waitFor(() => expect(screen.queryByText("Early Bird")).not.toBeInTheDocument());

      fireEvent.click(screen.getByRole("button", { name: /Complete/ }));

      // In-range (Jan 10, Jan 20) narrowed to complete (Jan 20) = Late Comer.
      await waitFor(() => expect(screen.queryByText("Middle Child")).not.toBeInTheDocument());
      expect(screen.getByText("Late Comer")).toBeInTheDocument();
    });

    it("explains an empty roster as a date-range miss, not an empty tab", async () => {
      render(<ParticipantsPanelPage />);
      await screen.findByText("Early Bird");

      setRange("2025-06-01", "2025-06-30");

      expect(
        await screen.findByText("No participants in this date range."),
      ).toBeInTheDocument();
    });
  });
});
