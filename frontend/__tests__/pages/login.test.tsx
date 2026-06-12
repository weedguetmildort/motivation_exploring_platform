import { render, screen } from "@testing-library/react";
import LoginPage from "../../pages/login";

jest.mock("next/router", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

describe("LoginPage", () => {
  it("renders the login form and the disclaimer", () => {
    render(<LoginPage />);

    expect(screen.getByText("Log in", { selector: "h1" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
    expect(screen.getByText(/Emerging Technologies in Education Group/)).toBeInTheDocument();
  });
});
