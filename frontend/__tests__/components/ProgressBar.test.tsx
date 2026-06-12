import { render, screen, fireEvent } from "@testing-library/react";
import ProgressBar from "../../components/ProgressBar";
import type { User } from "../../lib/auth";

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "1",
    email: "user@example.com",
    is_admin: false,
    ...overrides,
  };
}

describe("ProgressBar", () => {
  it("renders the study progress header and completion count", () => {
    render(<ProgressBar user={makeUser()} />);
    expect(screen.getByText("Study Progress")).toBeInTheDocument();
    expect(screen.getByText("0 of 5 completed")).toBeInTheDocument();
  });

  it("counts completed steps", () => {
    render(
      <ProgressBar
        user={makeUser({ survey_pre_base_completed: true, quiz_base_completed: true })}
      />
    );
    expect(screen.getByText("2 of 5 completed")).toBeInTheDocument();
  });

  it("renders all step labels", () => {
    render(<ProgressBar user={makeUser()} />);
    expect(screen.getAllByText("Pre-Quiz Survey").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Base Quiz").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Mid Survey").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Variant Quiz").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Final Survey").length).toBeGreaterThan(0);
  });

  it("uses the variant-specific label when assigned_var is set", () => {
    render(<ProgressBar user={makeUser({ assigned_var: "double" })} />);
    expect(screen.getAllByText("Dual Agent Quiz").length).toBeGreaterThan(0);
  });

  it("does not show a collapse toggle by default and content is visible", () => {
    render(<ProgressBar user={makeUser()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getAllByText("Pre-Quiz Survey").length).toBeGreaterThan(0);
  });

  it("toggles content visibility when collapsible", () => {
    render(<ProgressBar user={makeUser()} collapsible />);

    const toggle = screen.getByRole("button", { name: "Collapse progress" });
    fireEvent.click(toggle);

    expect(screen.queryByText("Pre-Quiz Survey")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand progress" })).toBeInTheDocument();
  });

  it("marks the active step", () => {
    render(<ProgressBar user={makeUser()} activeStep="quiz_base" />);
    const labels = screen.getAllByText("Base Quiz");
    expect(labels[0].className).toContain("text-accent-600");
  });

  it("marks completed steps differently from incomplete steps", () => {
    render(<ProgressBar user={makeUser({ survey_pre_base_completed: true })} />);
    const completedLabels = screen.getAllByText("Pre-Quiz Survey");
    const incompleteLabels = screen.getAllByText("Base Quiz");
    expect(completedLabels[0].className).toContain("text-accent-600");
    expect(incompleteLabels[0].className).toContain("text-gray-400");
  });
});
