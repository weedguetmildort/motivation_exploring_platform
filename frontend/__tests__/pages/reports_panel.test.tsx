import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ReportsPanelPage from "../../pages/reports_panel";
import { getMe, logout } from "../../lib/auth";
import { getAllReports, addComment, updateStatus } from "../../lib/reports";

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
  getAllReports: jest.fn(),
  addComment: jest.fn(),
  updateStatus: jest.fn(),
}));

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockGetAllReports = getAllReports as jest.Mock;
const mockAddComment = addComment as jest.Mock;
const mockUpdateStatus = updateStatus as jest.Mock;

const adminUser = { id: "1", email: "admin@example.com", is_admin: true };

const openReport = {
  id: "r1",
  user_email: "student@example.com",
  quiz_id: "base",
  question_id: "q1",
  category: "bug" as const,
  description: "The submit button did nothing.",
  status: "open" as const,
  comments: [],
  created_at: "2024-01-01T12:00:00.000Z",
  updated_at: "2024-01-01T12:00:00.000Z",
};

const resolvedReportWithComment = {
  id: "r2",
  user_email: "other@example.com",
  quiz_id: null,
  question_id: null,
  category: "other" as const,
  description: "Just a note.",
  status: "resolved" as const,
  comments: [
    {
      id: "c1",
      author_email: "admin@example.com",
      is_admin: true,
      body: "Looking into it.",
      created_at: "2024-01-02T12:00:00.000Z",
    },
  ],
  created_at: "2024-01-02T10:00:00.000Z",
  updated_at: "2024-01-02T12:00:00.000Z",
};

describe("ReportsPanelPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockGetAllReports.mockReset();
    mockAddComment.mockReset();
    mockUpdateStatus.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<ReportsPanelPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("redirects non-admin users to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "2", email: "user@example.com", is_admin: false } });
    render(<ReportsPanelPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("Issue Reports")).not.toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<ReportsPanelPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("loads open reports by default for an admin user", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetAllReports.mockResolvedValue([openReport]);
    render(<ReportsPanelPage />);

    expect(await screen.findByText("Issue Reports")).toBeInTheDocument();
    expect(await screen.findByText("The submit button did nothing.")).toBeInTheDocument();
    expect(mockGetAllReports).toHaveBeenCalledWith("open");
  });

  it("shows a message when there are no reports", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetAllReports.mockResolvedValue([]);
    render(<ReportsPanelPage />);

    await waitFor(() => expect(mockGetAllReports).toHaveBeenCalled());
    expect(await screen.findByText("No reports found.")).toBeInTheDocument();
  });

  it("switches tabs and reloads with the selected status filter", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetAllReports.mockResolvedValue([openReport]);
    render(<ReportsPanelPage />);

    await screen.findByText("The submit button did nothing.");

    mockGetAllReports.mockResolvedValue([resolvedReportWithComment]);
    fireEvent.click(screen.getByText("Resolved"));

    await waitFor(() => expect(mockGetAllReports).toHaveBeenCalledWith("resolved"));
    expect(await screen.findByText("Just a note.")).toBeInTheDocument();
  });

  it("requests all statuses when the All tab is selected", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetAllReports.mockResolvedValue([openReport]);
    render(<ReportsPanelPage />);

    await screen.findByText("The submit button did nothing.");
    fireEvent.click(screen.getByText("All"));

    await waitFor(() => expect(mockGetAllReports).toHaveBeenCalledWith(undefined));
  });

  it("expands a report to show details, status control, and comment thread", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetAllReports.mockResolvedValue([resolvedReportWithComment]);
    render(<ReportsPanelPage />);

    const row = await screen.findByText("Just a note.");
    fireEvent.click(row);

    expect(await screen.findByText("Reported by:")).toBeInTheDocument();
    expect(screen.getByText("other@example.com")).toBeInTheDocument();
    expect(screen.getByText("Looking into it.")).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
  });

  it("changes the status via the dropdown", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetAllReports.mockResolvedValue([openReport]);
    mockUpdateStatus.mockResolvedValue({ ...openReport, status: "in_progress" });
    render(<ReportsPanelPage />);

    const row = await screen.findByText("The submit button did nothing.");
    fireEvent.click(row);

    const select = await screen.findByDisplayValue("Open");
    fireEvent.change(select, { target: { value: "in_progress" } });

    await waitFor(() => expect(mockUpdateStatus).toHaveBeenCalledWith("r1", "in_progress"));
  });

  it("posts a comment and clears the textarea", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetAllReports.mockResolvedValue([openReport]);
    mockAddComment.mockResolvedValue({
      ...openReport,
      comments: [
        { id: "c2", author_email: "admin@example.com", is_admin: true, body: "On it.", created_at: "2024-01-03T00:00:00.000Z" },
      ],
    });
    render(<ReportsPanelPage />);

    const row = await screen.findByText("The submit button did nothing.");
    fireEvent.click(row);

    const textarea = await screen.findByPlaceholderText("Add a comment…");
    fireEvent.change(textarea, { target: { value: "On it." } });
    fireEvent.click(screen.getByRole("button", { name: "Post comment" }));

    await waitFor(() => expect(mockAddComment).toHaveBeenCalledWith("r1", "On it."));
    expect(await screen.findByText("On it.")).toBeInTheDocument();
  });

  it("disables the post comment button when the textarea is empty", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetAllReports.mockResolvedValue([openReport]);
    render(<ReportsPanelPage />);

    const row = await screen.findByText("The submit button did nothing.");
    fireEvent.click(row);

    await screen.findByPlaceholderText("Add a comment…");
    expect(screen.getByRole("button", { name: "Post comment" })).toBeDisabled();
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetAllReports.mockResolvedValue([]);
    mockLogout.mockResolvedValue(undefined);
    render(<ReportsPanelPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("navigates to the admin panel when Dashboard is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockGetAllReports.mockResolvedValue([]);
    render(<ReportsPanelPage />);

    fireEvent.click(await screen.findByText("Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/admin");
  });
});
