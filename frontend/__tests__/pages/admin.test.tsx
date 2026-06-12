import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AdminPage from "../../pages/admin";
import { getMe, logout } from "../../lib/auth";

const mockReplace = jest.fn();
const mockPush = jest.fn();
jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
}));

jest.mock("../../lib/auth", () => ({
  getMe: jest.fn(),
  logout: jest.fn(),
}));

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;

describe("AdminPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<AdminPage />);
    expect(screen.getByText("Loading dashboard…")).toBeInTheDocument();
  });

  it("renders the admin panel links for an admin user", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "admin@example.com", is_admin: true } });
    render(<AdminPage />);

    expect(await screen.findByText("Admin Panel")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: /Quiz Questions Panel/ })).toHaveAttribute("href", "/questions_panel");
    expect(screen.getByRole("link", { name: /Survey Questions Panel/ })).toHaveAttribute("href", "/surveys_panel");
    expect(screen.getByRole("link", { name: /Links Panel/ })).toHaveAttribute("href", "/links_panel");
    expect(screen.getByRole("link", { name: /Trusted Domain Allowlist/ })).toHaveAttribute("href", "/allowlist_panel");
  });

  it("redirects non-admin users to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "2", email: "user@example.com", is_admin: false } });
    render(<AdminPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("Admin Panel")).not.toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<AdminPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "admin@example.com", is_admin: true } });
    mockLogout.mockResolvedValue(undefined);
    render(<AdminPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("navigates to the dashboard when the Dashboard button is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "admin@example.com", is_admin: true } });
    render(<AdminPage />);

    fireEvent.click(await screen.findByText("Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });
});
