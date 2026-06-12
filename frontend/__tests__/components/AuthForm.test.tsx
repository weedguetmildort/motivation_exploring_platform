import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AuthForm from "../../components/AuthForm";
import { login, signup } from "../../lib/auth";

const mockPush = jest.fn();
jest.mock("next/router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock("../../lib/auth", () => ({
  login: jest.fn(),
  signup: jest.fn(),
}));

const mockLogin = login as jest.Mock;
const mockSignup = signup as jest.Mock;

describe("AuthForm", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockLogin.mockReset();
    mockSignup.mockReset();
  });

  describe("login mode", () => {
    it("renders only email and password fields", () => {
      render(<AuthForm mode="login" />);

      expect(screen.getByText("Log in", { selector: "h1" })).toBeInTheDocument();
      expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
      expect(screen.getByPlaceholderText("••••••••")).toBeInTheDocument();
      expect(screen.queryByPlaceholderText("John")).not.toBeInTheDocument();
      expect(screen.queryByPlaceholderText("Doe")).not.toBeInTheDocument();
      expect(screen.queryByText(/I consent/)).not.toBeInTheDocument();
    });

    it("submits credentials and redirects to /dashboard on success", async () => {
      mockLogin.mockResolvedValue({ user: { id: "1" } });
      render(<AuthForm mode="login" />);

      fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
        target: { value: "ada@example.com" },
      });
      fireEvent.change(screen.getByPlaceholderText("••••••••"), {
        target: { value: "secret" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Log in" }));

      await waitFor(() => expect(mockLogin).toHaveBeenCalledWith("ada@example.com", "secret"));
      await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/dashboard"));
    });

    it("shows an error message when login fails", async () => {
      mockLogin.mockRejectedValue(new Error("Invalid credentials"));
      render(<AuthForm mode="login" />);

      fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
        target: { value: "ada@example.com" },
      });
      fireEvent.change(screen.getByPlaceholderText("••••••••"), {
        target: { value: "wrong" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Log in" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Invalid credentials");
      expect(mockPush).not.toHaveBeenCalled();
    });

    it("falls back to a generic error message when the error has no message", async () => {
      mockLogin.mockRejectedValue({});
      render(<AuthForm mode="login" />);

      fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
        target: { value: "ada@example.com" },
      });
      fireEvent.change(screen.getByPlaceholderText("••••••••"), {
        target: { value: "wrong" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Log in" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong.");
    });

    it("shows a 'Please wait…' state while the request is pending", async () => {
      let resolveLogin: (value: unknown) => void = () => {};
      mockLogin.mockReturnValue(new Promise((resolve) => { resolveLogin = resolve; }));
      render(<AuthForm mode="login" />);

      fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
        target: { value: "ada@example.com" },
      });
      fireEvent.change(screen.getByPlaceholderText("••••••••"), {
        target: { value: "secret" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Log in" }));

      const button = await screen.findByRole("button", { name: "Please wait…" });
      expect(button).toBeDisabled();

      resolveLogin({ user: { id: "1" } });
      await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/dashboard"));
    });

    it("renders a link to the signup page", () => {
      render(<AuthForm mode="login" />);
      const link = screen.getByRole("link", { name: "Sign up" });
      expect(link).toHaveAttribute("href", "/signup");
    });
  });

  describe("signup mode", () => {
    function fillRequiredFields(overrides: Partial<{ first: string; last: string; email: string; password: string }> = {}) {
      fireEvent.change(screen.getByPlaceholderText("John"), {
        target: { value: overrides.first ?? "Ada" },
      });
      fireEvent.change(screen.getByPlaceholderText("Doe"), {
        target: { value: overrides.last ?? "Lovelace" },
      });
      fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
        target: { value: overrides.email ?? "ada@example.com" },
      });
      fireEvent.change(screen.getByPlaceholderText("••••••••"), {
        target: { value: overrides.password ?? "secret123" },
      });
    }

    it("renders the signup-specific fields", () => {
      render(<AuthForm mode="signup" />);

      expect(screen.getByText("Create an account", { selector: "h1" })).toBeInTheDocument();
      expect(screen.getByPlaceholderText("John")).toBeInTheDocument();
      expect(screen.getByPlaceholderText("Doe")).toBeInTheDocument();
      expect(screen.getByText(/I consent/)).toBeInTheDocument();
    });

    it("requires first and last name", async () => {
      const { container } = render(<AuthForm mode="signup" />);
      fillRequiredFields({ first: "", last: "" });
      fireEvent.click(screen.getByRole("checkbox"));
      // bypass native HTML5 required-field validation so onSubmit runs
      fireEvent.submit(container.querySelector("form")!);

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "First name and last name are required."
      );
      expect(mockSignup).not.toHaveBeenCalled();
    });

    it("requires the password to meet the minimum length", async () => {
      render(<AuthForm mode="signup" />);
      fillRequiredFields({ password: "abc" });
      fireEvent.click(screen.getByRole("checkbox"));
      fireEvent.click(screen.getByRole("button", { name: "Sign up" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Password must be at least 6 characters long."
      );
      expect(mockSignup).not.toHaveBeenCalled();
    });

    it("shows the password hint in red once a too-short password is entered", () => {
      render(<AuthForm mode="signup" />);
      fireEvent.change(screen.getByPlaceholderText("••••••••"), {
        target: { value: "abc" },
      });
      const hint = screen.getByText(/Password must be at least 6 characters\./);
      expect(hint.className).toContain("text-red-600");
    });

    it("requires consent before submitting", async () => {
      const { container } = render(<AuthForm mode="signup" />);
      fillRequiredFields();
      // bypass native HTML5 required-field validation so onSubmit runs
      fireEvent.submit(container.querySelector("form")!);

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "You must consent to participate in the study."
      );
      expect(mockSignup).not.toHaveBeenCalled();
    });

    it("submits signup data and redirects on success", async () => {
      mockSignup.mockResolvedValue({ user: { id: "1" } });
      render(<AuthForm mode="signup" />);
      fillRequiredFields();
      fireEvent.click(screen.getByRole("checkbox"));
      fireEvent.click(screen.getByRole("button", { name: "Sign up" }));

      await waitFor(() =>
        expect(mockSignup).toHaveBeenCalledWith({
          firstName: "Ada",
          lastName: "Lovelace",
          email: "ada@example.com",
          password: "secret123",
          consent: true,
        })
      );
      await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/consent"));
    });

    it("renders a link to the login page", () => {
      render(<AuthForm mode="signup" />);
      const link = screen.getByRole("link", { name: "Log in" });
      expect(link).toHaveAttribute("href", "/login");
    });
  });
});
