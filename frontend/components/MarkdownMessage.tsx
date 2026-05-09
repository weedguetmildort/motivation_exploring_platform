import React, { useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

// Convert the body of a \begin{itemize} or \begin{enumerate} block to a
// markdown list. Each \item becomes a bullet/numbered entry; continuation
// lines (including already-converted nested lists) are indented by 2 spaces.
function convertListBody(body: string, ordered: boolean): string {
  const parts = body.split(/\\item\b\s*/);
  let counter = 0;
  return parts
    .slice(1) // ignore preamble before first \item
    .map((rawItem) => {
      const trimmedItem = rawItem.trimEnd();
      if (!trimmedItem.trim()) return "";
      counter++;
      const bullet = ordered ? `${counter}.` : `-`;
      // Normalize each line: trim leading whitespace, drop blank continuation lines
      const lines = trimmedItem
        .split("\n")
        .map((l) => l.trim())
        .filter((l, i) => i === 0 || l.length > 0);
      const first = lines[0];
      if (!first) return "";
      const rest = lines.slice(1).map((l) => `  ${l}`).join("\n");
      return rest ? `${bullet} ${first}\n${rest}` : `${bullet} ${first}`;
    })
    .filter((s) => s.length > 0)
    .join("\n");
}

function wrapExpressions(text: string): string {
  // Step 0: Unwrap fenced code blocks whose content is LaTeX so the inner
  // content gets processed as math/text instead of shown as raw code.
  text = text.replace(/```[^\n]*\n([\s\S]+?)```/g, (match, inner) => {
    const trimmed = inner.trim();
    if (
      /\$\$[\s\S]+?\$\$/.test(trimmed) ||
      /\\begin\{(?:align|equation|gather|multline|tabular|quote|verse|itemize|enumerate)/.test(trimmed)
    ) {
      return "\n\n" + trimmed + "\n\n";
    }
    return match;
  });

  // Step 1: Normalize \(...\) and \[...\] → $...$ / $$...$$ so all math uses one delimiter.
  // \[...\] is display math, must produce $$ so block environments like \begin{array} render correctly.
  text = text.replace(/(?:^|\n)\[\n([\s\S]+?)\n\](?:\n|$)/g,
    (_, inner) => `\n$$\n${inner.trim()}\n$$\n`);
  text = text.replace(/\\\(([\s\S]+?)\\\)/g, (_, inner) => `$${inner.trim()}$`);
  text = text.replace(/\\\[([\s\S]+?)\\\]/g, (_, inner) => `$$\n${inner.trim()}\n$$`);

  // Step 2: Collapse inline $...$ that spans a single newline.
  // remark-math only parses single-line inline math. The AI sometimes wraps a
  // formula onto the next line (e.g. newline before the closing $). This must
  // run before step 3 so pipe-escaping sees the complete formula on one line.
  // (?<!\$) on both anchors prevents starting a match at the second $ of $$,
  // which would corrupt display math blocks produced in step 1.
  text = text.replace(/(?<!\$)\$(?!\$)((?:[^\n$]|\n(?!\n)){1,500})(?<!\$)\$(?!\$)/g, (match, inner) => {
    if (!inner.includes("\n")) return match;
    return `$${inner.replace(/\s*\n\s*/g, " ")}$`;
  });

  // Step 3: Escape | inside $...$ so GFM table rows aren't split on math operators
  // like P(A|B). After step 2 all formulas are on a single line, so [^$\n]+ is safe.
  // Same (?<!\$) guards to avoid touching $$ display math blocks.
  text = text.replace(/(?<!\$)\$(?!\$)([^$\n]+)(?<!\$)\$(?!\$)/g, (match, inner) =>
    inner.includes("|") ? `$${inner.replace(/\|/g, "\\vert ")}$` : match
  );

  // Step 4: Wrap bare display math environments in $$ — must run after steps 2-3
  // so those steps cannot corrupt the newly introduced $$ blocks.
  // Uses explicit alternation instead of backreferences to avoid backtracking
  // issues when the environment name contains an optional character (align vs align*).
  // \n\n padding ensures remark-math sees the $$ block as a paragraph-level element.
  text = text.replace(
    /(?<!\$)(\\begin\{align\*?\}[\s\S]+?\\end\{align\*?\}|\\begin\{gather\*?\}[\s\S]+?\\end\{gather\*?\}|\\begin\{equation\*?\}[\s\S]+?\\end\{equation\*?\}|\\begin\{multline\*?\}[\s\S]+?\\end\{multline\*?\})(?!\$)/g,
    (match) => `\n\n$$\n${match.trim()}\n$$\n\n`
  );

  // Step 5: Convert LaTeX text environments to Markdown equivalents.

  // \begin{quote}...\end{quote} → blockquote
  text = text.replace(/\\begin\{quote\}([\s\S]+?)\\end\{quote\}/g, (_, inner) => {
    const lines = inner.trim().split("\n").map((l: string) => `> ${l.trim()}`);
    return "\n\n" + lines.join("\n") + "\n\n";
  });

  // \begin{verse}...\end{verse} → blockquote; \\ = forced line break (two trailing spaces)
  text = text.replace(/\\begin\{verse\}([\s\S]+?)\\end\{verse\}/g, (_, inner) => {
    const lines = inner.trim().split("\n").map((l: string) =>
      "> " + l.replace(/\\\\$/, "").trim()
    );
    return "\n\n" + lines.join("  \n") + "\n\n";
  });

  // Step 6: Convert \begin{itemize} and \begin{enumerate} environments to
  // Markdown lists. Processes iteratively so nested environments (same or
  // mixed type) are converted innermost-first: the lazy [\s\S]+? always
  // matches the nearest \end{...}, so each pass converts the innermost
  // remaining environment until none are left.
  {
    let prev = "";
    while (prev !== text) {
      prev = text;
      text = text.replace(
        /\\begin\{(itemize|enumerate)\}([\s\S]+?)\\end\{\1\}/g,
        (_, env, body) => convertListBody(body, env === "enumerate")
      );
    }
  }

  // \begin{tabular}{cols}...\end{tabular} → GFM Markdown table.
  // Strips \hline, splits rows on \\, splits cells on &.
  text = text.replace(/\\begin\{tabular\}\{[^}]*\}([\s\S]+?)\\end\{tabular\}/g, (_, body) => {
    const rows = body
      .replace(/\\hline/g, "")
      .trim()
      .split(/\\\\\s*\n?/)
      .map((r: string) => r.trim())
      .filter((r: string) => r.length > 0);

    if (rows.length === 0) return "";

    const parseRow = (row: string) => row.split("&").map((c: string) => c.trim());
    const headers = parseRow(rows[0]);
    const separator = headers.map(() => "---");
    const dataRows = rows.slice(1).map(parseRow);
    const toMdRow = (cells: string[]) => `| ${cells.join(" | ")} |`;

    return (
      "\n\n" +
      toMdRow(headers) + "\n" +
      toMdRow(separator) + "\n" +
      dataRows.map(toMdRow).join("\n") +
      "\n\n"
    );
  });

  return text;
}

const schema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    // allow KaTeX HTML output attributes
    span: [
      ...(defaultSchema.attributes?.span || []),
      ["className"],
      ["style"],
      ["aria-hidden"],
    ],
    div: [
      ...(defaultSchema.attributes?.div || []),
      ["className"],
      ["style"],
    ],
  },
};

function makeComponents(dark: boolean) {
  return {
    a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className={dark ? "text-white underline opacity-90 hover:opacity-100" : "text-blue-600 underline hover:text-blue-800"}
      >
        {children}
      </a>
    ),
    div: ({ className, children, style }: { className?: string; children?: React.ReactNode; style?: React.CSSProperties }) => {
      if (className?.includes("katex-display")) {
        return (
          <div
            className={`${className} relative border-2 rounded px-3 py-2 my-2 overflow-x-auto max-w-full ${dark ? "border-white/60" : "border-gray-800"}`}
            style={style}
          >
            {children}
          </div>
        );
      }
      return <div className={className} style={style}>{children}</div>;
    },
    table: ({ children }: { children?: React.ReactNode }) => (
      <div className="overflow-x-auto my-3">
        <table className="w-full border-collapse text-sm">{children}</table>
      </div>
    ),
    th: ({ children }: { children?: React.ReactNode }) => (
      <th className={`border px-3 py-2 text-left font-semibold whitespace-nowrap ${dark ? "border-white/40 bg-white/10" : "border-gray-300 bg-gray-50"}`}>
        {children}
      </th>
    ),
    td: ({ children }: { children?: React.ReactNode }) => (
      <td className={`border px-3 py-2 align-top ${dark ? "border-white/40" : "border-gray-300"}`}>{children}</td>
    ),
    hr: () => <hr className={`!mt-3 !mb-1 ${dark ? "border-white/40" : "border-gray-300"}`} />,
    ul: ({ children }: { children?: React.ReactNode }) => (
      <ul className="list-disc pl-5 my-2 space-y-1">{children}</ul>
    ),
    ol: ({ children }: { children?: React.ReactNode }) => (
      <ol className="list-decimal pl-5 my-2 space-y-1">{children}</ol>
    ),
    li: ({ children }: { children?: React.ReactNode }) => (
      <li className="leading-normal">{children}</li>
    ),
    blockquote: ({ children }: { children?: React.ReactNode }) => (
      <blockquote className={`inline-block border-2 rounded px-3 py-2 my-2 break-words overflow-wrap-anywhere text-[1.15em] max-w-full ${dark ? "border-white/60" : "border-gray-800"}`}>
        {children}
      </blockquote>
    ),
    pre: ({ children }: { children?: React.ReactNode }) => (
      <pre className={`overflow-x-auto max-w-full rounded p-2 text-sm ${dark ? "bg-white/15 text-white" : "bg-gray-100 text-gray-900"}`}>
        {children}
      </pre>
    ),
    code: ({ className, children }: { className?: string; children?: React.ReactNode }) => (
      <code className={`${className ?? ""} break-all`}>{children}</code>
    ),
  };
}

const components = makeComponents(false);
const darkComponents = makeComponents(true);

const inlineComponents = {
  ...components,
  p: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
};

export default function MarkdownMessage({ content, inline = false, dark = false }: Readonly<{ content: string; inline?: boolean; dark?: boolean }>) {
  const wrapped_content = wrapExpressions(content);
  const containerRef = useRef<HTMLDivElement>(null);

  // Scale down display math blocks that are wider than their container so they
  // never overflow the chat bubble — even when the user changes browser zoom.
  useEffect(() => {
    if (inline) return;
    const el = containerRef.current;
    if (!el) return;

    const fitMath = () => {
      // Reset all inline font-size overrides so the browser lays out at natural size.
      const displays = el.querySelectorAll<HTMLElement>(".katex-display");
      displays.forEach((d: HTMLElement) => { d.style.fontSize = ""; });
      // Defer the measurement to the next animation frame — avoids forcing a
      // synchronous reflow inside the ResizeObserver callback, which would
      // re-trigger the observer and cause a flash/loop on resize.
      requestAnimationFrame(() => {
        if (!containerRef.current) return;
        displays.forEach((d: HTMLElement) => {
          const available = d.clientWidth;
          if (d.scrollWidth > available && available > 0) {
            // Clamp to 0.65em minimum so equations remain legible on mobile
            // even when they can't fully fit — the container scrolls horizontally.
            d.style.fontSize = `${Math.max(0.65, available / d.scrollWidth)}em`;
          }
        });
      });
    };

    const ro = new ResizeObserver(fitMath);
    ro.observe(el);
    fitMath();
    return () => ro.disconnect();
  }, [wrapped_content, inline]);

  let activeComponents = dark ? darkComponents : components;
  if (inline) activeComponents = inlineComponents;

  const rendered = (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[
        [rehypeSanitize, schema],
        [rehypeKatex, { output: "html" }],
      ]}
      components={activeComponents}
    >
      {wrapped_content}
    </ReactMarkdown>
  );

  if (inline) return <span>{rendered}</span>;

  return (
    <div ref={containerRef} className="prose prose-base text-base max-w-none break-words [&>*+h2]:mt-5 [&>*+h3]:mt-4 [&>*+h4]:mt-3 [&>p+p]:mt-3">
      {rendered}
    </div>
  );
}
