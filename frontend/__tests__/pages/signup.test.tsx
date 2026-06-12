import { render, screen } from "@testing-library/react";
import SignupPage from "../../pages/signup";

jest.mock("next/router", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

describe("SignupPage", () => {
  it("renders the signup form and the disclaimer", () => {
    render(<SignupPage />);

    expect(screen.getByText("Create an account", { selector: "h1" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("John")).toBeInTheDocument();
    expect(screen.getByText(/Emerging Technologies in Education Group/)).toBeInTheDocument();
  });
});
