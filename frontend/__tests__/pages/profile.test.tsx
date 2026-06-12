import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ProfilePage from "../../pages/profile";
import { getMe, logout, changePassword } from "../../lib/auth";

const mockReplace = jest.fn();
const mockPush = jest.fn();
jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
}));

jest.mock("../../lib/auth", () => ({
  getMe: jest.fn(),
  logout: jest.fn(),
  changePassword: jest.fn(),
}));

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockChangePassword = changePassword as jest.Mock;

function fillPasswordForm(container: HTMLElement, current: string, next: string, confirm: string) {
  const inputs = container.querySelectorAll('input[type="password"]');
  fireEvent.change(inputs[0], { target: { value: current } });
  fireEvent.change(inputs[1], { target: { value: next } });
  fireEvent.change(inputs[2], { target: { value: confirm } });
}

describe("ProfilePage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockChangePassword.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<ProfilePage />);
    expect(screen.getByText("Loading profile…")).toBeInTheDocument();
  });

  it("renders the profile page for a logged-in user", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "user@example.com", is_admin: false } });
    render(<ProfilePage />);

    expect(await screen.findByText("Profile")).toBeInTheDocument();
    expect(screen.getByText("Change Password")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<ProfilePage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "user@example.com", is_admin: false } });
    mockLogout.mockResolvedValue(undefined);
    render(<ProfilePage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("navigates to the dashboard when the Dashboard button is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "user@example.com", is_admin: false } });
    render(<ProfilePage />);

    fireEvent.click(await screen.findByText("Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("shows a validation error when fields are missing", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "user@example.com", is_admin: false } });
    const { container } = render(<ProfilePage />);
    await screen.findByText("Profile");

    fireEvent.submit(container.querySelector("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("Please fill out all fields.");
    expect(mockChangePassword).not.toHaveBeenCalled();
  });

  it("shows a validation error when new passwords do not match", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "user@example.com", is_admin: false } });
    const { container } = render(<ProfilePage />);
    await screen.findByText("Profile");

    fillPasswordForm(container, "oldpass", "newpass1", "newpass2");
    fireEvent.submit(container.querySelector("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("New password and confirmation do not match.");
    expect(mockChangePassword).not.toHaveBeenCalled();
  });

  it("shows a validation error when the new password is too short", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "user@example.com", is_admin: false } });
    const { container } = render(<ProfilePage />);
    await screen.findByText("Profile");

    fillPasswordForm(container, "oldpass", "abc", "abc");
    fireEvent.submit(container.querySelector("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("New password must be at least 6 characters long.");
    expect(mockChangePassword).not.toHaveBeenCalled();
  });

  it("submits the password change and shows a success message", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "user@example.com", is_admin: false } });
    mockChangePassword.mockResolvedValue({ ok: true });
    const { container } = render(<ProfilePage />);
    await screen.findByText("Profile");

    fillPasswordForm(container, "oldpass", "newpassword", "newpassword");
    fireEvent.submit(container.querySelector("form")!);

    await waitFor(() => expect(mockChangePassword).toHaveBeenCalledWith("oldpass", "newpassword"));
    expect(await screen.findByRole("status")).toHaveTextContent("Password updated successfully.");

    const inputs = container.querySelectorAll('input[type="password"]');
    inputs.forEach((input) => expect((input as HTMLInputElement).value).toBe(""));
  });

  it("shows the backend error message when changePassword fails with a message", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "user@example.com", is_admin: false } });
    mockChangePassword.mockRejectedValue(new Error("Incorrect current password"));
    const { container } = render(<ProfilePage />);
    await screen.findByText("Profile");

    fillPasswordForm(container, "wrongpass", "newpassword", "newpassword");
    fireEvent.submit(container.querySelector("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect current password");
  });

  it("shows the backend detail when changePassword fails with a detail field", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "user@example.com", is_admin: false } });
    mockChangePassword.mockRejectedValue({ detail: "Server exploded" });
    const { container } = render(<ProfilePage />);
    await screen.findByText("Profile");

    fillPasswordForm(container, "wrongpass", "newpassword", "newpassword");
    fireEvent.submit(container.querySelector("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("Server exploded");
  });

  it("shows a generic error when changePassword fails without a message or detail", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1", email: "user@example.com", is_admin: false } });
    mockChangePassword.mockRejectedValue({});
    const { container } = render(<ProfilePage />);
    await screen.findByText("Profile");

    fillPasswordForm(container, "wrongpass", "newpassword", "newpassword");
    fireEvent.submit(container.querySelector("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to change password.");
  });
});
