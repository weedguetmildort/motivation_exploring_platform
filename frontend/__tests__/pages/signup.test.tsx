import { render, screen } from "@testing-library/react";
import SignupPage from "../../pages/signup";

jest.mock("next/router", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));

jest.mock("../../lib/auth", () => ({
  login:  jest.fn(),
  signup: jest.fn(),
  getMe:  jest.fn().mockRejectedValue(new Error("not authenticated")),
}));

describe("SignupPage", () => {
  it("renders the signup form and the disclaimer", async () => {
    render(<SignupPage />);

    expect(await screen.findByText("Create an account", { selector: "h1" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("John")).toBeInTheDocument();
    expect(screen.getByText(/Emerging Technologies in Education Group/)).toBeInTheDocument();
  });
});
