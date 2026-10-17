import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AnalyticsPanelPage from "../../pages/analytics_panel";
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

const mockGetMe    = getMe    as jest.Mock;
const mockLogout   = logout   as jest.Mock;
const mockApiFetch = apiFetch as jest.Mock;

const adminUser = { id: "1", email: "admin@example.com", is_admin: true };

const copyEvent = {
  id: "c1",
  user_email: "alice@test.edu",
  question_id: "q1",
  quiz_id: "quiz1",
  copied_text: "some copied text",
  created_at: "2025-01-01T10:00:00.000Z",
};

const linkClick = {
  id: "l1",
  user_email: "bob@test.edu",
  question_id: "q2",
  quiz_id: "quiz1",
  url: "https://example.com/resource",
  clicked_at: "2025-01-02T10:00:00.000Z",
};

const chatMessage = {
  id: "m1",
  user_email: "carol@test.edu",
  question_id: "q3",
  trigger: "start",
  stated_choice_id: { default: "A", B: "no" },
  answer_incorrectly: false,
  created_at: "2025-01-03T10:00:00.000Z",
};

describe("AnalyticsPanelPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockApiFetch.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<AnalyticsPanelPage />);
    expect(screen.getByText("Loading analytics…")).toBeInTheDocument();
  });

  it("redirects to /login when not authenticated", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<AnalyticsPanelPage />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("redirects non-admin users to /dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "2", email: "user@test.edu", is_admin: false } });
    render(<AnalyticsPanelPage />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
  });

  it("renders the panel title and the three tab buttons for an admin", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<AnalyticsPanelPage />);

    expect(await screen.findByText("Analytics Panel")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy Events" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Link Clicks" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chat Interactions" })).toBeInTheDocument();
  });

  it("loads copy-events and shows the table on the default Copy Events tab", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([copyEvent]);
    render(<AnalyticsPanelPage />);

    await screen.findByText("Analytics Panel");
    expect(await screen.findByText("alice@test.edu")).toBeInTheDocument();
    expect(screen.getByText("some copied text")).toBeInTheDocument();
    expect(mockApiFetch).toHaveBeenCalledWith("/api/copy-events");
  });

  it("shows a loading indicator on the Copy Events tab while fetching", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockReturnValue(new Promise(() => {}));
    render(<AnalyticsPanelPage />);

    await screen.findByText("Analytics Panel");
    expect(await screen.findByText("Loading…")).toBeInTheDocument();
  });

  it("shows an error when copy events fail to load", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockRejectedValue(new Error("network error"));
    render(<AnalyticsPanelPage />);

    expect(await screen.findByText("Failed to load copy events.")).toBeInTheDocument();
  });

  it("shows 'No results.' when the Copy Events tab returns an empty list", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<AnalyticsPanelPage />);

    await screen.findByText("Analytics Panel");
    expect(await screen.findByText("No results.")).toBeInTheDocument();
  });

  it("shows the event count label on the Copy Events tab", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([copyEvent]);
    render(<AnalyticsPanelPage />);

    await screen.findByText("alice@test.edu");
    expect(screen.getByText("1 events")).toBeInTheDocument();
  });

  it("filters copy events by email search", async () => {
    const otherEvent = { ...copyEvent, id: "c2", user_email: "dave@test.edu" };
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([copyEvent, otherEvent]);
    render(<AnalyticsPanelPage />);

    await screen.findByText("alice@test.edu");
    expect(screen.getByText("dave@test.edu")).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText("Filter by email…");
    fireEvent.change(searchInput, { target: { value: "alice" } });

    expect(screen.getByText("alice@test.edu")).toBeInTheDocument();
    expect(screen.queryByText("dave@test.edu")).not.toBeInTheDocument();
    expect(screen.getByText("1 events")).toBeInTheDocument();
  });

  it("clears the search when the clear button is clicked", async () => {
    const otherEvent = { ...copyEvent, id: "c2", user_email: "dave@test.edu" };
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([copyEvent, otherEvent]);
    render(<AnalyticsPanelPage />);

    await screen.findByText("alice@test.edu");

    const searchInput = screen.getByPlaceholderText("Filter by email…");
    fireEvent.change(searchInput, { target: { value: "alice" } });
    expect(screen.queryByText("dave@test.edu")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "✕" }));
    expect(screen.getByText("dave@test.edu")).toBeInTheDocument();
  });

  describe("Link Clicks tab", () => {
    it("loads link clicks when the Link Clicks tab is selected", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([copyEvent])
        .mockResolvedValueOnce([linkClick]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Link Clicks" }));

      expect(await screen.findByText("bob@test.edu")).toBeInTheDocument();
      expect(screen.getByText(/example\.com/)).toBeInTheDocument();
      expect(screen.getByText("1 clicks")).toBeInTheDocument();
    });

    it("shows an error when link clicks fail to load", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockRejectedValueOnce(new Error("network error"));
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Link Clicks" }));

      expect(await screen.findByText("Failed to load link clicks.")).toBeInTheDocument();
    });

    it("filters link clicks by email search", async () => {
      const otherClick = { ...linkClick, id: "l2", user_email: "eve@test.edu" };
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([linkClick, otherClick]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Link Clicks" }));

      await screen.findByText("bob@test.edu");
      const searchInput = screen.getByPlaceholderText("Filter by email…");
      fireEvent.change(searchInput, { target: { value: "bob" } });

      expect(screen.getByText("bob@test.edu")).toBeInTheDocument();
      expect(screen.queryByText("eve@test.edu")).not.toBeInTheDocument();
    });
  });

  describe("Chat Interactions tab", () => {
    it("loads chat messages when the Chat Interactions tab is selected", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([copyEvent])
        .mockResolvedValueOnce([chatMessage]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

      expect(await screen.findByText("carol@test.edu")).toBeInTheDocument();
      expect(screen.getByText("1 messages")).toBeInTheDocument();
    });

    it("shows an error when chat messages fail to load", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockRejectedValueOnce(new Error("network error"));
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

      expect(await screen.findByText("Failed to load chat interactions.")).toBeInTheDocument();
    });

    it("filters messages by the Only with stated choice checkbox", async () => {
      const noChoiceMsg = { ...chatMessage, id: "m2", user_email: "dan@test.edu", stated_choice_id: null };
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([chatMessage, noChoiceMsg]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

      await screen.findByText("carol@test.edu");
      expect(screen.getByText("dan@test.edu")).toBeInTheDocument();
      expect(screen.getByText("2 messages")).toBeInTheDocument();

      fireEvent.click(screen.getByLabelText("Only with stated choice"));

      expect(screen.getByText("carol@test.edu")).toBeInTheDocument();
      expect(screen.queryByText("dan@test.edu")).not.toBeInTheDocument();
      expect(screen.getByText("1 messages")).toBeInTheDocument();
    });

    it("filters messages by the Only leaked manipulation checkbox", async () => {
      const leakedMsg = { ...chatMessage, id: "m6", user_email: "greg@test.edu", manipulation_leaked: { default: true } };
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([chatMessage, leakedMsg]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

      await screen.findByText("carol@test.edu");
      expect(screen.getByText("greg@test.edu")).toBeInTheDocument();
      expect(screen.getByText("2 messages")).toBeInTheDocument();

      fireEvent.click(screen.getByLabelText("Only leaked manipulation"));

      expect(screen.queryByText("carol@test.edu")).not.toBeInTheDocument();
      expect(screen.getByText("greg@test.edu")).toBeInTheDocument();
      expect(screen.getByText("1 messages")).toBeInTheDocument();
    });

    it("shows a leaked warning badge when manipulation_leaked has a true value", async () => {
      const leakedMsg = { ...chatMessage, id: "m7", manipulation_leaked: { default: true } };
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([leakedMsg]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

      expect(await screen.findByText("⚠ Leaked")).toBeInTheDocument();
    });

    it("shows 'No' when manipulation_leaked has no true values", async () => {
      const cleanMsg = { ...chatMessage, id: "m8", manipulation_leaked: { default: false } };
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([cleanMsg]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

      await screen.findByText("carol@test.edu");
      expect(screen.queryByText("⚠ Leaked")).not.toBeInTheDocument();
    });

    it("shows '—' when manipulation_leaked is null", async () => {
      const noLeak = { ...chatMessage, id: "m9", manipulation_leaked: null };
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([noLeak]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

      await screen.findByText("carol@test.edu");
      expect(screen.queryByText("⚠ Leaked")).not.toBeInTheDocument();
      const dashes = screen.getAllByText("—");
      expect(dashes.length).toBeGreaterThan(0);
    });

    it("filters chat messages by email search", async () => {
      const otherMsg = { ...chatMessage, id: "m3", user_email: "frank@test.edu" };
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([chatMessage, otherMsg]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

      await screen.findByText("carol@test.edu");
      const searchInput = screen.getByPlaceholderText("Filter by email…");
      fireEvent.change(searchInput, { target: { value: "carol" } });

      expect(screen.getByText("carol@test.edu")).toBeInTheDocument();
      expect(screen.queryByText("frank@test.edu")).not.toBeInTheDocument();
    });

    it("shows choiceSummary: renders stated_choice_id as key:value pairs", async () => {
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([chatMessage]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

      await screen.findByText("carol@test.edu");
      expect(screen.getByText("A, B:no")).toBeInTheDocument();
    });

    it("shows '—' when stated_choice_id is null", async () => {
      const noChoice = { ...chatMessage, stated_choice_id: null };
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([noChoice]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

      await screen.findByText("carol@test.edu");
      const dashes = screen.getAllByText("—");
      expect(dashes.length).toBeGreaterThan(0);
    });

    it("shows 'Yes' for answer_incorrectly=true and 'No' for false", async () => {
      const wrongMsg   = { ...chatMessage, id: "m4", answer_incorrectly: true };
      const correctMsg = { ...chatMessage, id: "m5", answer_incorrectly: false };
      mockGetMe.mockResolvedValue({ user: adminUser });
      mockApiFetch
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([wrongMsg, correctMsg]);
      render(<AnalyticsPanelPage />);

      await screen.findByText("Analytics Panel");
      fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

      await screen.findByText("Yes");
      expect(screen.getByText("No")).toBeInTheDocument();
    });
  });

  it("truncates long copied text and shows an em dash for a missing question id", async () => {
    const longCopy = { ...copyEvent, id: "c9", question_id: null, copied_text: "x".repeat(100) };
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([longCopy]);
    render(<AnalyticsPanelPage />);

    await screen.findByText("Analytics Panel");
    expect(await screen.findByText("x".repeat(80) + "…")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows an em dash for a link click with no question id", async () => {
    const noQ = { ...linkClick, id: "l9", question_id: null };
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([noQ]);
    render(<AnalyticsPanelPage />);

    await screen.findByText("Analytics Panel");
    fireEvent.click(screen.getByRole("button", { name: "Link Clicks" }));

    await screen.findByText("bob@test.edu");
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders 'none' for null stated-choice values and an em dash for unknown correctness", async () => {
    const nullChoice = {
      ...chatMessage,
      id: "m9",
      stated_choice_id: { default: null, A: null },
      answer_incorrectly: null,
    };
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([nullChoice]);
    render(<AnalyticsPanelPage />);

    await screen.findByText("Analytics Panel");
    fireEvent.click(screen.getByRole("button", { name: "Chat Interactions" }));

    await screen.findByText("carol@test.edu");
    expect(screen.getByText("none, A:none")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("navigates to the dashboard when the Dashboard button is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<AnalyticsPanelPage />);

    await screen.findByText("Analytics Panel");
    fireEvent.click(await screen.findByText("Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("logs out and redirects to /login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockLogout.mockResolvedValue(undefined);
    mockApiFetch.mockResolvedValue([]);
    render(<AnalyticsPanelPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
