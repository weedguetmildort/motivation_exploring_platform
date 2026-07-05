import { render, screen } from "@testing-library/react";
import LoginPage from "../../pages/login";

jest.mock("next/router", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));

jest.mock("../../lib/auth", () => ({
  login:  jest.fn(),
  signup: jest.fn(),
  getMe:  jest.fn().mockRejectedValue(new Error("not authenticated")),
}));

describe("LoginPage", () => {
  it("renders the login form and the disclaimer", async () => {
    render(<LoginPage />);

    expect(await screen.findByText("Log in", { selector: "h1" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
    expect(screen.getByText(/Emerging Technologies in Education Group/)).toBeInTheDocument();
  });
});
