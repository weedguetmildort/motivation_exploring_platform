import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import FollowupStudyPage from "../../pages/followup_study";
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

const eligible = {
  id: "1",
  email: "user@example.com",
  is_admin: false,
  survey_stage: "complete",
  followup_study_granted: true,
};

describe("FollowupStudyPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<FollowupStudyPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<FollowupStudyPage />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("renders the Quiz 2 placeholder and returns to the dashboard for an eligible user", async () => {
    mockGetMe.mockResolvedValue({ user: eligible });
    render(<FollowupStudyPage />);

    expect(await screen.findByRole("heading", { name: "Quiz 2 — Follow-Up Study" })).toBeInTheDocument();
    expect(screen.getByText(/future home of Quiz 2/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Return to dashboard" }));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("redirects an ineligible user (granted but study not complete) to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { ...eligible, survey_stage: "post_base" } });
    render(<FollowupStudyPage />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText(/future home of Quiz 2/)).not.toBeInTheDocument();
  });

  it("redirects an ineligible user (complete but not granted) to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { ...eligible, followup_study_granted: false } });
    render(<FollowupStudyPage />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
  });
});
