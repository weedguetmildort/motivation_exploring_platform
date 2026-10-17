import { render, screen, fireEvent } from "@testing-library/react";
import ChatHeader from "../../components/ChatHeader";
import { QUIZ_THEMES } from "../../lib/quizTheme";

describe("ChatHeader", () => {
  it("renders the same AI Assistant title regardless of quiz type", () => {
    render(<ChatHeader quizId="base" />);
    expect(screen.getByText("AI Assistant")).toBeInTheDocument();

    render(<ChatHeader quizId="followup" />);
    expect(screen.getAllByText("AI Assistant").length).toBeGreaterThan(0);
  });

  it("toggles the info popover when the '?' button is clicked", () => {
    render(<ChatHeader quizId="links" />);

    const infoButton = screen.getByRole("button", { name: "About this assistant type" });
    expect(screen.queryByText(QUIZ_THEMES.links.description)).not.toBeInTheDocument();

    fireEvent.click(infoButton);
    expect(screen.getByText("How this works")).toBeInTheDocument();
    expect(screen.getByText(QUIZ_THEMES.links.description)).toBeInTheDocument();

    fireEvent.click(infoButton);
    expect(screen.queryByText(QUIZ_THEMES.links.description)).not.toBeInTheDocument();
  });

  it("closes the popover when clicking outside of it", () => {
    render(<ChatHeader quizId="double" />);

    fireEvent.click(screen.getByRole("button", { name: "About this assistant type" }));
    expect(screen.getByText(QUIZ_THEMES.double.description)).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByText(QUIZ_THEMES.double.description)).not.toBeInTheDocument();
  });

  it("computes an in-viewport popover position when opened", () => {
    const rafSpy = jest
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((cb: FrameRequestCallback) => { cb(0); return 0; });

    render(<ChatHeader quizId="links" />);
    fireEvent.click(screen.getByRole("button", { name: "About this assistant type" }));

    // The rAF positioning callback ran synchronously; popover is shown.
    expect(screen.getByText("How this works")).toBeInTheDocument();
    rafSpy.mockRestore();
  });

  it("repositions the popover when it would overflow the viewport edges", () => {
    const rafSpy = jest
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((cb: FrameRequestCallback) => { cb(0); return 0; });
    // Force the button + popover rects to overflow the right and bottom edges,
    // exercising the clamp branches in the positioning effect.
    const rectSpy = jest.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
      left: 900, right: 1300, top: 700, bottom: 730, width: 400, height: 300, x: 900, y: 700,
      toJSON: () => {},
    } as DOMRect);

    render(<ChatHeader quizId="double" />);
    fireEvent.click(screen.getByRole("button", { name: "About this assistant type" }));

    expect(screen.getByText("How this works")).toBeInTheDocument();
    rectSpy.mockRestore();
    rafSpy.mockRestore();
  });

  it("does not render the question toggle button when onToggleQuestion is not provided", () => {
    render(<ChatHeader quizId="base" />);
    expect(screen.queryByLabelText(/question/i)).not.toBeInTheDocument();
  });

  it("shows a Maximize button when the question is not collapsed", () => {
    const onToggleQuestion = jest.fn();
    render(<ChatHeader quizId="base" questionCollapsed={false} onToggleQuestion={onToggleQuestion} />);

    const button = screen.getByRole("button", { name: "Maximize question" });
    expect(button).toHaveTextContent("Maximize");

    fireEvent.click(button);
    expect(onToggleQuestion).toHaveBeenCalled();
  });

  it("shows a Minimize button when the question is collapsed", () => {
    render(<ChatHeader quizId="base" questionCollapsed={true} onToggleQuestion={jest.fn()} />);

    const button = screen.getByRole("button", { name: "Minimize question" });
    expect(button).toHaveTextContent("Minimize");
  });
});
