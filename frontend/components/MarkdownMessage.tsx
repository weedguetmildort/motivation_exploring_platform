import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

function wrapExpressions(text: string): string {
  // wraps "\n[...\n]" for own line formulas
  text = text.replace(/(?:^|\n)\[\n([\s\S]+?)\n\](?:\n|$)/g, (_, inner) => `\n$$\n${inner.trim()}\n$$\n`);

  // wraps inline \(...\) or \[...\]
  text = text.replace(/\\\((.+?)\\\)/gs, (_, inner) => `$${inner.trim()}$`);
  text = text.replace(/\\\[(.+?)\\\]/gs, (_, inner) => `$${inner.trim()}$`);

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