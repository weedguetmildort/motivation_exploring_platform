import { render, screen, fireEvent } from "@testing-library/react";
import QuestionBox, { Choice } from "../../components/QuestionBox";

const choices: Choice[] = [
  { id: "a", label: "Choice A" },
  { id: "b", label: "Choice B", description: "More info" },
  { id: "c", label: "Choice C", disabled: true },
];

describe("QuestionBox", () => {
  it("renders all choices with labels and descriptions", () => {
    render(<QuestionBox choices={choices} />);

    expect(screen.getByText("Choice A")).toBeInTheDocument();
    expect(screen.getByText("Choice B")).toBeInTheDocument();
    expect(screen.getByText("More info")).toBeInTheDocument();
    expect(screen.getByText("Choice C")).toBeInTheDocument();
  });

  it("uses defaultValue for uncontrolled initial selection", () => {
    render(<QuestionBox choices={choices} defaultValue="b" />);
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const radioB = radios.find((r) => r.value === "b")!;
    expect(radioB.checked).toBe(true);
  });

  it("calls onChange and updates selection when uncontrolled", () => {
    const onChange = jest.fn();
    render(<QuestionBox choices={choices} onChange={onChange} />);

    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const radioA = radios.find((r) => r.value === "a")!;
    fireEvent.click(radioA);

    expect(onChange).toHaveBeenCalledWith("a");
    expect(radioA.checked).toBe(true);
  });

  it("respects a controlled value", () => {
    const onChange = jest.fn();
    render(<QuestionBox choices={choices} value="a" onChange={onChange} />);

    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.find((r) => r.value === "a")!.checked).toBe(true);

    fireEvent.click(radios.find((r) => r.value === "b")!);
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("disables the radio input for disabled choices", () => {
    render(<QuestionBox choices={choices} />);
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const radioC = radios.find((r) => r.value === "c")!;
    expect(radioC.disabled).toBe(true);
  });

  it("uses the provided ariaLabel for the radio group", () => {
    render(<QuestionBox choices={choices} ariaLabel="Custom label" />);
    expect(screen.getByRole("radiogroup", { name: "Custom label" })).toBeInTheDocument();
  });

  it("applies horizontal layout classes when orientation is horizontal", () => {
    const { container } = render(<QuestionBox choices={choices} orientation="horizontal" />);
    expect(container.querySelector(".flex.flex-wrap.gap-3")).not.toBeNull();
  });
});
