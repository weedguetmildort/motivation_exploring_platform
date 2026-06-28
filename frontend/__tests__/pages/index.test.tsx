import { render, screen } from "@testing-library/react";
import Landing from "../../pages/index";

describe("Landing page", () => {
  it("renders the heading, sign up / log in links, and the disclaimer", () => {
    render(<Landing />);

    expect(screen.getByText("AI Problem-Solving Research Study")).toBeInTheDocument();
    expect(screen.getByText("Sign up or log in to start.")).toBeInTheDocument();

    const signupLink = screen.getByRole("link", { name: "Sign up" });
    expect(signupLink).toHaveAttribute("href", "/signup");

    const loginLink = screen.getByRole("link", { name: "Log in" });
    expect(loginLink).toHaveAttribute("href", "/login");

    expect(screen.getByText(/Emerging Technologies in Education Group/)).toBeInTheDocument();
  });
});
