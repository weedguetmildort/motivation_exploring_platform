import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import DashboardPage from "../../pages/dashboard";
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

const baseUser = {
  id: "1",
  email: "user@example.com",
  is_admin: false,
  assigned_var: "followup",
  demographics_completed: true,
  survey_pre_base_completed: false,
  quiz_base_completed: false,
  survey_post_base_completed: false,
  quiz_variant_completed: false,
  survey_post_variant_completed: false,
};

const completeUser = {
  ...baseUser,
  survey_pre_base_completed: true,
  quiz_base_completed: true,
  survey_post_base_completed: true,
  quiz_variant_completed: true,
  survey_post_variant_completed: true,
};

describe("DashboardPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<DashboardPage />);
    expect(screen.getByText("Loading dashboard…")).toBeInTheDocument();
  });

  it("redirects to demographics when not yet completed", async () => {
    mockGetMe.mockResolvedValue({ user: { ...baseUser, demographics_completed: false } });
    render(<DashboardPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/demographics"));
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<DashboardPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("shows the study-complete card when all steps are done", async () => {
    mockGetMe.mockResolvedValue({ user: completeUser });
    render(<DashboardPage />);

    expect(await screen.findByText("Study Complete — thank you for participating!")).toBeInTheDocument();
    expect(screen.queryByText("Admin")).not.toBeInTheDocument();
  });

  it("shows the next-step hero card and navigates to it", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    render(<DashboardPage />);

    expect(await screen.findByText("Next Step")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Survey 1" })).toBeInTheDocument();

    const button = screen.getByRole("button", { name: /Start the Survey 1/ });
    fireEvent.click(button);

    expect(mockPush).toHaveBeenCalledWith("/survey?stage=pre_quiz");
  });

  it("renders the admin section with tool, quiz, and survey links for admins", async () => {
    mockGetMe.mockResolvedValue({ user: { ...baseUser, is_admin: true } });
    render(<DashboardPage />);

    expect(await screen.findByText("Admin")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: /Chat/ })).toHaveAttribute("href", "/chat");
    expect(screen.getByRole("link", { name: /Playground/ })).toHaveAttribute("href", "/playground");
    expect(screen.getByRole("link", { name: /Admin Panel/ })).toHaveAttribute("href", "/admin");

    expect(screen.getByRole("link", { name: /Base Quiz/ })).toHaveAttribute("href", "/quiz/base");
    expect(screen.getByRole("link", { name: /Follow-Up Questions/ })).toHaveAttribute("href", "/quiz/followup");
    expect(screen.getByRole("link", { name: /Dual Agent/ })).toHaveAttribute("href", "/quiz/double");
    expect(screen.getByRole("link", { name: /Embedded Links/ })).toHaveAttribute("href", "/quiz/links");

    expect(screen.getByRole("link", { name: /Pre-Quiz Survey/ })).toHaveAttribute("href", "/survey?stage=pre_quiz");
    expect(screen.getByRole("link", { name: /Mid Survey/ })).toHaveAttribute("href", "/survey?stage=post_base");
    expect(screen.getByRole("link", { name: /Final Survey/ })).toHaveAttribute("href", "/survey?stage=post_variant");
  });

  it("navigates to the profile page when Profile is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    render(<DashboardPage />);

    fireEvent.click(await screen.findByText("Profile"));
    expect(mockPush).toHaveBeenCalledWith("/profile");
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: baseUser });
    mockLogout.mockResolvedValue(undefined);
    render(<DashboardPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
