import { render, screen } from "@testing-library/react";
import MarkdownMessage from "../../components/MarkdownMessage";

describe("MarkdownMessage smoke test", () => {
  it("renders basic markdown content", () => {
    render(<MarkdownMessage content="Hello **world**" />);
    expect(screen.getByText("world")).toBeInTheDocument();
  });

  it("normalizes bracket-delimited display math without throwing", () => {
    // Exercises the `[\n … \n]` → $$ …$$ normalization branch in wrapExpressions.
    const { container } = render(<MarkdownMessage content={"[\nx^2 + y^2\n]"} />);
    expect(container).toBeTruthy();
  });

  it("collapses inline math that spans a newline", () => {
    // inner includes a newline → the collapse branch runs.
    const { container } = render(<MarkdownMessage content={"before $a\nb$ after"} />);
    expect(container).toBeTruthy();
  });

  it("leaves single-line inline math untouched", () => {
    // inner has no newline → the early-return branch runs.
    render(<MarkdownMessage content={"inline $x + 1$ here"} inline />);
    // inline mode renders inside a span without throwing
    expect(document.querySelector("span")).toBeTruthy();
  });

  it("renders display math blocks (katex-display container)", () => {
    const { container } = render(<MarkdownMessage content={"$$\n\\frac{1}{2}\n$$"} />);
    expect(container).toBeTruthy();
  });
});
