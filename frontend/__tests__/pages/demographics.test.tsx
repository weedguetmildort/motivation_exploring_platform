import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import DemographicsPage from "../../pages/demographics";
import { getMe, logout, invalidateMeCache } from "../../lib/auth";
import { saveMyDemographics } from "../../lib/demographics";

const mockReplace = jest.fn();
const mockPush = jest.fn();
jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
}));

jest.mock("../../lib/auth", () => ({
  getMe: jest.fn(),
  logout: jest.fn(),
  invalidateMeCache: jest.fn(),
}));

jest.mock("../../lib/demographics", () => ({
  saveMyDemographics: jest.fn(),
}));

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockInvalidateMeCache = invalidateMeCache as jest.Mock;
const mockSaveMyDemographics = saveMyDemographics as jest.Mock;

const incompleteUser = { id: "1", email: "user@example.com", is_admin: false, demographics_completed: false };

function fillRequiredFields(container: HTMLElement) {
  const selects = container.querySelectorAll("select");
  fireEvent.change(selects[0], { target: { value: "Male" } }); // gender
  fireEvent.change(selects[1], { target: { value: "Undergraduate" } }); // academic level
  fireEvent.change(selects[2], { target: { value: "first" } }); // year
  fireEvent.change(selects[3], { target: { value: "Computer Science" } }); // major

  const checkboxes = container.querySelectorAll('input[type="checkbox"]');
  fireEvent.click(checkboxes[0]); // white

  const ageInput = screen.getByPlaceholderText("e.g., 18");
  fireEvent.change(ageInput, { target: { value: "20" } });
}

describe("DemographicsPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockInvalidateMeCache.mockReset();
    mockSaveMyDemographics.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<DemographicsPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("redirects to dashboard when demographics are already completed", async () => {
    mockGetMe.mockResolvedValue({ user: { ...incompleteUser, demographics_completed: true } });
    render(<DemographicsPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<DemographicsPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("renders the demographics form", async () => {
    mockGetMe.mockResolvedValue({ user: incompleteUser });
    render(<DemographicsPage />);

    expect(await screen.findByText("Demographics")).toBeInTheDocument();
    expect(screen.getByText(/Before you continue/)).toBeInTheDocument();
  });

  it("navigates to the profile page when Profile is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: incompleteUser });
    render(<DemographicsPage />);

    fireEvent.click(await screen.findByText("Profile"));
    expect(mockPush).toHaveBeenCalledWith("/profile");
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: incompleteUser });
    mockLogout.mockResolvedValue(undefined);
    render(<DemographicsPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("shows validation errors when submitting an empty form", async () => {
    mockGetMe.mockResolvedValue({ user: incompleteUser });
    render(<DemographicsPage />);
    await screen.findByText("Demographics");

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Please fill out the required fields.");
    expect(screen.getByText("Please select your gender.")).toBeInTheDocument();
    expect(screen.getByText("Please select at least one option.")).toBeInTheDocument();
    expect(screen.getByText("Please select your academic level.")).toBeInTheDocument();
    expect(screen.getByText("Please select your year in college.")).toBeInTheDocument();
    expect(screen.getByText("Please select your major/field of study.")).toBeInTheDocument();
    expect(screen.getByText("Please enter your age.")).toBeInTheDocument();
    expect(mockSaveMyDemographics).not.toHaveBeenCalled();
  });

  it("shows a self-describe input when gender is Other", async () => {
    mockGetMe.mockResolvedValue({ user: incompleteUser });
    const { container } = render(<DemographicsPage />);
    await screen.findByText("Demographics");

    const selects = container.querySelectorAll("select");
    fireEvent.change(selects[0], { target: { value: "Other" } });

    expect(screen.getByPlaceholderText("e.g., Non-binary")).toBeInTheDocument();
  });

  it("shows and validates an other-major input when major is Other", async () => {
    mockGetMe.mockResolvedValue({ user: incompleteUser });
    const { container } = render(<DemographicsPage />);
    await screen.findByText("Demographics");

    fillRequiredFields(container);

    const selects = container.querySelectorAll("select");
    fireEvent.change(selects[3], { target: { value: "Other" } });

    expect(screen.getByPlaceholderText("e.g., Computer Science")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Please enter your major/field of study.")).toBeInTheDocument();
    expect(mockSaveMyDemographics).not.toHaveBeenCalled();
  });

  it("validates that age must be a whole number within range", async () => {
    mockGetMe.mockResolvedValue({ user: incompleteUser });
    const { container } = render(<DemographicsPage />);
    await screen.findByText("Demographics");

    fillRequiredFields(container);
    const ageInput = screen.getByPlaceholderText("e.g., 18");
    const form = container.querySelector("form")!;

    fireEvent.change(ageInput, { target: { value: "15.5" } });
    fireEvent.submit(form);
    expect(await screen.findByText("Age must be a whole number.")).toBeInTheDocument();

    fireEvent.change(ageInput, { target: { value: "200" } });
    fireEvent.submit(form);
    expect(await screen.findByText("Please enter a valid age between 16 and 120.")).toBeInTheDocument();

    expect(mockSaveMyDemographics).not.toHaveBeenCalled();
  });

  it("submits valid data and redirects to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: incompleteUser });
    mockSaveMyDemographics.mockResolvedValue({ ok: true });
    const { container } = render(<DemographicsPage />);
    await screen.findByText("Demographics");

    fillRequiredFields(container);

    const classInput = screen.getByPlaceholderText(/COP3502/);
    fireEvent.change(classInput, { target: { value: "N/A" } });

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() =>
      expect(mockSaveMyDemographics).toHaveBeenCalledWith({
        gender: "Male",
        other_gender: undefined,
        race_ethnicity: ["white"],
        academic_level: "Undergraduate",
        other_academic_level: undefined,
        year: "first",
        major: "Computer Science",
        other_major: undefined,
        class_name: "N/A",
        age: "20",
      }),
    );

    await waitFor(() => expect(mockInvalidateMeCache).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows an error message when saving demographics fails", async () => {
    mockGetMe.mockResolvedValue({ user: incompleteUser });
    mockSaveMyDemographics.mockRejectedValue(new Error("server error"));
    const { container } = render(<DemographicsPage />);
    await screen.findByText("Demographics");

    fillRequiredFields(container);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to save demographics.");
  });
});
