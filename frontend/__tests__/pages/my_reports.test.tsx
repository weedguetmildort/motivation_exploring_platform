import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import MyReportsPage from "../../pages/my_reports";
import { getMe, logout } from "../../lib/auth";
import { getMyReports, addComment } from "../../lib/reports";

const mockReplace = jest.fn();
const mockPush = jest.fn();
jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
}));

jest.mock("../../lib/auth", () => ({
  getMe: jest.fn(),
  logout: jest.fn(),
}));

jest.mock("../../lib/reports", () => ({
  getMyReports: jest.fn(),
  addComment: jest.fn(),
}));

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockGetMyReports = getMyReports as jest.Mock;
const mockAddComment = addComment as jest.Mock;

const regularUser = { id: "1", email: "user@example.com", is_admin: false };

const openReport = {
  id: "r1",
  user_email: "user@example.com",
  quiz_id: "base",
  question_id: "q1",
  category: "bug" as const,
  description: "The submit button did nothing.",
  status: "open" as const,
  comments: [
    {
      id: "c1",
      author_email: "admin@example.com",
      is_admin: true,
      body: "Looking into it.",
      created_at: "2024-01-02T12:00:00.000Z",
    },
  ],
  created_at: "2024-01-01T12:00:00.000Z",
  updated_at: "2024-01-02T12:00:00.000Z",
};

const closedReport = {
  id: "r2",
  user_email: "user@example.com",
  quiz_id: null,
  question_id: null,
  category: "other" as const,
  description: "Already fixed, thanks.",
  status: "closed" as const,
  comments: [],
  created_at: "2024-01-03T12:00:00.000Z",
  updated_at: "2024-01-03T12:00:00.000Z",
};

describe("MyReportsPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockGetMyReports.mockReset();
    mockAddComment.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<MyReportsPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<MyReportsPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("loads all of the user's reports by default", async () => {
    mockGetMe.mockResolvedValue({ user: regularUser });
    mockGetMyReports.mockResolvedValue([openReport]);
    render(<MyReportsPage />);

    expect(await screen.findByText("My Reports")).toBeInTheDocument();
    expect(await screen.findByText("The submit button did nothing.")).toBeInTheDocument();
    expect(mockGetMyReports).toHaveBeenCalledWith(undefined);
  });

  it("shows an empty state when there are no reports", async () => {
    mockGetMe.mockResolvedValue({ user: regularUser });
    mockGetMyReports.mockResolvedValue([]);
    render(<MyReportsPage />);

    await waitFor(() => expect(mockGetMyReports).toHaveBeenCalled());
    expect(
      await screen.findByText(/No reports found\. You can submit a report/)
    ).toBeInTheDocument();
  });

  it("switches tabs and reloads with the selected status filter", async () => {
    mockGetMe.mockResolvedValue({ user: regularUser });
    mockGetMyReports.mockResolvedValue([openReport]);
    render(<MyReportsPage />);

    await screen.findByText("The submit button did nothing.");

    mockGetMyReports.mockResolvedValue([closedReport]);
    fireEvent.click(screen.getByText("Closed"));

    await waitFor(() => expect(mockGetMyReports).toHaveBeenCalledWith("closed"));
    expect(await screen.findByText("Already fixed, thanks.")).toBeInTheDocument();
  });

  it("expands a report to show its description and comment thread", async () => {
    mockGetMe.mockResolvedValue({ user: regularUser });
    mockGetMyReports.mockResolvedValue([openReport]);
    render(<MyReportsPage />);

    const row = await screen.findByText("The submit button did nothing.");
    fireEvent.click(row);

    expect(await screen.findByText("Looking into it.")).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
  });

  it("allows commenting on an open report", async () => {
    mockGetMe.mockResolvedValue({ user: regularUser });
    mockGetMyReports.mockResolvedValue([openReport]);
    mockAddComment.mockResolvedValue({
      ...openReport,
      comments: [
        ...openReport.comments,
        { id: "c2", author_email: "user@example.com", is_admin: false, body: "Still broken.", created_at: "2024-01-04T00:00:00.000Z" },
      ],
    });
    render(<MyReportsPage />);

    const row = await screen.findByText("The submit button did nothing.");
    fireEvent.click(row);

    const textarea = await screen.findByPlaceholderText("Add a follow-up comment…");
    fireEvent.change(textarea, { target: { value: "Still broken." } });
    fireEvent.click(screen.getByRole("button", { name: "Post comment" }));

    await waitFor(() => expect(mockAddComment).toHaveBeenCalledWith("r1", "Still broken."));
    expect(await screen.findByText("Still broken.")).toBeInTheDocument();
  });

  it("does not show a comment box for a closed report", async () => {
    mockGetMe.mockResolvedValue({ user: regularUser });
    mockGetMyReports.mockResolvedValue([closedReport]);
    render(<MyReportsPage />);

    const row = await screen.findByText("Already fixed, thanks.");
    fireEvent.click(row);

    await waitFor(() => expect(screen.queryByText(/No reports found/)).not.toBeInTheDocument());
    expect(screen.queryByPlaceholderText("Add a follow-up comment…")).not.toBeInTheDocument();
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: regularUser });
    mockGetMyReports.mockResolvedValue([]);
    mockLogout.mockResolvedValue(undefined);
    render(<MyReportsPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("navigates to the dashboard when Dashboard is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: regularUser });
    mockGetMyReports.mockResolvedValue([]);
    render(<MyReportsPage />);

    fireEvent.click(await screen.findByText("Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });
});
