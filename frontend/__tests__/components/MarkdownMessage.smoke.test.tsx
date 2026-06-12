import { render, screen } from "@testing-library/react";
import MarkdownMessage from "../../components/MarkdownMessage";

describe("MarkdownMessage smoke test", () => {
  it("renders basic markdown content", () => {
    render(<MarkdownMessage content="Hello **world**" />);
    expect(screen.getByText("world")).toBeInTheDocument();
  });
});
