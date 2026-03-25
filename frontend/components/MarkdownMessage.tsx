import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

function wrapExpressions(text: string): string {
  // Step 1: Normalize \(...\) and \[...\] → $...$ so all math uses one delimiter.
  text = text.replace(/(?:^|\n)\[\n([\s\S]+?)\n\](?:\n|$)/g,
    (_, inner) => `\n$$\n${inner.trim()}\n$$\n`);
  text = text.replace(/\\\(([\s\S]+?)\\\)/g, (_, inner) => `$${inner.trim()}$`);
  text = text.replace(/\\\[([\s\S]+?)\\\]/g, (_, inner) => `$${inner.trim()}$`);

  // Step 2: Collapse inline $...$ that spans a single newline.
  // remark-math only parses single-line inline math. The AI sometimes wraps a
  // formula onto the next line (e.g. newline before the closing $). This must
  // run before step 3 so pipe-escaping sees the complete formula on one line.
  text = text.replace(/\$(?!\$)((?:[^\n$]|\n(?!\n)){1,500})\$(?!\$)/g, (match, inner) => {
    if (!inner.includes("\n")) return match;
    return `$${inner.replace(/\s*\n\s*/g, " ")}$`;
  });

  // Step 3: Escape | inside $...$ so GFM table rows aren't split on math operators
  // like P(A|B). After step 2 all formulas are on a single line, so [^$\n]+ is safe.
  text = text.replace(/\$(?!\$)([^$\n]+)\$(?!\$)/g, (match, inner) =>
    inner.includes("|") ? `$${inner.replace(/\|/g, "\\vert ")}$` : match
  );

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

const components = {
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-blue-600 underline hover:text-blue-800"
    >
      {children}
    </a>
  ),
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="overflow-x-auto my-3">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th className="border border-gray-300 bg-gray-50 px-3 py-2 text-left font-semibold whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="border border-gray-300 px-3 py-2 align-top">{children}</td>
  ),
  hr: () => <hr className="!mt-3 !mb-1 border-gray-300" />,
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
    <blockquote className="inline-block border-2 border-gray-800 rounded px-3 py-2 my-2 break-words overflow-wrap-anywhere text-[1.15em] max-w-full">
      {children}
    </blockquote>
  ),
};

const inlineComponents = {
  ...components,
  p: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
};

export default function MarkdownMessage({ content, inline = false }: { content: string; inline?: boolean }) {
  const wrapped_content = wrapExpressions(content);

  const rendered = (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[
        [rehypeSanitize, schema],
        [rehypeKatex, { output: "html" }],
      ]}
      components={inline ? inlineComponents : components}
    >
      {wrapped_content}
    </ReactMarkdown>
  );

  if (inline) return <span>{rendered}</span>;

  return (
    <div className="prose prose-sm max-w-none [&>*+h2]:mt-5 [&>*+h3]:mt-4 [&>*+h4]:mt-3 [&>p+p]:mt-3">
      {rendered}
    </div>
  );
}