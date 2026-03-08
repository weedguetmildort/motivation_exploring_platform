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
    // allow KaTeX/Math HTML output
    span: [
      ...(defaultSchema.attributes?.span || []),
      ["className"],
      ["style"],
    ],
    div: [
      ...(defaultSchema.attributes?.div || []),
      ["className"],
      ["style"],
    ],
  },
};

export default function MarkdownMessage({ content }: { content: string }) {
  const wrapped_content = wrapExpressions(content);

  return (
    <div className="prose prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[
          [rehypeSanitize, schema],
          rehypeKatex,
        ]}
      >
        {wrapped_content}
      </ReactMarkdown>
    </div>
  );
}