import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import DashboardPage from "../../pages/dashboard";
import { getMe, logout } from "../../lib/auth";

jest.mock("../../components/DashboardStudyAccess", () => ({ __esModule: true, default: ({ user }: { user: { is_admin: boolean } }) => user.is_admin ? <section aria-label="Admin study workspace" /> : null }));

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

  it.each([{ consent: false }, { consent: true, consent_declined_at: "2026-10-15T12:00:00Z" }])("requires fresh Study 2 consent after a decline: %j", async consent => {
    mockGetMe.mockResolvedValue({ user: { ...baseUser, study_id: "study-2", consent_agreed_at: "2026-10-14T12:00:00Z", ...consent } });
    render(<DashboardPage />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/consent"));
    expect(screen.queryByText("Study Complete — thank you for participating!")).not.toBeInTheDocument();
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

  it("shows the follow-up study card only when granted AND the study is complete", async () => {
    mockGetMe.mockResolvedValue({
      user: { ...completeUser, survey_stage: "complete", followup_study_granted: true },
    });
    render(<DashboardPage />);

    expect(await screen.findByRole("heading", { name: "Follow-up study" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(mockPush).toHaveBeenCalledWith("/followup_study");
  });

  it("hides the follow-up card when granted but the study is not complete", async () => {
    mockGetMe.mockResolvedValue({ user: { ...baseUser, followup_study_granted: true } });
    render(<DashboardPage />);

    await screen.findByText("Next Step"); // incomplete → hero renders, dashboard loaded
    expect(screen.queryByRole("heading", { name: "Follow-up study" })).not.toBeInTheDocument();
  });

  it("hides the follow-up card when complete but not granted", async () => {
    mockGetMe.mockResolvedValue({
      user: { ...completeUser, survey_stage: "complete", followup_study_granted: false },
    });
    render(<DashboardPage />);

    await screen.findByText("Study Complete — thank you for participating!");
    expect(screen.queryByRole("heading", { name: "Follow-up study" })).not.toBeInTheDocument();
  });

  it("renders the admin section with tool, quiz, and survey links for admins", async () => {
    mockGetMe.mockResolvedValue({ user: { ...baseUser, is_admin: true } });
    render(<DashboardPage />);

    expect(await screen.findByText("Admin")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: /Chat/ })).toHaveAttribute("href", "/chat?study=study-1");
    expect(screen.getByRole("link", { name: /Playground/ })).toHaveAttribute("href", "/playground?study=study-1");
    expect(screen.getByRole("link", { name: /Admin Panel/ })).toHaveAttribute("href", "/admin?study=study-1");

    expect(screen.getByRole("link", { name: /Base Quiz/ })).toHaveAttribute("href", "/quiz/base?study=study-1");
    expect(screen.getByRole("link", { name: /Follow-Up Questions/ })).toHaveAttribute("href", "/quiz/followup?study=study-1");
    expect(screen.getByRole("link", { name: /Dual Agent/ })).toHaveAttribute("href", "/quiz/double?study=study-1");
    expect(screen.getByRole("link", { name: /Embedded Links/ })).toHaveAttribute("href", "/quiz/links?study=study-1");

    expect(screen.getByRole("link", { name: /Pre-Quiz Survey/ })).toHaveAttribute("href", "/survey?stage=pre_quiz&study=study-1");
    expect(screen.getByRole("link", { name: /Mid Survey/ })).toHaveAttribute("href", "/survey?stage=post_base&study=study-1");
    expect(screen.getByRole("link", { name: /Final Survey/ })).toHaveAttribute("href", "/survey?stage=post_variant&study=study-1");
  });

  it("shows admins every variant quiz even when their own Study 1 preview has one variant", async () => {
    mockGetMe.mockResolvedValue({ user: { ...baseUser, is_admin: true, assigned_var: "double",
      step_order: ["survey:pre_quiz", "quiz:base", "survey:post_base", "quiz:double", "survey:post_variant"], completed_steps: [] } });
    render(<DashboardPage />);

    expect(await screen.findByText("Admin")).toBeInTheDocument();
    for (const [name, href] of [[/Base Quiz/, "/quiz/base"], [/Follow-Up Questions/, "/quiz/followup"],
      [/Dual Agent/, "/quiz/double"], [/Embedded Links/, "/quiz/links"]] as const) {
      expect(screen.getByRole("link", { name })).toHaveAttribute("href", `${href}?study=study-1`);
    }
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
