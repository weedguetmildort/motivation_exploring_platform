import { render, screen, fireEvent } from "@testing-library/react";
import MentionSuggestions from "../../components/MentionSuggestions";

describe("MentionSuggestions", () => {
  it("renders nothing when not visible", () => {
    const { container } = render(
      <MentionSuggestions visible={false} agents={["agenta"]} selectedIndex={0} onSelect={jest.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when there are no agents", () => {
    const { container } = render(
      <MentionSuggestions visible={true} agents={[]} selectedIndex={0} onSelect={jest.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a button per agent and highlights the selected index", () => {
    render(
      <MentionSuggestions visible={true} agents={["agenta", "agentb"]} selectedIndex={1} onSelect={jest.fn()} />
    );

    const buttonA = screen.getByText("@agenta");
    const buttonB = screen.getByText("@agentb");
    expect(buttonA).toBeInTheDocument();
    expect(buttonB.className).toContain("bg-accent-500");
    expect(buttonA.className).not.toContain("bg-accent-500");
  });

  it("calls onSelect with the agent name when clicked", () => {
    const onSelect = jest.fn();
    render(
      <MentionSuggestions visible={true} agents={["agenta", "agentb"]} selectedIndex={0} onSelect={onSelect} />
    );

    fireEvent.click(screen.getByText("@agentb"));
    expect(onSelect).toHaveBeenCalledWith("agentb");
  });
});
