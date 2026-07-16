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
});
