import { render, screen, waitFor } from "@testing-library/react";
import Landing from "../../pages/index";

const mockReplace = jest.fn();
jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

jest.mock("../../lib/auth", () => ({
  getMe: jest.fn(),
}));

import { getMe } from "../../lib/auth";
const mockGetMe = getMe as jest.Mock;

describe("Landing page", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockGetMe.mockReset();
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
  });

  it("renders the heading, sign up / log in links, and the disclaimer", async () => {
    render(<Landing />);

    expect(await screen.findByText("AI Problem-Solving Research Study")).toBeInTheDocument();
    expect(screen.getByText("Sign up or log in to start.")).toBeInTheDocument();

    const signupLink = screen.getByRole("link", { name: "Sign up" });
    expect(signupLink).toHaveAttribute("href", "/signup");

    const loginLink = screen.getByRole("link", { name: "Log in" });
    expect(loginLink).toHaveAttribute("href", "/login");

    expect(screen.getByText(/Emerging Technologies in Education Group/)).toBeInTheDocument();
  });

  it("redirects to /dashboard when a session already exists", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "1" } });
    render(<Landing />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("AI Problem-Solving Research Study")).not.toBeInTheDocument();
  });
});
