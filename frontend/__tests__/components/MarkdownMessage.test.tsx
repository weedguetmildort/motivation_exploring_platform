import { render, screen, fireEvent } from "@testing-library/react";
import MarkdownMessage from "../../components/MarkdownMessage";

describe("MarkdownMessage", () => {
  it("renders bold and italic text", () => {
    const { container } = render(<MarkdownMessage content="Hello **bold** and *italic*" />);
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelector("em")?.textContent).toBe("italic");
  });

  it("renders links opening in a new tab, styled for light backgrounds", () => {
    render(<MarkdownMessage content="[Example](https://example.com)" />);
    const link = screen.getByRole("link", { name: "Example" });
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
    expect(link.className).toContain("text-blue-600");
  });

  it("styles links differently in dark mode", () => {
    render(<MarkdownMessage content="[Example](https://example.com)" dark />);
    const link = screen.getByRole("link", { name: "Example" });
    expect(link.className).toContain("text-white");
  });

  it("renders a GFM table with styled headers and cells", () => {
    const content = "| A | B |\n| --- | --- |\n| 1 | 2 |";
    const { container } = render(<MarkdownMessage content={content} />);

    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(table?.parentElement?.className).toContain("overflow-x-auto");

    const th = container.querySelector("th");
    expect(th?.textContent).toBe("A");
    expect(th?.className).toContain("border-gray-300");

    const td = container.querySelector("td");
    expect(td?.textContent).toBe("1");
  });

  it("renders an unordered list with custom classes", () => {
    const { container } = render(<MarkdownMessage content={"- one\n- two"} />);
    const ul = container.querySelector("ul");
    expect(ul?.className).toContain("list-disc");
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0].className).toContain("leading-normal");
    expect(items[0].textContent).toBe("one");
  });

  it("renders an ordered list with custom classes", () => {
    const { container } = render(<MarkdownMessage content={"1. one\n2. two"} />);
    const ol = container.querySelector("ol");
    expect(ol?.className).toContain("list-decimal");
    expect(container.querySelectorAll("li")).toHaveLength(2);
  });

  it("renders a horizontal rule with custom classes", () => {
    const { container } = render(<MarkdownMessage content={"above\n\n---\n\nbelow"} />);
    const hr = container.querySelector("hr");
    expect(hr?.className).toContain("border-gray-300");
  });

  it("renders a markdown blockquote with custom classes", () => {
    const { container } = render(<MarkdownMessage content="> a quoted line" />);
    const blockquote = container.querySelector("blockquote");
    expect(blockquote?.className).toContain("inline-block");
    expect(blockquote?.textContent).toContain("a quoted line");
  });

  it("renders fenced code blocks inside <pre><code>", () => {
    const { container } = render(<MarkdownMessage content={"```js\nconst x = 1;\n```"} />);
    const pre = container.querySelector("pre");
    const code = container.querySelector("pre code");
    expect(pre?.className).toContain("bg-gray-100");
    expect(code?.textContent).toContain("const x = 1;");
    expect(code?.className).toContain("break-all");
  });

  it("renders inline code with custom classes", () => {
    const { container } = render(<MarkdownMessage content="Use `npm install`" />);
    const code = container.querySelector("code");
    expect(code?.textContent).toBe("npm install");
    expect(code?.className).toContain("break-all");
  });

  it("converts \\(...\\) and \\[...\\] into KaTeX math", () => {
    const { container } = render(<MarkdownMessage content={"Inline \\(E=mc^2\\) and block \\[a^2+b^2=c^2\\]"} />);
    expect(container.querySelectorAll(".katex").length).toBeGreaterThan(0);
  });

  it("wraps a bare \\begin{align}...\\end{align} block in display math", () => {
    const content = "\\begin{align} a &= b \\\\ c &= d \\end{align}";
    const { container } = render(<MarkdownMessage content={content} />);
    expect(container.querySelector(".katex-display")).not.toBeNull();
  });

  it("converts a \\begin{quote}...\\end{quote} block into a blockquote", () => {
    const content = "\\begin{quote}\nHello there\nGeneral Kenobi\n\\end{quote}";
    const { container } = render(<MarkdownMessage content={content} />);
    const blockquote = container.querySelector("blockquote");
    expect(blockquote?.textContent).toContain("Hello there");
    expect(blockquote?.textContent).toContain("General Kenobi");
  });

  it("converts a \\begin{verse}...\\end{verse} block into a blockquote with line breaks", () => {
    const content = "\\begin{verse}\nLine one \\\\\nLine two\n\\end{verse}";
    const { container } = render(<MarkdownMessage content={content} />);
    const blockquote = container.querySelector("blockquote");
    expect(blockquote).not.toBeNull();
    expect(blockquote?.querySelector("br")).not.toBeNull();
  });

  it("converts a single-level \\begin{itemize} block into a markdown list", () => {
    const content = "\\begin{itemize}\n\\item First item\n\\item Second item\n\\end{itemize}";
    const { container } = render(<MarkdownMessage content={content} />);
    const items = container.querySelectorAll("ul li");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe("First item");
    expect(items[1].textContent).toBe("Second item");
  });

  it("converts a single-level \\begin{enumerate} block into an ordered markdown list", () => {
    const content = "\\begin{enumerate}\n\\item First\n\\item Second\n\\end{enumerate}";
    const { container } = render(<MarkdownMessage content={content} />);
    const items = container.querySelectorAll("ol li");
    expect(items).toHaveLength(2);
  });

  it("converts a \\begin{tabular} block into a markdown table", () => {
    const content = "\\begin{tabular}{cc}\nA & B \\\\\n1 & 2 \\\\\n\\end{tabular}";
    const { container } = render(<MarkdownMessage content={content} />);
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(container.querySelector("th")?.textContent).toBe("A");
    expect(container.querySelector("td")?.textContent).toBe("1");
  });

  it("unwraps a fenced code block whose content is LaTeX display math", () => {
    const content = "```\n$$\n\\begin{align}\na &= b\n\\end{align}\n$$\n```";
    const { container } = render(<MarkdownMessage content={content} />);
    expect(container.querySelector("pre")).toBeNull();
    expect(container.querySelector(".katex-display")).not.toBeNull();
  });

  it("renders inline mode content within a span without paragraph wrappers", () => {
    const { container } = render(<MarkdownMessage content="just text" inline />);
    expect(container.querySelector("span")).not.toBeNull();
    expect(container.querySelector("p")).toBeNull();
    expect(container.textContent).toBe("just text");
  });

  it("calls onLinkClick with the href when a link is clicked", () => {
    const onLinkClick = jest.fn();
    render(<MarkdownMessage content="[Example](https://example.com)" onLinkClick={onLinkClick} />);

    fireEvent.click(screen.getByRole("link", { name: "Example" }));

    expect(onLinkClick).toHaveBeenCalledWith("https://example.com");
  });

  it("calls onLinkClick in dark mode too", () => {
    const onLinkClick = jest.fn();
    render(<MarkdownMessage content="[Example](https://example.com)" dark onLinkClick={onLinkClick} />);

    fireEvent.click(screen.getByRole("link", { name: "Example" }));

    expect(onLinkClick).toHaveBeenCalledWith("https://example.com");
  });

  it("calls onLinkClick in inline mode too", () => {
    const onLinkClick = jest.fn();
    render(<MarkdownMessage content="[Example](https://example.com)" inline onLinkClick={onLinkClick} />);

    fireEvent.click(screen.getByRole("link", { name: "Example" }));

    expect(onLinkClick).toHaveBeenCalledWith("https://example.com");
  });

  it("does not throw when a link is clicked and no onLinkClick is provided", () => {
    render(<MarkdownMessage content="[Example](https://example.com)" />);
    expect(() => fireEvent.click(screen.getByRole("link", { name: "Example" }))).not.toThrow();
  });
});
