import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import ExportPanelPage from "../../pages/export_panel";
import { getMe, logout } from "../../lib/auth";

const mockReplace = jest.fn();
const mockPush    = jest.fn();
jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
}));

jest.mock("../../lib/auth", () => ({
  getMe:  jest.fn(),
  logout: jest.fn(),
}));

const mockGetMe   = getMe   as jest.Mock;
const mockLogout  = logout  as jest.Mock;

const adminUser = { id: "1", email: "admin@example.com", is_admin: true };

const mockWindowOpen = jest.fn();
Object.defineProperty(window, "open", { value: mockWindowOpen, writable: true });

describe("ExportPanelPage", () => {
  beforeEach(() => {
    sessionStorage.clear();
    window.history.replaceState({}, "", "/export_panel");
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockWindowOpen.mockClear();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<ExportPanelPage />);
    expect(screen.getByText("Loading export panel…")).toBeInTheDocument();
  });

  it("redirects to /login when not authenticated", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<ExportPanelPage />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("redirects non-admin users to /dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "2", email: "user@test.edu", is_admin: false } });
    render(<ExportPanelPage />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
  });

  it("renders the panel with all research and operational export cards for an admin", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<ExportPanelPage />);

    expect(await screen.findByText("Export Data")).toBeInTheDocument();
    expect(screen.getByText("Participants")).toBeInTheDocument();
    expect(screen.getByText("Quiz Answers")).toBeInTheDocument();
    expect(screen.getByText("Survey Responses")).toBeInTheDocument();
    expect(screen.getByText("Events (Copy + Links)")).toBeInTheDocument();
    expect(screen.getByText("Chat Messages")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Download CSV" })).toHaveLength(7);
  });

  it("calls window.open with the correct URL when a Download CSV button is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<ExportPanelPage />);

    await screen.findByText("Export Data");
    const buttons = screen.getAllByRole("button", { name: "Download CSV" });
    fireEvent.click(buttons[0]); // Participants

    expect(mockWindowOpen).toHaveBeenCalledWith("/api/export/participants", "_blank");
  });

  it("keeps Study 2 selection in downloads opened in a new tab", async () => {
    window.history.replaceState({}, "", "/export_panel?study=study-2");
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<ExportPanelPage />);
    await screen.findByText("Export Data");
    fireEvent.click(screen.getAllByRole("button", { name: "Download CSV" })[0]);
    expect(mockWindowOpen).toHaveBeenCalledWith("/api/studies/study-2/export/participants", "_blank");
    fireEvent.click(screen.getByRole("button", { name: "Download ZIP" }));
    expect(mockWindowOpen).toHaveBeenCalledWith("/api/studies/study-2/export/research-bundle", "_blank");
  });

  it("downloads the versioned research snapshot as a ZIP", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<ExportPanelPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Download ZIP" }));
    expect(mockWindowOpen).toHaveBeenCalledWith("/api/export/research-bundle", "_blank");
  });

  it("disables the button and shows 'Opening…' immediately after clicking", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<ExportPanelPage />);

    await screen.findByText("Export Data");
    const buttons = screen.getAllByRole("button", { name: "Download CSV" });
    fireEvent.click(buttons[0]);

    const openingBtn = screen.getAllByRole("button", { name: "Opening…" });
    expect(openingBtn[0]).toBeDisabled();
  });

  it("re-enables the button after the 2-second timeout", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<ExportPanelPage />);

    await screen.findByText("Export Data");
    const buttons = screen.getAllByRole("button", { name: "Download CSV" });
    fireEvent.click(buttons[0]);

    expect(screen.getByRole("button", { name: "Opening…" })).toBeDisabled();

    act(() => { jest.advanceTimersByTime(2000); });

    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "Download CSV" })).toHaveLength(7)
    );
  });

  it("opens different URLs for each export type", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<ExportPanelPage />);

    await screen.findByText("Export Data");

    const expectedUrls = [
      "/api/export/participants",
      "/api/export/quiz-answers",
      "/api/export/survey-responses",
      "/api/export/events",
      "/api/export/chat-messages",
      "/api/export/research-questions",
      "/api/export/research-variants",
    ];

    for (const url of expectedUrls) {
      // reset to all-enabled state before each click
      act(() => { jest.advanceTimersByTime(2000); });
      await waitFor(() =>
        expect(screen.getAllByRole("button", { name: "Download CSV" })).toHaveLength(7)
      );
      const buttons = screen.getAllByRole("button", { name: "Download CSV" });
      const idx = expectedUrls.indexOf(url);
      fireEvent.click(buttons[idx]);
      expect(mockWindowOpen).toHaveBeenCalledWith(url, "_blank");
    }
  });

  it("navigates to /dashboard when the Dashboard button is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<ExportPanelPage />);

    fireEvent.click(await screen.findByText("Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("logs out and redirects to /login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockLogout.mockResolvedValue(undefined);
    render(<ExportPanelPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
