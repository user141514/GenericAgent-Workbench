import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownMessageProps = {
  role: string;
  text: string;
};

export function MarkdownMessage({ role, text }: MarkdownMessageProps) {
  if (!text) return null;

  if (role !== "assistant" && role !== "system") {
    return <p className="plain-message-text">{text}</p>;
  }

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
