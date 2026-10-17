import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Playground from "../../pages/playground";
import { getMe, logout } from "../../lib/auth";
import { apiFetch } from "../../lib/fetcher";

const mockReplace = jest.fn();
const mockPush = jest.fn();
jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
}));

jest.mock("../../lib/auth", () => ({
  getMe: jest.fn(),
  logout: jest.fn(),
}));

jest.mock("../../lib/fetcher", () => ({
  apiFetch: jest.fn(),
}));

jest.mock("../../components/ChatBox", () => () => <div data-testid="chat-box" />);

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockApiFetch = apiFetch as jest.Mock;

const adminUser = { id: "1", email: "admin@example.com", is_admin: true };

const questions = [
  {
    id: "q1",
    stem: "Question One",
    subtitle: "Subtitle One",
    choices: [
      { id: "a", label: "Choice A" },
      { id: "b", label: "Choice B" },
    ],
  },
  {
    id: "q2",
    stem: "Question Two",
    choices: [
      { id: "a", label: "Choice A2" },
      { id: "b", label: "Choice B2" },
    ],
  },
];

describe("Playground", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockApiFetch.mockReset();
    mockApiFetch.mockResolvedValue([]);
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<Playground />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("redirects non-admin users to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "2", email: "user@example.com", is_admin: false } });
    render(<Playground />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("Playground")).not.toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<Playground />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("renders the playground with case selection buttons for admins", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<Playground />);

    expect(await screen.findByText("Playground")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Base Case" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Follow-up Question Case" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Double Agent Case" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Embedded Links Case" })).toBeInTheDocument();

    expect(screen.getByText(/FollowUpQuestionBox renders under the last answer/)).toBeInTheDocument();
    expect(screen.getByTestId("chat-box")).toBeInTheDocument();
  });

  it("switches case content when a different case button is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<Playground />);

    await screen.findByText("Playground");

    fireEvent.click(screen.getByRole("button", { name: "Base Case" }));
    expect(screen.getByText(/This should be the/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Double Agent Case" }));
    expect(screen.getByText(/independently respond to the user/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Embedded Links Case" }));
    expect(screen.getByText(/inline citation links embedded/)).toBeInTheDocument();
  });

  it("shows a message when no questions are available", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<Playground />);

    await screen.findByText("Playground");
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/questions/"));

    expect(await screen.findByText("No questions available. Add some in the admin panel.")).toBeInTheDocument();
    expect(screen.getByText("No questions")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("shows an error message when loading questions fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockRejectedValue(new Error("network error"));
    render(<Playground />);

    expect(await screen.findByText("Failed to load questions.")).toBeInTheDocument();
  });

  it("renders questions, allows selecting a choice, and navigates between questions", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue(questions);
    render(<Playground />);

    expect(await screen.findByRole("heading", { name: "Question One" })).toBeInTheDocument();
    expect(screen.getByText("Subtitle One")).toBeInTheDocument();
    expect(screen.getByText("Question 1 of 2")).toBeInTheDocument();

    const previousButton = screen.getByRole("button", { name: "Previous" });
    const nextButton = screen.getByRole("button", { name: "Next" });
    expect(previousButton).toBeDisabled();
    expect(nextButton).not.toBeDisabled();

    expect(screen.getByText("(none)")).toBeInTheDocument();
    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[0]);
    expect(screen.getByText("a")).toBeInTheDocument();

    fireEvent.click(nextButton);
    expect(await screen.findByRole("heading", { name: "Question Two" })).toBeInTheDocument();
    expect(screen.getByText("Question 2 of 2")).toBeInTheDocument();
    expect(nextButton).toBeDisabled();
    expect(previousButton).not.toBeDisabled();

    fireEvent.click(previousButton);
    expect(await screen.findByRole("heading", { name: "Question One" })).toBeInTheDocument();
  });

  it("navigates to the dashboard when the Dashboard button is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    render(<Playground />);

    fireEvent.click(await screen.findByText("Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockLogout.mockResolvedValue(undefined);
    render(<Playground />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
