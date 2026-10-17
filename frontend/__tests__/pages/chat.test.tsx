import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ChatPage from "../../pages/chat";
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

jest.mock("../../components/ChatBox", () => () => <div data-testid="chat-box" />);

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;

describe("ChatPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
  });

  it("shows a checking state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<ChatPage />);
    expect(screen.getByText("Checking session…")).toBeInTheDocument();
  });

  it("renders the chat page for an admin user", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "admin@example.com", is_admin: true } });
    render(<ChatPage />);

    expect(await screen.findByText("Chat")).toBeInTheDocument();
    expect(screen.getByTestId("chat-box")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("redirects non-admin users to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "2", email: "user@example.com", is_admin: false } });
    render(<ChatPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("Chat")).not.toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<ChatPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "admin@example.com", is_admin: true } });
    mockLogout.mockResolvedValue(undefined);
    render(<ChatPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("navigates to the dashboard when the Dashboard button is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "admin@example.com", is_admin: true } });
    render(<ChatPage />);

    fireEvent.click(await screen.findByText("Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });
});
