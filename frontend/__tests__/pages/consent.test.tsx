import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ConsentPage from "../../pages/consent";
import { getMe, invalidateMeCache, logout, recordConsentAgreement } from "../../lib/auth";

const mockReplace = jest.fn();
const mockPush = jest.fn();
jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
}));

jest.mock("../../lib/auth", () => ({
  getMe: jest.fn(),
  logout: jest.fn(),
  invalidateMeCache: jest.fn(),
  recordConsentAgreement: jest.fn(),
}));

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockInvalidateMeCache = invalidateMeCache as jest.Mock;
const mockRecordConsentAgreement = recordConsentAgreement as jest.Mock;

const authedUser = { id: "1", email: "user@example.com", is_admin: false };

describe("ConsentPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockInvalidateMeCache.mockReset();
    mockRecordConsentAgreement.mockReset();
    mockRecordConsentAgreement.mockResolvedValue({ ok: true });
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<ConsentPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<ConsentPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("renders the consent form once authenticated", async () => {
    mockGetMe.mockResolvedValue({ user: authedUser });
    render(<ConsentPage />);

    expect(await screen.findByText("Research Consent Form")).toBeInTheDocument();
    expect(
      screen.getByText(/Understanding Overreliance towards AI in Educational Settings/)
    ).toBeInTheDocument();
    expect(screen.getByText(/Neha Rani \(Faculty in CISE\)/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "neharani@ufl.edu" })
    ).toHaveAttribute("href", "mailto:neharani@ufl.edu");
  });

  it("renders all required information sections", async () => {
    mockGetMe.mockResolvedValue({ user: authedUser });
    render(<ConsentPage />);

    await screen.findByText("Research Consent Form");

    expect(screen.getByText("Purpose of the Study")).toBeInTheDocument();
    expect(screen.getByText("What will you be asked to do")).toBeInTheDocument();
    expect(screen.getByText("Time Required")).toBeInTheDocument();
    expect(screen.getByText("Research Benefits")).toBeInTheDocument();
    expect(screen.getByText("Research Risks")).toBeInTheDocument();
    expect(screen.getByText("Statement of Confidentiality")).toBeInTheDocument();
    expect(
      screen.getByText("Who to contact if you have questions")
    ).toBeInTheDocument();
    expect(screen.getByText("Voluntary Participation")).toBeInTheDocument();
    expect(screen.getByText(/about 45 minutes/)).toBeInTheDocument();
    expect(screen.getByText(/352-273-9600/)).toBeInTheDocument();
  });

  it("renders the agree and decline buttons", async () => {
    mockGetMe.mockResolvedValue({ user: authedUser });
    render(<ConsentPage />);

    expect(await screen.findByRole("button", { name: "I agree to participate" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "I do not wish to participate" })).toBeInTheDocument();
  });

  it("saves the displayed consent text and navigates to the dashboard when the user agrees", async () => {
    mockGetMe.mockResolvedValue({ user: authedUser });
    render(<ConsentPage />);

    const agreeButton = await screen.findByRole("button", { name: "I agree to participate" });
    fireEvent.click(agreeButton);

    await waitFor(() => expect(mockRecordConsentAgreement).toHaveBeenCalled());
    const savedText = mockRecordConsentAgreement.mock.calls[0][0] as string;
    expect(savedText).toContain("Research Consent Form");
    expect(savedText).toContain("Purpose of the Study");
    expect(savedText).toContain("Voluntary Participation");
    // The instructions/buttons box itself should not be part of the saved snapshot.
    expect(savedText).not.toContain("I agree to participate");

    expect(mockInvalidateMeCache).toHaveBeenCalled();
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/dashboard"));
    expect(mockLogout).not.toHaveBeenCalled();
  });

  it("shows an error and does not navigate when saving consent fails", async () => {
    mockGetMe.mockResolvedValue({ user: authedUser });
    mockRecordConsentAgreement.mockRejectedValue(new Error("network error"));
    render(<ConsentPage />);

    const agreeButton = await screen.findByRole("button", { name: "I agree to participate" });
    fireEvent.click(agreeButton);

    expect(
      await screen.findByText("Failed to save your consent. Please try again.")
    ).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalledWith("/dashboard");
    expect(agreeButton).not.toBeDisabled();
  });

  it("logs out and redirects to login when the user declines", async () => {
    mockGetMe.mockResolvedValue({ user: authedUser });
    mockLogout.mockResolvedValue(undefined);
    render(<ConsentPage />);

    const declineButton = await screen.findByRole("button", { name: "I do not wish to participate" });
    fireEvent.click(declineButton);

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("redirects to login even if logout fails when the user declines", async () => {
    mockGetMe.mockResolvedValue({ user: authedUser });
    mockLogout.mockRejectedValue(new Error("network error"));
    render(<ConsentPage />);

    const declineButton = await screen.findByRole("button", { name: "I do not wish to participate" });
    fireEvent.click(declineButton);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
